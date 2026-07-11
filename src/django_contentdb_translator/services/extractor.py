# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Extract translatable text from ContentDB JSON structures.

Walks Content JSON (tiles/sections), Meta JSON, Extension JSON, and Navigation JSON.
Returns a flat list of {key, text} items ready for the AI toolbox.

Keys encode the JSON path for the applicator to reconstruct the translated JSON:
  tile.<uuid>.title
  tile.<uuid>.description
  tile.<uuid>.btn.<index>.label
  section.<uuid>.title
  section.<uuid>.description
  section.<uuid>.btn.<index>.label
  meta.title
  ext.title
  ext.btn.<index>.label
  nav.<item-id>.label
  nav.<item-id>.col.<col-id>.heading
  nav.<item-id>.col.<col-id>.link.<link-id>.label
  nav.<item-id>.col.<col-id>.caption
  nav.<item-id>.col.<col-id>.button_label
  nav.<item-id>.col.<col-id>.alt_text
  route.<route-id>.url
  author.<uid>.role
  author.<uid>.description
  author.<uid>.tag
"""

from __future__ import annotations

import logging

from django_contentdb_translator.settings import (
    TRANSLATABLE_EXTENSION_FIELDS,
    TRANSLATABLE_META_FIELDS,
    TRANSLATABLE_NAV_COLUMN_FIELDS,
    TRANSLATABLE_NAV_ITEM_FIELDS,
    TRANSLATABLE_NAV_LINK_FIELDS,
    TRANSLATABLE_SECTION_BUTTON_FIELD,
    TRANSLATABLE_SECTION_FIELDS,
    TRANSLATABLE_TILE_BUTTON_FIELD,
    TRANSLATABLE_TILE_FIELDS,
)

logger = logging.getLogger("process")


def extract_page_items(
    content_json: dict,
    meta_json: dict | None,
    extension_json: dict | None,
    draft_name: str | None = None,
    category_name: str | None = None,
    category_url_key: str | None = None,
) -> list[dict]:
    """Extract translatable items from a page Content record.

    Returns list of {"key": "path", "text": "value"} for all non-empty translatable fields.
    One page = one batch — keeps full context for the provider.
    """
    items: list[dict] = []
    if draft_name and draft_name.strip():
        items.append({"key": "draft.name", "text": draft_name})
    if category_name and category_name.strip():
        items.append({"key": "category.name", "text": category_name})
    if category_url_key and category_url_key.strip():
        items.append({"key": "category.url_key", "text": category_url_key})
    items.extend(_extract_tiles(content_json))
    items.extend(_extract_sections(content_json))
    items.extend(_extract_meta(meta_json))
    items.extend(_extract_extension(extension_json))
    return items


def extract_navigation_items(content_json: dict) -> list[dict]:
    """Extract translatable items from navigation (header/footer) Content JSON."""
    items: list[dict] = []
    for nav_item in content_json.get("items", []):
        item_id = nav_item.get("id", "")
        for field in TRANSLATABLE_NAV_ITEM_FIELDS:
            text = nav_item.get(field, "")
            if text and isinstance(text, str) and text.strip():
                items.append({"key": f"nav.{item_id}.{field}", "text": text})

        for column in nav_item.get("columns", []):
            col_id = column.get("id", "")
            for field in TRANSLATABLE_NAV_COLUMN_FIELDS:
                text = column.get(field, "")
                if text and isinstance(text, str) and text.strip():
                    items.append({"key": f"nav.{item_id}.col.{col_id}.{field}", "text": text})

            for link in column.get("links", []):
                link_id = link.get("id", "")
                for field in TRANSLATABLE_NAV_LINK_FIELDS:
                    text = link.get(field, "")
                    if text and isinstance(text, str) and text.strip():
                        items.append({"key": f"nav.{item_id}.col.{col_id}.link.{link_id}.{field}", "text": text})

    return items


def extract_route_items(routes: list[dict]) -> list[dict]:
    """Extract translatable route URLs.

    Args:
        routes: list of {"id": route_pk, "url": "about-us"} dicts
    """
    return [
        {"key": f"route.{r['id']}.url", "text": r["url"]}
        for r in routes
        if r.get("url") and isinstance(r["url"], str) and r["url"].strip()
    ]


def extract_author_items(authors: list[dict], source_language: str) -> list[dict]:
    """Extract translatable author fields from t9n dicts.

    Args:
        authors: list of {"uid": "...", "role_t9n": {...}, "description_t9n": {...}, "tag_t9n": {...}}
        source_language: ISO2 code to extract from t9n dicts
    """
    items: list[dict] = []
    for author in authors:
        uid = str(author["uid"])
        for field in ("role", "description", "tag"):
            t9n = author.get(f"{field}_t9n", {}) or {}
            text = t9n.get(source_language, "")
            if text and isinstance(text, str) and text.strip():
                items.append({"key": f"author.{uid}.{field}", "text": text})
    return items


# --- Internal helpers ---


def _extract_tiles(content_json: dict) -> list[dict]:
    """Walk tiles dict and extract translatable fields."""
    items: list[dict] = []
    tiles = content_json.get("tiles", {})
    if not isinstance(tiles, dict):
        return items

    for tile_uuid, tile_data in tiles.items():
        if not isinstance(tile_data, dict):
            continue
        for field in TRANSLATABLE_TILE_FIELDS:
            text = tile_data.get(field, "")
            if text and isinstance(text, str) and text.strip():
                items.append({"key": f"tile.{tile_uuid}.{field}", "text": text})

        # Button labels
        for i, button in enumerate(tile_data.get("custom_buttons", []) or []):
            if not isinstance(button, dict):
                continue
            label = button.get(TRANSLATABLE_TILE_BUTTON_FIELD, "")
            if label and isinstance(label, str) and label.strip():
                items.append({"key": f"tile.{tile_uuid}.btn.{i}.{TRANSLATABLE_TILE_BUTTON_FIELD}", "text": label})

    return items


def _extract_sections(content_json: dict) -> list[dict]:
    """Walk sections dict and extract translatable fields."""
    items: list[dict] = []
    sections = content_json.get("sections", {})
    if not isinstance(sections, dict):
        return items

    for section_uuid, section_data in sections.items():
        if not isinstance(section_data, dict):
            continue
        for field in TRANSLATABLE_SECTION_FIELDS:
            text = section_data.get(field, "")
            if text and isinstance(text, str) and text.strip():
                items.append({"key": f"section.{section_uuid}.{field}", "text": text})

        for i, button in enumerate(section_data.get("custom_buttons", []) or []):
            if not isinstance(button, dict):
                continue
            label = button.get(TRANSLATABLE_SECTION_BUTTON_FIELD, "")
            if label and isinstance(label, str) and label.strip():
                items.append(
                    {
                        "key": f"section.{section_uuid}.btn.{i}.{TRANSLATABLE_SECTION_BUTTON_FIELD}",
                        "text": label,
                    }
                )

    return items


def _extract_meta(meta_json: dict | None) -> list[dict]:
    """Extract translatable fields from meta JSON (SEO)."""
    if not meta_json or not isinstance(meta_json, dict):
        return []
    items: list[dict] = []
    for field in TRANSLATABLE_META_FIELDS:
        text = meta_json.get(field, "")
        if text and isinstance(text, str) and text.strip():
            items.append({"key": f"meta.{field}", "text": text})
    return items


def _extract_extension(extension_json: dict | None) -> list[dict]:
    """Extract translatable fields from extension JSON (blog header)."""
    if not extension_json or not isinstance(extension_json, dict):
        return []
    items: list[dict] = []
    for field in TRANSLATABLE_EXTENSION_FIELDS:
        text = extension_json.get(field, "")
        if text and isinstance(text, str) and text.strip():
            items.append({"key": f"ext.{field}", "text": text})

    # Extension custom_buttons
    for i, button in enumerate(extension_json.get("custom_buttons", []) or []):
        if not isinstance(button, dict):
            continue
        label = button.get("label", "")
        if label and isinstance(label, str) and label.strip():
            items.append({"key": f"ext.btn.{i}.label", "text": label})

    return items
