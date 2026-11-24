# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Analysis run and SSE progress event schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shortlist.schemas.common import RunStatus


class AnalysisRunResponse(BaseModel):
    """Status and progress of a batch analysis run."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    status: RunStatus
    processed_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    cumulative_cost_usd: float = Field(ge=0.0)
    error_count: int = Field(ge=0)
    started_at: datetime | None
    finished_at: datetime | None


class RunEvent(BaseModel):
    """Server-Sent Event payload for live run progress."""

    run_id: str
    status: RunStatus
    processed_count: int
    total_count: int
    cumulative_cost_usd: float
    candidate_id: str | None = None
    message: str | None = None
