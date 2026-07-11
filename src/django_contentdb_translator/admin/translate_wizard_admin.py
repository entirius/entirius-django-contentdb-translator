# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Django admin wizard for AI content translation.

Adds a 3-step wizard to Django admin:
1. Configure: channel, languages, scope, options
2. Estimate: dry_run cost preview with per-language breakdown
3. Dispatch: create translation jobs, show job IDs
"""

from __future__ import annotations

import logging

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from django_contentdb_translator.admin.forms import TranslateConfigForm
from django_contentdb_translator.models import TranslationLink
from django_contentdb_translator.services import translator

logger = logging.getLogger("process")

WIZARD_SESSION_KEY = "translate_wizard_config"


class TranslateWizardProxy(TranslationLink):
    """Proxy model to mount the translation wizard in Django admin."""

    class Meta:
        proxy = True
        verbose_name = "Translate content"
        verbose_name_plural = "Translate content"


def _get_channels():
    try:
        from django_contentdb.models import ContentChannel

        return list(ContentChannel.objects.all().order_by("name"))
    except ImportError:
        return []


def _get_languages():
    try:
        from django_regional.models import Language

        return list(Language.objects.all().order_by("name_en"))
    except ImportError:
        return []


def _get_content_types():
    try:
        from django_contentdb.models import ContentType

        return list(ContentType.objects.filter(is_layout_extender=False).order_by("label"))
    except ImportError:
        return []


def _detect_source_language(channel_idx: str) -> str | None:
    """Detect source language from existing drafts in the channel.

    Picks the language with the most drafts assigned to this channel.
    Falls back to channel.default_language when no drafts exist.
    """
    try:
        from django.db.models import Count
        from django_contentdb.models import ContentChannel, Draft

        most_common = (
            Draft.objects.filter(channels__idx=channel_idx)
            .values("language__iso2")
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )
        if most_common and most_common["language__iso2"]:
            return most_common["language__iso2"].lower()

        channel = ContentChannel.objects.select_related("default_language").get(idx=channel_idx)
        if channel.default_language:
            return channel.default_language.iso2.lower()
    except Exception:
        pass
    return None


@admin.register(TranslateWizardProxy)
class TranslateWizardAdmin(admin.ModelAdmin):
    """Admin entry point for the translation wizard.

    The changelist is hidden — users are redirected to step 1 of the wizard.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("wizard/", self.admin_site.admin_view(self.step1_config), name="contentdb_translate_step1"),
            path("wizard/estimate/", self.admin_site.admin_view(self.step2_estimate), name="contentdb_translate_step2"),
            path("wizard/dispatch/", self.admin_site.admin_view(self.step3_dispatch), name="contentdb_translate_step3"),
        ]
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse("admin:contentdb_translate_step1"))

    # ------------------------------------------------------------------
    # Step 1: Configuration form
    # ------------------------------------------------------------------

    def step1_config(self, request):
        channels = _get_channels()
        languages = _get_languages()
        content_types = _get_content_types()

        if request.method == "POST":
            form = TranslateConfigForm(
                request.POST, channels=channels, languages=languages, content_types=content_types
            )
            if form.is_valid():
                request.session[WIZARD_SESSION_KEY] = form.cleaned_data
                return HttpResponseRedirect(reverse("admin:contentdb_translate_step2"))
        else:
            # Pre-fill source language from most common draft language in the first channel
            initial = {}
            if channels:
                detected = _detect_source_language(channels[0].idx)
                if detected:
                    initial["source_language"] = detected
            form = TranslateConfigForm(
                initial=initial, channels=channels, languages=languages, content_types=content_types
            )

        context = {
            **self.admin_site.each_context(request),
            "title": "Translate content — Step 1: Configuration",
            "form": form,
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        return TemplateResponse(request, "admin/django_contentdb_translator/translate_step1.html", context)

    # ------------------------------------------------------------------
    # Step 2: Cost estimate (dry_run=True)
    # ------------------------------------------------------------------

    def step2_estimate(self, request):
        config = request.session.get(WIZARD_SESSION_KEY)
        if not config:
            return HttpResponseRedirect(reverse("admin:contentdb_translate_step1"))

        try:
            estimate = _run_estimate(config)
        except Exception as exc:
            logger.exception("Translation estimate failed")
            context = {
                **self.admin_site.each_context(request),
                "title": "Translate content — Estimate Error",
                "error": str(exc),
                "opts": self.model._meta,
                "has_view_permission": True,
            }
            return TemplateResponse(request, "admin/django_contentdb_translator/translate_error.html", context)

        estimate_data = estimate.model_dump()

        context = {
            **self.admin_site.each_context(request),
            "title": "Translate content — Step 2: Cost Estimate",
            "config": config,
            "estimate": estimate_data,
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        return TemplateResponse(request, "admin/django_contentdb_translator/translate_step2.html", context)

    # ------------------------------------------------------------------
    # Step 3: Dispatch translation jobs (dry_run=False)
    # ------------------------------------------------------------------

    def step3_dispatch(self, request):
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:contentdb_translate_step1"))

        config = request.session.pop(WIZARD_SESSION_KEY, None)
        if not config:
            return HttpResponseRedirect(reverse("admin:contentdb_translate_step1"))

        try:
            result = _run_translate(config)
        except Exception as exc:
            logger.exception("Translation dispatch failed")
            context = {
                **self.admin_site.each_context(request),
                "title": "Translate content — Dispatch Error",
                "error": str(exc),
                "opts": self.model._meta,
                "has_view_permission": True,
            }
            return TemplateResponse(request, "admin/django_contentdb_translator/translate_error.html", context)

        result_data = result.model_dump()

        context = {
            **self.admin_site.each_context(request),
            "title": "Translate content — Jobs Dispatched",
            "config": config,
            "result": result_data,
            "opts": self.model._meta,
            "has_view_permission": True,
        }
        return TemplateResponse(request, "admin/django_contentdb_translator/translate_step3.html", context)


def _run_estimate(config: dict):
    """Run dry_run=True estimation based on wizard config."""
    scope = config["scope"]

    if scope == "single":
        return translator.translate_draft(
            channel_idx=config["channel"],
            draft_uid=config["draft_uid"],
            target_languages=config["target_languages"],
            source_language=config["source_language"],
            provider=config.get("provider") or None,
            dry_run=True,
        )

    return translator.translate_bulk(
        channel_idx=config["channel"],
        entity_type=config["entity_type"],
        target_languages=config["target_languages"],
        source_language=config["source_language"],
        provider=config.get("provider") or None,
        content_type_slug=config.get("content_type_slug") or None,
        dry_run=True,
        force=config.get("force", False),
    )


def _run_translate(config: dict):
    """Dispatch translation jobs (dry_run=False)."""
    scope = config["scope"]

    if scope == "single":
        return translator.translate_draft(
            channel_idx=config["channel"],
            draft_uid=config["draft_uid"],
            target_languages=config["target_languages"],
            source_language=config["source_language"],
            provider=config.get("provider") or None,
            force=config.get("force", False),
            publish=config.get("publish", False),
            dry_run=False,
        )

    return translator.translate_bulk(
        channel_idx=config["channel"],
        entity_type=config["entity_type"],
        target_languages=config["target_languages"],
        source_language=config["source_language"],
        provider=config.get("provider") or None,
        content_type_slug=config.get("content_type_slug") or None,
        force=config.get("force", False),
        publish=config.get("publish", False),
        dry_run=False,
    )
