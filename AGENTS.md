# AGENTS.md

entirius-django-contentdb-translator (Django app `django_contentdb_translator`) — ContentDB AI translation bridge
of Entirius. Extracts translatable text from ContentDB JSON structures (tiles, meta, extensions, navigation,
routes, authors), sends it to the remote AI toolbox, and clones Drafts with translated content. Each language
version is a separate Draft — that is ContentDB's multi-language model. One Django model (`TranslationLink` —
source→translated draft mapping).

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
- No AI attribution in commits or PR descriptions.

## Architecture

```
src/django_contentdb_translator/
├── api/
│   ├── views.py              # DraftTranslateView, BulkTranslateView, BulkJobViewSet
│   └── urls.py               # URL patterns
├── services/
│   ├── extractor.py          # Walk JSON → flat [{key, text}] items
│   ├── applicator.py         # Deep-copy + translate JSON → new Content → new Draft
│   ├── translator.py         # Orchestrator: extract → toolbox → apply
│   └── jobs.py               # Job list/detail proxy, scoped to the sales channel by job metadata
├── schemas/
│   ├── requests.py           # TranslateDraftRequest, BulkTranslateRequest (extend BaseTranslateRequest)
│   └── responses.py          # TranslateDraftResponse, ContentBulkEstimateResponse, DraftBreakdown
├── tasks/
│   └── apply_job.py          # poll_and_apply_content_job (Celery, 30s poll, 120 retries)
├── management/commands/
│   ├── translate_content.py  # CLI bulk translation
│   └── backfill_translation_links.py  # TranslationLink rows for translations made before the model
├── admin/                    # TranslationLink admin, translate wizard
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

| Topic | Where |
|---|---|
| Data model, endpoints and parameters, entity types, key path encoding, design decisions | `docs/index.md` |
| `translate_content`, `backfill_translation_links` | `docs/commands.md` |
| The `AI_TOOLBOX_*` settings | `django_utils.toolbox` — `docs/toolbox-client.md` of `entirius-django-utils` |
| What changed and why | `CHANGELOG.md` |

## Gotchas

- Every toolbox call uses the instance channel — `ToolboxClient()` (`AI_TOOLBOX_CHANNEL`), never the URL's
  `shop_idx`. The sales channel travels in job `metadata.channel_idx`; `poll_and_apply_content_job` gets it as an
  argument.
- `bulk/jobs/` filters the toolbox page by `metadata.channel_idx` — no `count`; `next`/`previous` are toolbox
  page cursors, so a page can come back short or empty. Another channel's job detail answers 404. Jobs created
  before the switch (on the sales-channel toolbox channel) are not listed; their poll task gets a toolbox 404
  and gives up without retrying.
- Applicator **clones** Drafts rather than updating in place. Each language is a separate Draft — that is how ContentDB stores multilingual content.
- `force=True` deletes existing target-language drafts for the same routes before creating new ones. Without `force`, existing translations are skipped.
- Route URLs are translated too — the translated draft gets new Route records with translated slugs.
- Authors use a different apply path: t9n JSON fields updated in place with `select_for_update()`, not Draft cloning.
- Source language resolution: explicit param > `ContentChannel.default_language` > fallback `"en"`.
- All translated text passes through `nh3.clean()` (via `django-utils-translator.sanitize`) before writing.
- Celery task `poll_and_apply_content_job` polls every 30s with max 120 retries (1 hour timeout).
- ContentSet membership is copied from source to translated draft.
- `AI_TOOLBOX_ENABLED = False` (the switch of `entirius-django-utils`): the endpoints answer 503
  `AI_TOOLBOX_DISABLED`; `poll_and_apply_content_job` logs a warning and returns without polling or raising.
