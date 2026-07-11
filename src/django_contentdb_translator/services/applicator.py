# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Apply translations back to ContentDB structures.

Core pattern: clone Draft with translated JSON rather than update in place.
Each language version is a separate Draft — that's ContentDB's multi-language model.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field

from django.db import transaction
from django_utils_translator.sanitize import sanitize

from django_contentdb_translator.settings import (
    TRANSLATABLE_EXTENSION_FIELDS,
    TRANSLATABLE_META_FIELDS,
    TRANSLATABLE_NAV_COLUMN_FIELDS,
    TRANSLATABLE_NAV_ITEM_FIELDS,
    TRANSLATABLE_NAV_LINK_FIELDS,
    TRANSLATABLE_SECTION_FIELDS,
    TRANSLATABLE_TILE_FIELDS,
)

logger = logging.getLogger("process")

_ALLOWED_AUTHOR_T9N_FIELDS = frozenset({"role", "description", "tag"})


@dataclass
class ApplyResult:
    created_draft_id: int | None = None
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def apply_page_translation(
    source_draft_id: int,
    items: list[dict],
    target_language: str,
    channel_idx: str,
    force: bool = False,
    publish: bool = False,
) -> ApplyResult:
    """Clone a Draft with translated content JSON."""
    from django_contentdb.models import Draft

    result = ApplyResult()
    source_draft = Draft.objects.select_related("content", "content_type", "language").get(pk=source_draft_id)

    translations = _build_translation_lookup(items)
    if not translations:
        result.skipped = len(items)
        return result

    target_lang_obj = _get_or_create_contentdb_language(target_language)
    if not target_lang_obj:
        result.errors.append(f"Language '{target_language}' not found in ContentDB and could not be created")
        return result

    if not force and _has_existing_translation(source_draft, target_lang_obj):
        result.skipped = len(items)
        return result

    source_route_urls = list(source_draft.routes.values_list("url", flat=True))

    with transaction.atomic():
        new_draft = _create_translated_draft(source_draft, translations, target_lang_obj, source_route_urls, force)
        result.created_draft_id = new_draft.pk

        # Record link: source draft → translated draft
        from django_contentdb_translator.models import TranslationLink

        TranslationLink.objects.update_or_create(
            source_draft_id=source_draft.pk,
            target_language=target_language,
            defaults={
                "translated_draft_id": new_draft.pk,
                "source_language": source_draft.language.iso2.lower(),
            },
        )

        if publish:
            _publish_draft(new_draft, source_draft.content)

        result.updated = len(translations)

    return result


def _build_translation_lookup(items: list[dict]) -> dict[str, str]:
    """Build key → sanitized translated text lookup from toolbox results."""
    translations: dict[str, str] = {}
    for item in items:
        key = item.get("key", "")
        text = item.get("translated_text", "") or item.get("text", "")
        if key and text:
            translations[key] = sanitize(text)
    return translations


def _has_existing_translation(source_draft, target_lang_obj) -> bool:
    """Check if a translation already exists for this draft in the target language.

    Uses TranslationLink — reliable mapping created when translations are applied.
    """
    from django_contentdb_translator.models import TranslationLink

    return TranslationLink.objects.filter(
        source_draft_id=source_draft.pk,
        target_language=target_lang_obj.iso2.lower(),
    ).exists()


def _create_translated_draft(source_draft, translations, target_lang_obj, source_route_urls, force):
    """Create or update translated Draft with translated JSON.

    When force=True and a TranslationLink exists, UPDATE the existing draft's
    Content in place instead of creating duplicates.
    """
    from django_contentdb.models import Content, ContentAttribute, Draft

    from django_contentdb_translator.models import TranslationLink

    source_content = source_draft.content

    new_content_json = _apply_translations_to_content(copy.deepcopy(source_content.content or {}), translations)
    new_meta_json = _apply_translations_to_meta(copy.deepcopy(source_content.meta or {}), translations)
    new_extension_json = _apply_translations_to_extension(copy.deepcopy(source_content.extension or {}), translations)
    new_category = _resolve_translated_category(source_content, translations, target_lang_obj)
    translated_name = (
        translations.get("draft.name")
        or new_meta_json.get("title")
        or new_extension_json.get("title")
        or source_draft.name
    )

    # Check if we should UPDATE an existing translation (force=True + link exists)
    existing_link = TranslationLink.objects.filter(
        source_draft_id=source_draft.pk,
        target_language=target_lang_obj.iso2.lower(),
    ).first()

    if existing_link:
        try:
            existing_draft = Draft.objects.select_related("content").get(pk=existing_link.translated_draft_id)
            # Update existing content in place
            existing_content = existing_draft.content
            existing_content.content = new_content_json
            existing_content.meta = new_meta_json
            existing_content.extension = new_extension_json
            existing_content.category = new_category
            existing_content.save(update_fields=["content", "meta", "extension", "category", "updated_at"])

            # Update draft name
            existing_draft.name = translated_name
            existing_draft.save(update_fields=["name"])

            # Update routes
            route_translations = {k: v for k, v in translations.items() if k.startswith("route.")}
            existing_draft.routes.clear()
            _create_translated_routes(existing_draft, source_draft, route_translations)

            logger.info(
                "Updated existing translation draft %d for source %d → %s",
                existing_draft.pk,
                source_draft.pk,
                target_lang_obj.iso2,
            )
            return existing_draft
        except Draft.DoesNotExist:
            # Link is stale — translated draft was deleted. Fall through to create new.
            existing_link.delete()

    # Create new Content + Draft
    new_content = Content.objects.create(
        content=new_content_json,
        meta=new_meta_json,
        extension=new_extension_json,
        category=new_category,
    )

    # Copy attributes
    source_attrs = ContentAttribute.objects.filter(content=source_content)
    ContentAttribute.objects.bulk_create(
        [ContentAttribute(content=new_content, attribute_value_id=sa.attribute_value_id) for sa in source_attrs]
    )

    new_draft = Draft.objects.create(
        content_type=source_draft.content_type,
        content=new_content,
        name=translated_name,
        language=target_lang_obj,
        is_system=source_draft.is_system,
    )

    # Copy channels
    source_channels = list(source_draft.channels.all())
    if source_channels:
        new_draft.channels.set(source_channels)

    # Create translated routes, copy authors & content sets
    route_translations = {k: v for k, v in translations.items() if k.startswith("route.")}
    _create_translated_routes(new_draft, source_draft, route_translations)
    _copy_authors(source_draft, new_draft)
    _copy_content_set(source_draft, new_draft)

    return new_draft


def _resolve_translated_category(source_content, translations, target_lang_obj):
    """Get or create a translated Category if category name/url_key was translated."""
    translated_cat_name = translations.get("category.name")
    translated_cat_url_key = translations.get("category.url_key")
    if not source_content.category or not (translated_cat_name or translated_cat_url_key):
        return source_content.category

    from django_contentdb.models import Category

    new_category, _ = Category.objects.get_or_create(
        name=translated_cat_name or source_content.category.name,
        language=target_lang_obj,
        defaults={"url_key": translated_cat_url_key or source_content.category.url_key},
    )
    return new_category


def _publish_draft(new_draft, source_content) -> None:
    """Create a Published record for a newly translated draft."""
    from django_contentdb.models import Content, Published

    publish_content = Content.objects.create(
        content=copy.deepcopy(new_draft.content.content),
        meta=copy.deepcopy(new_draft.content.meta),
        extension=copy.deepcopy(new_draft.content.extension),
        category=source_content.category,
    )
    Published.objects.create(draft=new_draft, content=publish_content)


def apply_author_translations(
    items: list[dict],
    target_language: str,
) -> ApplyResult:
    """Update author t9n fields with translations."""
    from django_contentdb.models import Author

    result = ApplyResult()
    author_updates: dict[str, dict[str, str]] = {}

    for item in items:
        key = item.get("key", "")
        text = item.get("translated_text", "") or item.get("text", "")
        if not key or not text:
            continue
        # key format: author.<uid>.<field>
        parts = key.split(".")
        if len(parts) != 3 or parts[0] != "author":
            continue
        uid, field_name = parts[1], parts[2]
        author_updates.setdefault(uid, {})[field_name] = sanitize(text)

    if not author_updates:
        return result

    with transaction.atomic():
        authors = {
            str(a.uid): a for a in Author.objects.select_for_update().filter(uid__in=list(author_updates.keys()))
        }
        to_update: list = []
        for uid, fields in author_updates.items():
            author = authors.get(uid)
            if not author:
                result.errors.append(f"Author {uid} not found")
                continue
            for field_name, text in fields.items():
                if field_name not in _ALLOWED_AUTHOR_T9N_FIELDS:
                    result.errors.append(f"Author {uid}: disallowed field '{field_name}'")
                    continue
                t9n_attr = f"{field_name}_t9n"
                t9n = getattr(author, t9n_attr, None)
                if not isinstance(t9n, dict):
                    t9n = {}
                t9n[target_language] = text
                setattr(author, t9n_attr, t9n)
            to_update.append(author)
            result.updated += 1

        if to_update:
            Author.objects.bulk_update(to_update, fields=["role_t9n", "description_t9n", "tag_t9n"], batch_size=500)

    return result


# --- Internal helpers ---


def _get_or_create_contentdb_language(iso2: str):
    """Get or create a django_contentdb.Language for the given iso2 code.

    Falls back to django_regional.Language for iso3 + name metadata when creating.
    """
    from django_contentdb.models import Language

    iso2_lower = iso2.lower()
    lang = Language.objects.filter(iso2__iexact=iso2_lower).first()
    if lang:
        return lang

    iso3, name_en, name_pl = _lookup_language_metadata(iso2_lower)
    lang, _ = Language.objects.get_or_create(
        iso2=iso2_lower,
        defaults={"iso3": iso3, "name_en": name_en, "name_pl": name_pl},
    )
    logger.info("Auto-created django_contentdb.Language iso2=%s iso3=%s", iso2_lower, iso3)
    return lang


def _lookup_language_metadata(iso2: str) -> tuple[str, str, str]:
    """Return (iso3, name_en, name_pl) for an iso2 code.

    Prefers django_regional.Language; falls back to a minimal static mapping.
    """
    try:
        from django_regional.models import Language as RegionalLanguage

        reg = RegionalLanguage.objects.filter(iso2__iexact=iso2).first()
        if reg:
            return reg.iso3.lower(), reg.name_en or iso2, getattr(reg, "name_pl", "") or ""
    except Exception:
        pass

    fallback = {
        "en": ("eng", "english", "angielski"),
        "pl": ("pol", "polish", "polski"),
        "de": ("ger", "german", "niemiecki"),
        "fr": ("fre", "french", "francuski"),
        "es": ("spa", "spanish", "hiszpański"),
        "it": ("ita", "italian", "włoski"),
        "pt": ("por", "portuguese", "portugalski"),
        "nl": ("dut", "dutch", "holenderski"),
        "cs": ("cze", "czech", "czeski"),
        "sk": ("slo", "slovak", "słowacki"),
        "ru": ("rus", "russian", "rosyjski"),
        "uk": ("ukr", "ukrainian", "ukraiński"),
        "ro": ("rum", "romanian", "rumuński"),
        "hu": ("hun", "hungarian", "węgierski"),
    }
    iso3, name_en, name_pl = fallback.get(iso2, (iso2 * 2, iso2, iso2))
    return iso3[:3], name_en, name_pl


def _apply_translations_to_content(content_json: dict, translations: dict[str, str]) -> dict:
    """Apply tile and section translations to a deep-copied content JSON."""
    tiles = content_json.get("tiles", {})
    if isinstance(tiles, dict):
        for tile_uuid, tile_data in tiles.items():
            if not isinstance(tile_data, dict):
                continue
            for field in TRANSLATABLE_TILE_FIELDS:
                key = f"tile.{tile_uuid}.{field}"
                if key in translations:
                    tile_data[field] = translations[key]

            for i, button in enumerate(tile_data.get("custom_buttons", []) or []):
                if not isinstance(button, dict):
                    continue
                key = f"tile.{tile_uuid}.btn.{i}.label"
                if key in translations:
                    button["label"] = translations[key]

    sections = content_json.get("sections", {})
    if isinstance(sections, dict):
        for section_uuid, section_data in sections.items():
            if not isinstance(section_data, dict):
                continue
            for field in TRANSLATABLE_SECTION_FIELDS:
                key = f"section.{section_uuid}.{field}"
                if key in translations:
                    section_data[field] = translations[key]

            for i, button in enumerate(section_data.get("custom_buttons", []) or []):
                if not isinstance(button, dict):
                    continue
                key = f"section.{section_uuid}.btn.{i}.label"
                if key in translations:
                    button["label"] = translations[key]

    # Navigation content (header/footer)
    items = content_json.get("items")
    if isinstance(items, list):
        _apply_navigation_translations(items, translations)

    return content_json


def _apply_navigation_translations(items: list, translations: dict[str, str]) -> None:
    """Apply translations to navigation JSON items in place."""
    for nav_item in items:
        if not isinstance(nav_item, dict):
            continue
        item_id = nav_item.get("id", "")
        for field in TRANSLATABLE_NAV_ITEM_FIELDS:
            key = f"nav.{item_id}.{field}"
            if key in translations:
                nav_item[field] = translations[key]

        for column in nav_item.get("columns", []):
            if not isinstance(column, dict):
                continue
            col_id = column.get("id", "")
            for field in TRANSLATABLE_NAV_COLUMN_FIELDS:
                key = f"nav.{item_id}.col.{col_id}.{field}"
                if key in translations:
                    column[field] = translations[key]

            for link in column.get("links", []):
                if not isinstance(link, dict):
                    continue
                link_id = link.get("id", "")
                for field in TRANSLATABLE_NAV_LINK_FIELDS:
                    key = f"nav.{item_id}.col.{col_id}.link.{link_id}.{field}"
                    if key in translations:
                        link[field] = translations[key]


def _apply_translations_to_meta(meta_json: dict, translations: dict[str, str]) -> dict:
    """Apply meta field translations to a deep-copied meta JSON."""
    if not meta_json:
        return meta_json
    for field in TRANSLATABLE_META_FIELDS:
        key = f"meta.{field}"
        if key in translations:
            meta_json[field] = translations[key]
    return meta_json


def _apply_translations_to_extension(extension_json: dict, translations: dict[str, str]) -> dict:
    """Apply extension field translations to a deep-copied extension JSON."""
    if not extension_json:
        return extension_json
    for field in TRANSLATABLE_EXTENSION_FIELDS:
        key = f"ext.{field}"
        if key in translations:
            extension_json[field] = translations[key]

    for i, button in enumerate(extension_json.get("custom_buttons", []) or []):
        if not isinstance(button, dict):
            continue
        key = f"ext.btn.{i}.label"
        if key in translations:
            button["label"] = translations[key]

    return extension_json


def _create_translated_routes(new_draft, source_draft, route_translations: dict[str, str]) -> None:
    """Create new routes with translated URLs and assign to draft."""
    from django_contentdb.models import Route

    source_routes = list(source_draft.routes.all())
    for route in source_routes:
        key = f"route.{route.pk}.url"
        translated_url = route_translations.get(key)
        if translated_url:
            new_route, _ = Route.objects.get_or_create(
                url=translated_url, defaults={"label": route.label, "placement": route.placement}
            )
            new_draft.routes.add(new_route)
        else:
            # No translation for this route — share the original
            new_draft.routes.add(route)


def _copy_authors(source_draft, new_draft) -> None:
    """Copy DraftAuthor and DraftCoAuthor from source to new draft."""
    from django_contentdb.models import DraftAuthor, DraftCoAuthor

    source_authors = list(DraftAuthor.objects.filter(draft=source_draft).order_by("position"))
    if source_authors:
        DraftAuthor.objects.bulk_create(
            [DraftAuthor(draft=new_draft, author=da.author, position=da.position) for da in source_authors],
            batch_size=500,
        )

    source_coauthors = list(DraftCoAuthor.objects.filter(draft=source_draft).order_by("position"))
    if source_coauthors:
        DraftCoAuthor.objects.bulk_create(
            [DraftCoAuthor(draft=new_draft, author=dca.author, position=dca.position) for dca in source_coauthors],
            batch_size=500,
        )


def _copy_content_set(source_draft, new_draft) -> None:
    """Copy ContentSet membership from source to new draft."""
    from django_contentdb.models import DraftToContentSet

    membership = DraftToContentSet.objects.filter(draft=source_draft).first()
    if membership:
        DraftToContentSet.objects.get_or_create(content_set=membership.content_set, draft=new_draft)
