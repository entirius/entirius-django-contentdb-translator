# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tracks which draft was translated from which source draft.

Stored here (not in django-contentdb) to avoid coupling the content module
to the translator. Zero changes to ContentDB models.
"""

from django.db import models


class TranslationLink(models.Model):
    """Maps source draft → translated draft per language.

    source_draft_id=5 (EN) → translated_draft_id=22 (PL)
    source_draft_id=5 (EN) → translated_draft_id=45 (ES)
    """

    source_draft_id = models.IntegerField(db_index=True)
    translated_draft_id = models.IntegerField(unique=True)
    source_language = models.CharField(max_length=5)
    target_language = models.CharField(max_length=5)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "django_contentdb_translator"
        db_table = "contentdb_translator_link"
        constraints = [
            models.UniqueConstraint(
                fields=["source_draft_id", "target_language"],
                name="unique_source_target_lang",
            ),
        ]

    def __str__(self) -> str:
        return f"Draft {self.source_draft_id} ({self.source_language}) → {self.translated_draft_id} ({self.target_language})"
