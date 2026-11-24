# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""API-specific request and response schemas for Phase 3 endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shortlist.schemas.candidates import CandidateSummary
from shortlist.schemas.common import ExtractionStatus, UserRole
from shortlist.schemas.jobs import CriterionItem
from shortlist.schemas.users import UserResponse


class SetupStatusResponse(BaseModel):
    """Whether the application requires initial admin account creation."""

    needs_setup: bool


class AuthSetupRequest(BaseModel):
    """Payload to create the initial admin user on first launch."""

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    locale: str = Field(default="fr", pattern="^(fr|en|ar)$")


class AuthSessionResponse(BaseModel):
    """Authenticated user session with CSRF token."""

    user: UserResponse
    csrf_token: str


class UserUpdate(BaseModel):
    """Admin update for user role or locale."""

    role: UserRole | None = None
    locale: str | None = Field(default=None, pattern="^(fr|en|ar)$")


class CriteriaGenerateResponse(BaseModel):
    """Generated criteria grid and any rejected discriminatory items."""

    criteria: list[CriterionItem]
    rejected_discriminatory: list[str] = Field(default_factory=list)
    model_used: str


class CandidateUploadResponse(BaseModel):
    """Result of uploading one or more CV files or a ZIP archive."""

    uploaded: list[CandidateSummary]
    duplicates_skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AnonymizedPreviewResponse(BaseModel):
    """Preview of the anonymized CV text that will be sent to an external LLM."""

    candidate_id: str
    filename: str
    anonymized_text: str
    extraction_status: ExtractionStatus
    sends_external_data: bool


class PrivacySettingsResponse(BaseModel):
    """Current global privacy and data retention settings."""

    model_config = ConfigDict(from_attributes=True)

    anonymization_level: str
    retention_days: int
    auto_purge_enabled: bool
    last_purge_at: datetime | None


class PrivacySettingsUpdate(BaseModel):
    """Partial update for global privacy settings."""

    anonymization_level: str | None = Field(default=None, pattern="^(max|standard)$")
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    auto_purge_enabled: bool | None = None


class PurgeResultResponse(BaseModel):
    """Summary of purged expired jobs, candidates, and stored files."""

    deleted_jobs: int
    deleted_candidates: int
    deleted_files: int


class AuditLogResponse(BaseModel):
    """Audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict[str, Any]
    created_at: datetime


class UsageLogResponse(BaseModel):
    """Daily token and cost ledger entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    api_key_id: str | None
    usage_date: str
    requests: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class RunStartRequest(BaseModel):
    """Optional parameters when starting or resuming an analysis run."""

    resume_failed: bool = False
