# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Smoke test: every public submodule imports cleanly under a configured Django."""

import importlib

import pytest

MODULES = [
    "django_contentdb_translator.apps",
    "django_contentdb_translator.settings",
    "django_contentdb_translator.urls",
    "django_contentdb_translator.models.translation_link",
    "django_contentdb_translator.services.extractor",
    "django_contentdb_translator.services.applicator",
    "django_contentdb_translator.services.translator",
    "django_contentdb_translator.schemas.requests",
    "django_contentdb_translator.schemas.responses",
    "django_contentdb_translator.tasks.apply_job",
    "django_contentdb_translator.api.views",
    "django_contentdb_translator.api.urls",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    importlib.import_module(module)
