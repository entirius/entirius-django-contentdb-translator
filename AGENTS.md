# AGENTS.md

ContentDB AI translation bridge — distribution `entirius-django-contentdb-translator`, Django app
`django_contentdb_translator`. Extracts translatable text from ContentDB JSON structures (tiles, meta, extensions, navigation, routes, authors), sends to the remote AI toolbox, and clones Drafts with translated content. Each language version is a separate Draft — that is ContentDB's multi-language model. One Django model (`TranslationLink` — source→translated draft mapping).

**Tech:** Python 3.11+, Django 5, DRF, drf-spectacular, Pydantic v2, Celery,
entirius-django-contentdb, entirius-django-utils-translator.

## Commands

| Command | Meaning |
|---|---|
| `make install` | sync dependencies (uv, incl. extras) |
| `make check` | lint + format-check (ruff) |
| `make fix` | auto-fix lint + format |
| `make test` | test suite (pytest + pytest-django) |

## Conventions

- English only: code, docs, commits, branches, PRs.
- MPL-2.0: every non-trivial source file carries the license header (pre-commit inserts it).
- Toolchain: uv + ruff + hatchling + pytest; all config in `pyproject.toml`; `uv.lock` committed.
- Git flow: `master` (production) + `develop` (integration); changes land via PR; semver tag on `master`.
- Never rename the package / Django app_label `django_contentdb_translator` — it is a schema contract.
- Migrations are part of the public contract — never edit an already released migration.
- Access: areas live on the AppConfig (`access_areas`, `access_route_rules`), every admin view carries
  `access_area`; a new admin route without one fails `tests/test_access_ownership.py`.
- Default: do not commit — git is the user's call.

## Architecture

```
src/django_contentdb_translator/
├── api/
│   ├── views.py              # DraftTranslateView, BulkTranslateView, BulkJobViewSet
│   └── urls.py               # 4 URL patterns
├── services/
│   ├── extractor.py          # Walk JSON → flat [{key, text}] items
│   ├── applicator.py         # Deep-copy + translate JSON → new Content → new Draft
│   └── translator.py         # Orchestrator: extract → toolbox → apply
├── schemas/
│   ├── requests.py           # TranslateDraftRequest, BulkTranslateRequest (extend BaseTranslateRequest)
│   └── responses.py          # TranslateDraftResponse, ContentBulkEstimateResponse, DraftBreakdown
├── tasks/
│   └── apply_job.py          # poll_and_apply_content_job (Celery, 30s poll, 120 retries)
├── management/commands/
│   └── translate_content.py  # CLI bulk translation
├── models/
│   └── translation_link.py   # TranslationLink (source draft → translated draft per language)
├── settings.py               # Translatable field lists (tiles, meta, extension, nav)
└── urls.py                   # Root: /api/contentdb-translator/v2/admin/<shop_idx>/
```

### Dependency Graph

```
django-contentdb-translator
    → django-utils-translator  (ToolboxClient, errors, base schemas, sanitize)
    → django-contentdb         (Draft, Content, Route, Author, ContentChannel)
```

### Request Flow

```
CMS → POST /drafts/{uid}/translate/ (or /bulk/translate/)
  → extractor: walk Content JSON, Meta, Extension, Navigation, Routes
  → ToolboxClient: POST /estimate/ (if dry_run)
  → ToolboxClient: POST /jobs/ (one per target language)
  → Celery poll: GET /jobs/{id}/ every 30s
  → On completion: GET /jobs/{id}/results/
  → applicator: deep-copy JSON → new Content → new Draft → copy channels/authors/routes
  → Optionally: auto-publish (create Published record)
```

## Data Model

One model: `TranslationLink` (`contentdb_translator_link` table) — maps `source_draft_id` →
`translated_draft_id` per target language (integer IDs by design: zero coupling to ContentDB models).
Job tracking lives in the AI toolbox. Content is stored via `django_contentdb` models.

## API Surface

Prefix: `/api/contentdb-translator/v2/admin/{shop_idx}/`

Auth: JWT + `IsAdminUser` on all endpoints.

| Method | Path | Summary |
|--------|------|---------|
| POST | `drafts/{uid}/translate/` | Translate single draft (dry_run for estimate) |
| POST | `bulk/translate/` | Bulk translate by entity type (page/navigation/author) |
| GET | `bulk/jobs/` | List translation jobs (proxied from toolbox) |
| GET | `bulk/jobs/{pk}/` | Get job detail (proxied from toolbox) |

### Key Parameters

| Parameter | Type | Effect |
|-----------|------|--------|
| `dry_run` | bool | Returns cost estimate without calling provider |
| `force` | bool | Overwrite existing draft in target language |
| `publish` | bool | Auto-publish translated draft after creation |
| `entity_type` | str | Bulk: `page`, `navigation`, or `author` |

## Entity Types

| Type | Extractor | Applicator |
|------|-----------|------------|
| `page` | Tiles (title, description, buttons), Meta (SEO), Extension (blog header) | Clone Draft with translated JSON, copy channels/authors/routes/content-sets |
| `navigation` | Nav items (label), columns (heading, caption, button_label, alt_text), links (label) | Clone Draft with translated navigation JSON |
| `author` | t9n dicts (role, description, tag) | Update Author t9n JSON fields in place |

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

## Commands

```bash
# Bulk translate pages to Italian
python manage.py translate_content --channel default-europe --target it --type page

# Estimate cost only
python manage.py translate_content --channel default-europe --target de --type page --estimate-only

# Force overwrite + auto-publish
python manage.py translate_content --channel default-europe --target fr --type navigation --force --publish
```

## Testing

```bash
make install
make test
```

## Gotchas

- Applicator **clones** Drafts rather than updating in place. Each language is a separate Draft — that is how ContentDB stores multilingual content.
- `force=True` deletes existing target-language drafts for the same routes before creating new ones. Without `force`, existing translations are skipped.
- Route URLs are translated too — the translated draft gets new Route records with translated slugs.
- Authors use a different apply path: t9n JSON fields updated in place with `select_for_update()`, not Draft cloning.
- Source language resolution: explicit param > `ContentChannel.default_language` > fallback `"en"`.
- All translated text passes through `nh3.clean()` (via `django-utils-translator.sanitize`) before writing.
- Celery task `poll_and_apply_content_job` polls every 30s with max 120 retries (1 hour timeout).
- ContentSet membership is copied from source to translated draft.
