# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.core.management.base import BaseCommand

from django_contentdb_translator.services import translator


class Command(BaseCommand):
    help = "Bulk translate ContentDB content via AI toolbox."

    def add_arguments(self, parser):
        parser.add_argument("--channel", required=True, help="Channel idx (e.g. default-europe)")
        parser.add_argument("--target", required=True, help="Target language ISO2 code (e.g. it)")
        parser.add_argument("--type", required=True, choices=["page", "navigation", "author"], help="Entity type")
        parser.add_argument("--source", default=None, help="Source language (defaults to channel default)")
        parser.add_argument("--provider", default=None, help="Provider override (deepl or gemini)")
        parser.add_argument("--content-type-slug", default=None, help="Filter by ContentType slug (e.g. blog-post)")
        parser.add_argument("--estimate-only", action="store_true", help="Estimate cost without translating")
        parser.add_argument("--force", action="store_true", help="Overwrite existing translations")
        parser.add_argument("--publish", action="store_true", help="Auto-publish translated drafts")

    def handle(self, *args, **options):
        result = translator.translate_bulk(
            channel_idx=options["channel"],
            entity_type=options["type"],
            target_languages=[options["target"]],
            source_language=options["source"],
            provider=options["provider"],
            content_type_slug=options["content_type_slug"],
            dry_run=options["estimate_only"],
            force=options["force"],
            publish=options["publish"],
        )

        data = result.model_dump()
        if options["estimate_only"]:
            self.stdout.write(self.style.SUCCESS(f"\nEstimate for {options['type']} → {options['target']}:"))
            self.stdout.write(f"  Items: {data.get('estimated_items', 0)}")
            self.stdout.write(f"  Characters: {data.get('total_chars', 0)}")
            self.stdout.write(f"  Cost: ${data.get('estimated_cost_usd', '0')}")
            if data.get("per_draft"):
                self.stdout.write("\n  Drafts:")
                for d in data["per_draft"]:
                    self.stdout.write(f"    {d['draft_name']}: {d['items']} items, {d['chars']} chars")
        else:
            job_ids = data.get("job_ids", [])
            self.stdout.write(self.style.SUCCESS(f"\nCreated {len(job_ids)} translation job(s)"))
            for jid in job_ids:
                self.stdout.write(f"  {jid}")
