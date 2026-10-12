---
title: ContentDB Translator
description: AI translation bridge for ContentDB — clones drafts with translated content via AI Toolbox.
---

ContentDB AI translation bridge. Extracts translatable text from ContentDB JSON structures (tiles, meta, extensions, navigation, routes, authors), sends it to the remote AI toolbox via HTTP, and creates new Drafts with translated content. One local Django model (`TranslationLink`) — the toolbox is the single source of truth for jobs, costs, and usage.

**Tech:** Python >=3.11 · Django >=5.0 · DRF · Pydantic · Celery · django-contentdb · django-utils-translator

## Architecture

```
django-contentdb-translator
├── services/
│   ├── extractor.py        # Walk JSON structures → flat [{key, text}] items
│   ├── applicator.py       # Deep-copy + translate JSON → new Content → new Draft
│   └── translator.py       # Orchestrator: extract → toolbox → apply
├── schemas/                # Request/response Pydantic models
├── api/                    # DRF ViewSets + URL patterns
├── tasks/
│   └── apply_job.py        # Celery: poll toolbox → apply on completion
├── models/
│   └── translation_link.py # TranslationLink (source draft → translated draft per language)
└── management/commands/
    ├── translate_content.py            # CLI bulk translation
    └── backfill_translation_links.py   # TranslationLink rows for existing translations
```

Layer rule: `API → translator (orchestrator) → extractor/applicator → ContentDB models`.

## Request Flow

```
CMS → POST /drafts/{uid}/translate/ (or /bulk/translate/)
  → extractor: walk Content JSON, Meta, Extension, Navigation, Routes
  → ToolboxClient: POST /api/ai-translator/v2/admin/{channel_idx}/estimate/
  → (if not estimate-only) ToolboxClient: POST /api/ai-translator/v2/admin/{channel_idx}/jobs/
  → Celery poll: GET /api/ai-translator/v2/admin/{channel_idx}/jobs/{id}/
  → On completion: GET /api/ai-translator/v2/admin/{channel_idx}/jobs/{id}/results/
  → applicator: deep-copy JSON → new Content → new Draft
  → Copy channels, authors, routes, ContentSet membership
  → Optionally auto-publish (create Published record)
```

## Data Model

One model: `TranslationLink` (`contentdb_translator_link` table) — maps `source_draft_id` →
`translated_draft_id` per target language (integer IDs by design: zero coupling to ContentDB models).
Job tracking lives in the AI toolbox. Content is stored via `django_contentdb` models.

## API

All endpoints: JWT + `IsAdminUser`. Prefix: `/api/contentdb-translator/v2/admin/{shop_idx}/`

| Method | Path | Summary |
|--------|------|---------|
| POST | `drafts/{uid}/translate/` | Translate single draft |
| POST | `bulk/translate/` | Bulk translate by entity type (page/navigation/author) |
| GET | `bulk/jobs/` | List jobs (proxied from toolbox) |
| GET | `bulk/jobs/{pk}/` | Job status (proxied from toolbox) |

All POST endpoints accept `dry_run: true` for cost estimation without calling the provider.

### Key Parameters

| Parameter | Effect |
|-----------|--------|
| `dry_run` | Returns a cost estimate without calling the provider |
| `force` | Overwrite existing draft in target language (default: skip) |
| `publish` | Auto-publish the translated draft after creation |
| `entity_type` | Bulk only: `page`, `navigation`, or `author` |

## Entity Types

| Type | What Gets Extracted | Apply Strategy |
|------|-------------------|----------------|
| `page` | Tile fields (title, description, buttons), Meta (SEO), Extension (blog header), Routes | Clone Draft with translated JSON; copy channels, authors, routes and ContentSet membership |
| `navigation` | Nav items (label), columns (heading, caption, button_label, alt_text), links (label) | Clone Draft with translated navigation JSON |
| `author` | t9n dicts (role, description, tag) | Update Author t9n fields in place |

## Key Path Encoding

Extractor encodes JSON paths as dot-separated keys for the applicator to reconstruct:

```
tile.<uuid>.title           → Content JSON tile field
meta.title                  → Meta JSON SEO field
ext.btn.<index>.label       → Extension JSON button
nav.<item-id>.label         → Navigation item
route.<route-id>.url        → Route URL slug
author.<uid>.role           → Author t9n field
```

## Configuration

ContentDB Translator uses the shared toolbox settings from `django-utils-translator`:

```python
# settings_local.py
AI_TOOLBOX_BASE_URL = "http://ai-toolbox:8001"   # required
AI_TOOLBOX_API_KEY = "ent_prod_..."               # required
AI_TOOLBOX_TIMEOUT = 60                           # optional (default: 60)
AI_TOOLBOX_MAX_RETRIES = 3                        # optional (default: 3)
```

`AI_TOOLBOX_BASE_URL` and `AI_TOOLBOX_API_KEY` are required — the module fails loud if either is missing.

With `AI_TOOLBOX_ENABLED = False` the toolbox is switched off on purpose: every endpoint answers 503 `AI_TOOLBOX_DISABLED` and `poll_and_apply_content_job` logs a warning and returns without polling.

API keys are generated in the AI Toolbox admin — see its configuration guide.

## Key Design Decisions

- **One model** — `TranslationLink` maps a source draft to its translated draft per language. Job tracking lives in the AI toolbox.
- **Clone, not update** — each language version is a separate Draft. The applicator deep-copies source JSON and creates a new Content + Draft record.
- **`force` flag** — when true, deletes existing target-language drafts for the same routes before creating new ones. Without force, existing translations are silently skipped.
- **Route translation** — route URLs are translated alongside content. Translated drafts get new Route records with translated slugs.
- **HTML sanitization** — `nh3.clean()` (via `django-utils-translator`) on all translated text before writing to ContentDB.
- **Celery polling** — `poll_and_apply_content_job` checks the toolbox every 30s for job completion (max 120 retries = 1 hour).
- **Author path** — authors use t9n JSON fields updated in place (`select_for_update()`), not Draft cloning.

See [Management Commands](./commands/) for CLI bulk translation.
