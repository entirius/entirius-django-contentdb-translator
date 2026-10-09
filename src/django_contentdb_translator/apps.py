# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.apps import AppConfig


class DjangoContentdbTranslatorConfig(AppConfig):
    name = "django_contentdb_translator"
    label = "django_contentdb_translator"
    verbose_name = "ContentDB AI Translator"
    default_auto_field = "django.db.models.BigAutoField"
    is_volkanos = True
    # Copied 1:1 from entirius-django-access cf538d2 catalogue defaults;
    # the access defaults stay until this module's release.
    access_areas = [
        {"key": "contentdb_translator.translate", "label": "AI translation (content)", "sensitive": ("ai_cost",)},
    ]
    # Every admin view carries its access_area; no route needs a path rule.
    access_route_rules = []
