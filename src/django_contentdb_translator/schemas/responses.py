# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pydantic response schemas for django-contentdb-translator API."""

from decimal import Decimal

from django_utils_translator.schemas.responses import BulkTranslateEstimateResponse, LanguageCostEstimate
from pydantic import BaseModel, Field


class DraftBreakdown(BaseModel):
    """Per-draft cost breakdown in bulk estimate."""

    draft_uid: str = Field(description="Draft UUID", examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"])
    draft_name: str = Field(description="Draft name", examples=["About Us"])
    items: int = Field(description="Number of translatable text items", examples=[12])
    chars: int = Field(description="Total characters", examples=[1450])
    routes: list[str] = Field(default_factory=list, description="Route URLs", examples=[["about-us", "contact"]])


class ContentBulkEstimateResponse(BulkTranslateEstimateResponse):
    """Extended estimate with per-draft breakdown."""

    per_draft: list[DraftBreakdown] = Field(default_factory=list, description="Per-draft cost breakdown")
    skipped_drafts: int = Field(default=0, description="Drafts skipped (already translated, force=False)", examples=[3])


class TranslateDraftResponse(BaseModel):
    """Response for single draft translation."""

    draft_uid: str = Field(description="Source draft UUID", examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"])
    draft_name: str = Field(description="Source draft name", examples=["About Us"])
    dry_run: bool = Field(description="True if estimate only", examples=[True])
    items: int = Field(description="Number of translatable items", examples=[12])
    total_chars: int = Field(description="Total characters", examples=[1450])
    estimated_cost_usd: Decimal | None = Field(description="Estimated cost in USD", examples=["0.42"])
    target_languages: list[str] = Field(description="Target languages", examples=[["de", "fr"]])
    per_language: list[LanguageCostEstimate] = Field(default_factory=list, description="Per-language cost breakdown")
    existing_translations: list[str] = Field(
        default_factory=list, description="Languages already translated", examples=[["de"]]
    )
    missing_translations: list[str] = Field(
        default_factory=list, description="Languages not yet translated", examples=[["fr"]]
    )
    job_ids: list[str] = Field(
        default_factory=list, description="Job UUIDs (when dry_run=False)", examples=[["job-uuid-1"]]
    )
