# django-contentdb-translator

ContentDB AI translation bridge for the Volkanos ecommerce platform — extracts translatable text
from ContentDB JSON structures (tiles, meta, extensions, navigation, routes, authors), sends it to
the remote AI toolbox and clones Drafts with translated content. Each language version is a
separate Draft.

## Installation

```shell
pip install entirius-django-contentdb-translator
```

Add the app to your project:

```python
INSTALLED_APPS = [
    ...
    "django_contentdb_translator",
]
```

Requires `django_contentdb` and `django_utils_translator` in `INSTALLED_APPS`
(both installed automatically as dependencies).

## Development

```shell
make install     # sync dependencies (uv)
make check       # lint + format check (ruff)
make test        # test suite (pytest + pytest-django)
```

Architecture, API and flow reference: [AGENTS.md](AGENTS.md).

## License

Mozilla Public License 2.0 — see [LICENSE](LICENSE).
