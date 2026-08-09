---
title: ContentDB Translator
description: AI translation bridge for ContentDB — clones drafts with translated content via AI Toolbox.
---

ContentDB AI translation bridge. Extracts translatable text from ContentDB JSON structures (tiles, meta, extensions, navigation, routes, authors), sends it to the remote `entirius-ai-toolbox` via HTTP, and creates new Drafts with translated content. Zero local Django models — the toolbox is the single source of truth for jobs, costs, and usage.

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
└── management/commands/
    └── translate_content.py  # CLI bulk translation
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
| `force` | Overwrite existing draft in target language (default: skip) |
| `publish` | Auto-publish the translated draft after creation |
| `entity_type` | Bulk only: `page`, `navigation`, or `author` |

## Entity Types

| Type | What Gets Extracted | Apply Strategy |
|------|-------------------|----------------|
| `page` | Tile fields (title, description, buttons), Meta (SEO), Extension (blog header), Routes | Clone Draft with translated JSON |
| `navigation` | Nav items (label), columns (heading, caption, button_label, alt_text), links (label) | Clone Draft with translated navigation JSON |
| `author` | t9n dicts (role, description, tag) | Update Author t9n fields in place |

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

API keys are generated in the AI Toolbox admin — see its configuration guide.

## Key Design Decisions

- **Zero models** — no migrations, no local DB tables. All tracking lives in the AI toolbox.
- **Clone, not update** — each language version is a separate Draft. The applicator deep-copies source JSON and creates a new Content + Draft record.
- **`force` flag** — when true, deletes existing target-language drafts for the same routes before creating new ones. Without force, existing translations are silently skipped.
- **Route translation** — route URLs are translated alongside content. Translated drafts get new Route records with translated slugs.
- **HTML sanitization** — `nh3.clean()` (via `django-utils-translator`) on all translated text before writing to ContentDB.
- **Celery polling** — `poll_and_apply_content_job` checks the toolbox every 30s for job completion (max 120 retries = 1 hour).
- **Author path** — authors use t9n JSON fields updated in place (`select_for_update()`), not Draft cloning.

## Management Commands

```bash
# Bulk translate pages to Italian
python manage.py translate_content --channel default-europe --target it --type page

# Cost estimate only
python manage.py translate_content --channel default-europe --target de --type page --estimate-only

# Force overwrite + auto-publish
python manage.py translate_content --channel default-europe --target fr --type navigation --force --publish
```
