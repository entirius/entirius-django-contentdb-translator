---
title: Management Commands
description: CLI commands for bulk ContentDB AI translation and for backfilling translation links.
---

## translate_content

Bulk-translate ContentDB entities from the command line.

| Option | Required | Description |
|--------|----------|-------------|
| `--channel` | Yes | Channel idx |
| `--target` | Yes | Target language ISO2 code |
| `--type` | Yes | `page`, `navigation` or `author` |
| `--source` | No | Source language (defaults to the channel default) |
| `--provider` | No | Provider override |
| `--content-type-slug` | No | Filter by ContentType slug |
| `--estimate-only` | No | Estimate cost without translating |
| `--force` | No | Overwrite existing translations |
| `--publish` | No | Auto-publish translated drafts |

### Examples

```bash
# Bulk translate pages to Italian
python manage.py translate_content --channel default-europe --target it --type page

# Estimate cost only
python manage.py translate_content --channel default-europe --target de --type page --estimate-only

# Force overwrite + auto-publish
python manage.py translate_content --channel default-europe --target fr --type navigation --force --publish
```

## backfill_translation_links

Backfills `TranslationLink` records for existing translations. Source drafts are matched to translations by
(name, content type), which works for static pages where the name is preserved across languages. Blog posts
with translated names are skipped: there is no reliable match without explicit tracking.

| Option | Required | Description |
|--------|----------|-------------|
| `--source-language` | No | Source language ISO2 (default: `en`) |
| `--dry-run` | No | Show what would be created without writing |

```bash
python manage.py backfill_translation_links --source-language en --dry-run
```
