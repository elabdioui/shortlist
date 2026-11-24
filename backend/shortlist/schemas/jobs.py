# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Job posting, criteria grid, and cost estimate schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shortlist.schemas.common import CriterionType, JobStatus


class CriterionItem(BaseModel):
    """A single screening criterion in a job's criteria set."""

    id: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    type: CriterionType = CriterionType.MANDATORY
    weight: int = Field(default=3, ge=1, le=5)


class CriteriaSetUpdate(BaseModel):
    """Payload to save/validate a job's criteria grid."""

    criteria: list[CriterionItem] = Field(min_length=1, max_length=20)


class CriteriaSetResponse(BaseModel):
    """Versioned criteria set associated with a job."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    version: int
    criteria: list[CriterionItem]
    frozen_at: datetime | None


class JobCreate(BaseModel):
    """Payload to create a new job posting."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    profile_id: str | None = None
    interview_threshold: float = Field(default=70.0, ge=0.0, le=100.0)
    review_threshold: float = Field(default=45.0, ge=0.0, le=100.0)
    max_budget_usd: float | None = Field(default=None, ge=0.0)


class JobUpdate(BaseModel):
    """Partial update for an existing job posting."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    profile_id: str | None = None
    interview_threshold: float | None = Field(default=None, ge=0.0, le=100.0)
    review_threshold: float | None = Field(default=None, ge=0.0, le=100.0)
    max_budget_usd: float | None = Field(default=None, ge=0.0)
    status: JobStatus | None = None


class JobResponse(BaseModel):
    """Public job representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    profile_id: str | None
    interview_threshold: float
    review_threshold: float
    max_budget_usd: float | None
    status: JobStatus
    created_at: datetime
    updated_at: datetime


class EstimateResponse(BaseModel):
    """Pre-run cost and duration estimate for a job."""

    job_id: str
    candidate_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0.0)
    estimated_duration_seconds: int = Field(ge=0)
    sends_external_data: bool
    provider_label: str | None = None
