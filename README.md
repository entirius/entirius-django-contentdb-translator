# entirius-django-contentdb-translator

A Django module that translates the CMS content of Entirius, the open-source modular ecommerce platform.
It extracts translatable text from ContentDB pages, navigation and authors, sends it to an AI toolbox service
over HTTP and creates a new draft per language.

[![PyPI](https://img.shields.io/pypi/v/entirius-django-contentdb-translator.svg)](https://pypi.org/project/entirius-django-contentdb-translator/)
[![Python](https://img.shields.io/pypi/pyversions/entirius-django-contentdb-translator.svg)](https://pypi.org/project/entirius-django-contentdb-translator/)
[![License: MPL-2.0](https://img.shields.io/badge/license-MPL--2.0-blue.svg)](https://github.com/entirius/entirius-django-contentdb-translator/blob/develop/LICENSE)

## What it does

- Translates pages (tiles, SEO meta, extensions, routes), navigation and author profiles.
- Creates each language version as a separate draft, with channels, authors, routes and content sets copied.
- Estimates the cost first: every translate call accepts `dry_run` and returns an estimate without translating.
- Runs translation as toolbox jobs that a Celery task polls and applies when they finish.
- Records which draft is the translation of which (`TranslationLink`), and can publish the result at once.
- Exposes an admin API (JWT, Pydantic schemas, OpenAPI) and the commands `translate_content` and
  `backfill_translation_links`.

## Installation

```shell
uv add entirius-django-contentdb-translator
pip install entirius-django-contentdb-translator
```

```python
INSTALLED_APPS = [
    # ...
    "django_contentdb",
    "django_regional",
    "django_utils",
    "django_utils_translator",
    "django_contentdb_translator",
]

# main/urls.py
urlpatterns.append(path("", include("django_contentdb_translator.urls")))
```

The module needs a reachable AI toolbox service, configured through `AI_TOOLBOX_BASE_URL` and
`AI_TOOLBOX_API_KEY` of `entirius-django-utils`; the channel idx of a call is sent as the toolbox channel. The
toolbox itself is not part of this package. Settings reference:
https://github.com/entirius/entirius-django-utils/blob/develop/docs/toolbox-client.md

## Quick start

```python
from django_contentdb_translator.services.translator import translate_draft

estimate = translate_draft(
    channel_idx="my-channel",
    draft_uid="<draft uid>",
    target_languages=["it"],
    dry_run=True,
)
```

With `dry_run=True` the call returns a cost estimate; without it a toolbox job is created and applied by the
Celery task. The admin API is mounted under `api/contentdb-translator/v2/admin/<shop_idx>/`. The same
orchestrator backs `manage.py translate_content`.

## Requirements

- Python 3.11 or newer, Django 5.0 or newer.
- PostgreSQL (through `entirius-django-contentdb`) and a Celery worker.
- A reachable AI toolbox service (`AI_TOOLBOX_*` settings).
- Entirius packages pulled in: `entirius-django-contentdb`, `entirius-django-regional`, `entirius-django-utils`,
  `entirius-django-utils-translator`.

## Documentation

- Module docs: https://github.com/entirius/entirius-django-contentdb-translator/tree/develop/docs
- Entirius documentation: https://docs.entirius.com/
- Changelog: https://github.com/entirius/entirius-django-contentdb-translator/blob/develop/CHANGELOG.md

## Part of Entirius

This module runs inside the Entirius backend service (Volkanos) next to the ContentDB module it translates.

- Backend service: https://github.com/entirius/entirius-service-volkanos
- Docker harness: https://github.com/entirius/entirius-zeno
- Sibling modules: https://github.com/entirius/entirius-django-contentdb, https://github.com/entirius/entirius-django-utils-translator,
  https://github.com/entirius/entirius-django-pim-translator

## Development

```shell
make install     # sync dependencies (uv, incl. extras)
make check       # lint + format check (ruff)
make test        # test suite (pytest + pytest-django)
```

Development and agent instructions: https://github.com/entirius/entirius-django-contentdb-translator/blob/develop/AGENTS.md

## License

Mozilla Public License 2.0 (MPL-2.0) — see https://github.com/entirius/entirius-django-contentdb-translator/blob/develop/LICENSE.
