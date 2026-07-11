# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib import admin

from django_contentdb_translator.models import TranslationLink


@admin.register(TranslationLink)
class TranslationLinkAdmin(admin.ModelAdmin):
    list_display = ("source_draft_id", "translated_draft_id", "source_language", "target_language", "created_at")
    list_filter = ("target_language", "source_language")
    search_fields = ("source_draft_id", "translated_draft_id")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
