# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Backfill TranslationLink records for existing translations.

Matches source drafts to translations by (name, content_type) — works for
static pages where name is preserved across languages. Blog posts with
translated names are skipped (no reliable matching without explicit tracking).
"""

from django.core.management.base import BaseCommand

from django_contentdb_translator.models import TranslationLink


class Command(BaseCommand):
    help = "Backfill TranslationLink records for existing translated drafts."

    def add_arguments(self, parser):
        parser.add_argument("--source-language", default="en", help="Source language ISO2 (default: en)")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")

    def handle(self, *args, **options):
        from django_contentdb.models import Draft

        source_lang = options["source_language"].lower()
        dry_run = options["dry_run"]

        # Get all source drafts
        source_drafts = list(
            Draft.objects.filter(
                language__iso2__iexact=source_lang,
                content_type__is_layout_extender=False,
            ).select_related("content_type", "language")
        )

        created = 0
        skipped = 0

        for source in source_drafts:
            # Find drafts with SAME name + content_type in OTHER languages
            translations = (
                Draft.objects.filter(
                    name=source.name,
                    content_type=source.content_type,
                )
                .exclude(
                    language__iso2__iexact=source_lang,
                )
                .select_related("language")
            )

            for trans in translations:
                target_lang = trans.language.iso2.lower()

                # Skip if link already exists
                if TranslationLink.objects.filter(source_draft_id=source.pk, target_language=target_lang).exists():
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  Link: {source.name} ({source_lang}) → {trans.name} ({target_lang}) [draft {source.pk} → {trans.pk}]"
                    )
                else:
                    TranslationLink.objects.create(
                        source_draft_id=source.pk,
                        translated_draft_id=trans.pk,
                        source_language=source_lang,
                        target_language=target_lang,
                    )
                created += 1

        action = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"\n{action} {created} links (skipped {skipped} existing)"))
        if dry_run:
            self.stdout.write("Run without --dry-run to apply.")
