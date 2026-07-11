# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Module settings for django-contentdb-translator.

Shared toolbox settings (AI_TOOLBOX_*) are in django_utils_translator.settings.
This file contains ContentDB-specific settings only.
"""

# Tile fields that contain translatable text.
TRANSLATABLE_TILE_FIELDS: list[str] = [
    "title",
    "description",
]

# Tile sub-objects with translatable text.
TRANSLATABLE_TILE_BUTTON_FIELD: str = "label"

# Section fields that contain translatable text.
TRANSLATABLE_SECTION_FIELDS: list[str] = [
    "title",
    "description",
]

# Section sub-objects with translatable text (custom_buttons share tile pattern).
TRANSLATABLE_SECTION_BUTTON_FIELD: str = "label"

# Meta JSON fields to translate (SEO).
TRANSLATABLE_META_FIELDS: list[str] = [
    "title",
    "description",
    "og_title",
    "og_description",
]

# Extension JSON fields to translate (blog post header).
TRANSLATABLE_EXTENSION_FIELDS: list[str] = [
    "title",
    "description",
]

# Navigation item fields to translate.
TRANSLATABLE_NAV_ITEM_FIELDS: list[str] = [
    "label",
]

# Navigation column fields to translate.
TRANSLATABLE_NAV_COLUMN_FIELDS: list[str] = [
    "heading",
    "caption",
    "button_label",
    "alt_text",
]

# Navigation link fields to translate.
TRANSLATABLE_NAV_LINK_FIELDS: list[str] = [
    "label",
]
