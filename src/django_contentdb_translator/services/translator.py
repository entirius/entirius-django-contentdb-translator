# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Orchestrator: extract → toolbox estimate/job → apply translations.

Connects extractors, the remote AI toolbox, and applicators.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django_utils_translator.clients import ToolboxClient
from django_utils_translator.schemas.responses import BulkTranslateJobResponse as BaseBulkJobResponse
from django_utils_translator.schemas.responses import LanguageCostEstimate
from django_utils_translator.settings import map_to_provider_code

from django_contentdb_translator.schemas.responses import (
    ContentBulkEstimateResponse,
    DraftBreakdown,
    TranslateDraftResponse,
)
from django_contentdb_translator.services.extractor import (
    extract_author_items,
    extract_navigation_items,
    extract_page_items,
    extract_route_items,
)

logger = logging.getLogger("process")


def _build_per_language_estimates(
    estimate: dict,
    target_languages: list[str],
    items_count: int,
    total_chars: int,
) -> list[LanguageCostEstimate]:
    """Build per-language cost estimates from toolbox response."""
    per_lang_data = estimate.get("per_language", [])
    result = []
    for i, lang in enumerate(target_languages):
        cost = per_lang_data[i].get("estimated_cost_usd") if i < len(per_lang_data) else None
        result.append(
            LanguageCostEstimate(
                language=lang,
                items=items_count,
                chars=total_chars,
                cost_usd=Decimal(str(cost)) if cost else None,
            )
        )
    return result


def _resolve_source_language(channel_idx: str, source_language: str | None) -> str:
    """Resolve source language from explicit param or channel default."""
    if source_language:
        return source_language
    try:
        from django_contentdb.models import ContentChannel
    except ImportError:
        return "en"
    try:
        channel = ContentChannel.objects.select_related("default_language").get(idx=channel_idx)
        if channel.default_language:
            return channel.default_language.iso2.lower()
    except ContentChannel.DoesNotExist:
        pass
    return "en"


def translate_draft(
    channel_idx: str,
    draft_uid: str,
    target_languages: list[str],
    source_language: str | None = None,
    provider: str | None = None,
    formality: str | None = None,
    context: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    publish: bool = False,
) -> TranslateDraftResponse:
    """Translate a single Draft to target languages."""
    source_lang = _resolve_source_language(channel_idx, source_language)
    draft, items, is_nav = _prepare_draft(draft_uid)

    source_routes = [r.url for r in draft.routes.all()]
    existing_langs = _get_existing_translation_languages(draft, source_routes)
    missing_langs = [lang for lang in target_languages if lang not in existing_langs]
    total_chars = sum(len(item["text"]) for item in items)

    if not items:
        return TranslateDraftResponse(
            draft_uid=str(draft.content.uid),
            draft_name=draft.name,
            dry_run=dry_run,
            items=0,
            total_chars=0,
            estimated_cost_usd=Decimal("0"),
            target_languages=target_languages,
            existing_translations=existing_langs,
            missing_translations=missing_langs,
        )

    if dry_run:
        return _estimate_single_draft(
            channel_idx,
            draft,
            items,
            total_chars,
            target_languages,
            existing_langs,
            missing_langs,
            provider,
        )

    return _dispatch_single_draft(
        channel_idx,
        draft,
        items,
        total_chars,
        is_nav,
        target_languages,
        source_lang,
        existing_langs,
        missing_langs,
        provider,
        formality,
        context,
        force,
        publish,
    )


def _prepare_draft(draft_uid: str) -> tuple:
    """Load draft, extract translatable items. Returns (draft, items, is_nav)."""
    from django_contentdb.models import Draft

    draft = (
        Draft.objects.select_related("content", "content_type", "language", "content__category")
        .prefetch_related("routes")
        .get(content__uid=draft_uid)
    )
    content = draft.content
    is_nav = draft.content_type.is_layout_extender

    if is_nav:
        items = extract_navigation_items(content.content or {})
    else:
        category = content.category
        items = extract_page_items(
            content.content or {},
            content.meta,
            content.extension,
            draft_name=draft.name,
            category_name=category.name if category else None,
            category_url_key=category.url_key if category else None,
        )

    route_data = [{"id": r.pk, "url": r.url} for r in draft.routes.all()]
    items.extend(extract_route_items(route_data))
    return draft, items, is_nav


def _estimate_single_draft(
    channel_idx,
    draft,
    items,
    total_chars,
    target_languages,
    existing_langs,
    missing_langs,
    provider,
) -> TranslateDraftResponse:
    """Dry-run estimate for a single draft."""
    mapped_targets = [map_to_provider_code(lang) for lang in target_languages]
    with ToolboxClient(channel_idx) as client:
        estimate = client.estimate(items=items, target_languages=mapped_targets, provider=provider)
    per_language = _build_per_language_estimates(estimate, target_languages, len(items), total_chars)
    return TranslateDraftResponse(
        draft_uid=str(draft.content.uid),
        draft_name=draft.name,
        dry_run=True,
        items=len(items),
        total_chars=total_chars * len(target_languages),
        estimated_cost_usd=Decimal(str(estimate.get("total_cost_usd", 0))),
        target_languages=target_languages,
        per_language=per_language,
        existing_translations=existing_langs,
        missing_translations=missing_langs,
    )


def _dispatch_single_draft(
    channel_idx,
    draft,
    items,
    total_chars,
    is_nav,
    target_languages,
    source_lang,
    existing_langs,
    missing_langs,
    provider,
    formality,
    context,
    force,
    publish,
) -> TranslateDraftResponse:
    """Create toolbox jobs and dispatch Celery tasks for a single draft."""
    from django_contentdb_translator.tasks.apply_job import poll_and_apply_content_job

    entity_type = "navigation" if is_nav else "page"
    mapped_source = map_to_provider_code(source_lang)
    job_ids = []

    with ToolboxClient(channel_idx) as client:
        for target_lang in target_languages:
            mapped_target = map_to_provider_code(target_lang)
            job = client.create_job(
                items=items,
                target_language=mapped_target,
                source_language=mapped_source,
                provider=provider,
                formality=formality,
                context=context,
                metadata={
                    "entity_type": entity_type,
                    "draft_uid": str(draft.content.uid),
                    "channel_idx": channel_idx,
                    "target_language": target_lang,
                },
            )
            job_id = job.get("id", "")
            job_ids.append(job_id)

            poll_and_apply_content_job.delay(
                job_id=job_id,
                source_draft_id=draft.pk,
                entity_type=entity_type,
                channel_idx=channel_idx,
                target_language=target_lang,
                force=force,
                publish=publish,
            )

    return TranslateDraftResponse(
        draft_uid=str(draft.content.uid),
        draft_name=draft.name,
        dry_run=False,
        items=len(items),
        total_chars=total_chars * len(target_languages),
        estimated_cost_usd=None,
        target_languages=target_languages,
        existing_translations=existing_langs,
        missing_translations=missing_langs,
        job_ids=job_ids,
    )


def translate_bulk(
    channel_idx: str,
    entity_type: str,
    target_languages: list[str],
    source_language: str | None = None,
    provider: str | None = None,
    formality: str | None = None,
    context: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    publish: bool = False,
    content_type_slug: str | None = None,
) -> ContentBulkEstimateResponse | BaseBulkJobResponse:
    """Bulk translate all drafts of a type in a channel.

    When content_type_slug is provided, only drafts of that ContentType are included.
    """
    source_lang = _resolve_source_language(channel_idx, source_language)

    if entity_type == "author":
        return _translate_authors_bulk(channel_idx, target_languages, source_lang, provider, dry_run, force)

    return _translate_drafts_bulk(
        channel_idx,
        entity_type,
        target_languages,
        source_lang,
        provider,
        formality,
        context,
        dry_run,
        force,
        publish,
        content_type_slug=content_type_slug,
    )


def _translate_drafts_bulk(
    channel_idx,
    entity_type,
    target_languages,
    source_lang,
    provider,
    formality,
    context,
    dry_run,
    force,
    publish,
    content_type_slug: str | None = None,
):
    """Bulk translate page or navigation drafts.

    When content_type_slug is provided, only drafts matching that ContentType.slug are included.
    """
    from django.db.models import Q
    from django_contentdb.models import Draft

    is_nav = entity_type == "navigation"

    # Get source-language drafts in this channel
    drafts_qs = (
        Draft.objects.select_related("content", "content__category", "content_type", "language")
        .prefetch_related("routes")
        .filter(
            language__iso2__iexact=source_lang,
            content_type__is_layout_extender=is_nav,
        )
        .filter(Q(channels__idx=channel_idx) | Q(channels__isnull=True))
        .distinct()
    )

    if content_type_slug:
        drafts_qs = drafts_qs.filter(content_type__slug=content_type_slug)

    drafts = list(drafts_qs)
    if not drafts:
        return ContentBulkEstimateResponse(
            entity_type=entity_type,
            estimated_items=0,
            total_chars=0,
            estimated_cost_usd=Decimal("0"),
            target_languages=target_languages,
            per_language=[],
            per_draft=[],
            skipped_drafts=0,
        )

    # Extract items per draft
    draft_items: list[tuple] = []  # (draft, items, route_data)
    for draft in drafts:
        content = draft.content
        if is_nav:
            items = extract_navigation_items(content.content or {})
        else:
            category = content.category
            items = extract_page_items(
                content.content or {},
                content.meta,
                content.extension,
                draft_name=draft.name,
                category_name=category.name if category else None,
                category_url_key=category.url_key if category else None,
            )
        route_data = [{"id": r.pk, "url": r.url} for r in draft.routes.all()]
        items.extend(extract_route_items(route_data))
        if items:
            draft_items.append((draft, items, route_data))

    if not draft_items:
        return ContentBulkEstimateResponse(
            entity_type=entity_type,
            estimated_items=0,
            total_chars=0,
            estimated_cost_usd=Decimal("0"),
            target_languages=target_languages,
            per_language=[],
            per_draft=[],
            skipped_drafts=0,
        )

    mapped_source = map_to_provider_code(source_lang)

    if dry_run:
        return _estimate_drafts_bulk(channel_idx, entity_type, target_languages, draft_items, provider, force)

    return _create_draft_jobs_bulk(
        channel_idx,
        entity_type,
        target_languages,
        draft_items,
        mapped_source,
        provider,
        formality,
        context,
        force,
        publish,
    )


def _estimate_drafts_bulk(channel_idx, entity_type, target_languages, draft_items, provider, force):
    """Estimate cost for bulk draft translation.

    When force=False, filters out drafts that already have translations in target languages.
    """
    # Filter drafts when force=False
    if force:
        filtered_draft_items = draft_items
        skipped = 0
    else:
        skipped_pks = _get_already_translated_draft_pks(draft_items, target_languages)
        filtered_draft_items = [(d, i, r) for d, i, r in draft_items if d.pk not in skipped_pks]
        skipped = len(draft_items) - len(filtered_draft_items)

    # Flatten items from FILTERED drafts only
    all_items = []
    per_draft_breakdown = []
    for draft, items, route_data in filtered_draft_items:
        all_items.extend(items)
        routes = [r["url"] for r in route_data]
        per_draft_breakdown.append(
            DraftBreakdown(
                draft_uid=str(draft.content.uid),
                draft_name=draft.name,
                items=len(items),
                chars=sum(len(item["text"]) for item in items),
                routes=routes,
            )
        )

    if not all_items:
        return ContentBulkEstimateResponse(
            entity_type=entity_type,
            estimated_items=0,
            total_chars=0,
            estimated_cost_usd=Decimal("0"),
            target_languages=target_languages,
            per_language=[],
            per_draft=per_draft_breakdown,
            skipped_drafts=skipped,
        )

    total_chars = sum(len(item["text"]) for item in all_items)
    mapped_targets = [map_to_provider_code(lang) for lang in target_languages]

    with ToolboxClient(channel_idx) as client:
        estimate = client.estimate(items=all_items, target_languages=mapped_targets, provider=provider)

    per_language = _build_per_language_estimates(estimate, target_languages, len(all_items), total_chars)
    total_cost = Decimal(str(estimate.get("total_cost_usd", 0)))

    return ContentBulkEstimateResponse(
        entity_type=entity_type,
        estimated_items=len(all_items),
        total_chars=total_chars * len(target_languages),
        estimated_cost_usd=total_cost,
        target_languages=target_languages,
        per_language=per_language,
        per_draft=per_draft_breakdown,
        skipped_drafts=skipped,
    )


def _create_draft_jobs_bulk(
    channel_idx, entity_type, target_languages, draft_items, mapped_source, provider, formality, context, force, publish
):
    """Create async jobs for bulk draft translation."""
    from django_contentdb_translator.tasks.apply_job import poll_and_apply_content_job

    # Filter drafts when force=False
    if force:
        filtered_draft_items = draft_items
    else:
        skipped_pks = _get_already_translated_draft_pks(draft_items, target_languages)
        filtered_draft_items = [(d, i, r) for d, i, r in draft_items if d.pk not in skipped_pks]

    job_ids = []
    total_cost = Decimal("0")
    total_items = 0

    with ToolboxClient(channel_idx) as client:
        for draft, items, route_data in filtered_draft_items:
            for target_lang in target_languages:
                mapped_target = map_to_provider_code(target_lang)
                job = client.create_job(
                    items=items,
                    target_language=mapped_target,
                    source_language=mapped_source,
                    provider=provider,
                    formality=formality,
                    context=context,
                    metadata={
                        "entity_type": entity_type,
                        "draft_uid": str(draft.content.uid),
                        "channel_idx": channel_idx,
                        "target_language": target_lang,
                    },
                )
                job_id = job.get("id", "")
                job_ids.append(job_id)
                total_items = max(total_items, len(items))

                estimated = job.get("estimated_cost_usd")
                if estimated:
                    total_cost += Decimal(str(estimated))

                poll_and_apply_content_job.delay(
                    job_id=job_id,
                    source_draft_id=draft.pk,
                    entity_type=entity_type,
                    channel_idx=channel_idx,
                    target_language=target_lang,
                    force=force,
                    publish=publish,
                )

    return BaseBulkJobResponse(
        entity_type=entity_type,
        job_ids=job_ids,
        estimated_items=total_items,
        estimated_cost_usd=total_cost,
        status="pending",
        target_languages=target_languages,
    )


def _translate_authors_bulk(channel_idx, target_languages, source_lang, provider, dry_run, force):
    """Bulk translate author t9n fields."""
    from django_contentdb.models import Author

    authors_qs = Author.objects.filter(is_active=True)
    author_data = []
    for author in authors_qs:
        data = {
            "uid": str(author.uid),
            "role_t9n": author.role_t9n or {},
            "description_t9n": author.description_t9n or {},
            "tag_t9n": author.tag_t9n or {},
        }
        if not force:
            # Skip authors who already have all target languages
            has_all = all(
                data["role_t9n"].get(lang) or data["description_t9n"].get(lang) or data["tag_t9n"].get(lang)
                for lang in target_languages
            )
            if has_all:
                continue
        author_data.append(data)

    items = extract_author_items(author_data, source_lang)
    if not items:
        return ContentBulkEstimateResponse(
            entity_type="author",
            estimated_items=0,
            total_chars=0,
            estimated_cost_usd=Decimal("0"),
            target_languages=target_languages,
            per_language=[],
            per_draft=[],
        )

    mapped_targets = [map_to_provider_code(lang) for lang in target_languages]
    total_chars = sum(len(item["text"]) for item in items)

    with ToolboxClient(channel_idx) as client:
        if dry_run:
            estimate = client.estimate(items=items, target_languages=mapped_targets, provider=provider)
            per_language = _build_per_language_estimates(estimate, target_languages, len(items), total_chars)
            return ContentBulkEstimateResponse(
                entity_type="author",
                estimated_items=len(items),
                total_chars=total_chars * len(target_languages),
                estimated_cost_usd=Decimal(str(estimate.get("total_cost_usd", 0))),
                target_languages=target_languages,
                per_language=per_language,
                per_draft=[],
            )

        # Authors are small — process synchronously, one job for all
        from django_contentdb_translator.tasks.apply_job import poll_and_apply_content_job

        job_ids = []
        for target_lang in target_languages:
            mapped_target = map_to_provider_code(target_lang)
            job = client.create_job(
                items=items,
                target_language=mapped_target,
                source_language=map_to_provider_code(source_lang),
                provider=provider,
                metadata={"entity_type": "author", "channel_idx": channel_idx, "target_language": target_lang},
            )
            job_id = job.get("id", "")
            job_ids.append(job_id)
            poll_and_apply_content_job.delay(
                job_id=job_id,
                source_draft_id=None,
                entity_type="author",
                channel_idx=channel_idx,
                target_language=target_lang,
                force=force,
                publish=False,
            )

        return BaseBulkJobResponse(
            entity_type="author",
            job_ids=job_ids,
            estimated_items=len(items),
            estimated_cost_usd=None,
            status="pending",
            target_languages=target_languages,
        )


def _get_already_translated_draft_pks(draft_items: list[tuple], target_languages: list[str]) -> set[int]:
    """Return PKs of source drafts that already have a translation in any target language.

    Uses TranslationLink table — reliable mapping created when translations are applied.
    """
    from django_contentdb_translator.models import TranslationLink

    source_pks = [draft.pk for draft, _, _ in draft_items]
    if not source_pks:
        return set()

    existing_links = TranslationLink.objects.filter(
        source_draft_id__in=source_pks,
        target_language__in=target_languages,
    ).values_list("source_draft_id", flat=True)

    return set(existing_links)


def _get_existing_translation_languages(draft, source_routes: list[str]) -> list[str]:
    """Get languages that already have translations for this draft.

    Uses TranslationLink table for reliable detection.
    """
    from django_contentdb_translator.models import TranslationLink

    existing = TranslationLink.objects.filter(
        source_draft_id=draft.pk,
    ).values_list("target_language", flat=True)
    return list(existing)
