# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pydantic request schemas for django-contentdb-translator API."""

from typing import Literal

from django_utils_translator.schemas.requests import BaseTranslateRequest
from pydantic import Field


class TranslateDraftRequest(BaseTranslateRequest):
    """Translate a single draft to target languages."""

    force: bool = Field(default=False, description="Overwrite existing draft in target language.")
    publish: bool = Field(default=False, description="Auto-publish the translated draft.")


class BulkTranslateRequest(BaseTranslateRequest):
    """Bulk translate all content of a type in a channel."""

    entity_type: Literal["page", "navigation", "author"] = Field(
        description="Entity type to translate.", examples=["page"]
    )
    content_type_slug: str | None = Field(
        default=None, description="Filter by ContentType slug (e.g. 'blog-post'). Pages only.", examples=["blog-post"]
    )
    force: bool = Field(default=False, description="Overwrite existing translations.")
    publish: bool = Field(default=False, description="Auto-publish translated drafts.")
