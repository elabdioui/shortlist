# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Candidate, LLM evaluation, evidence verification, and human decision schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shortlist.schemas.common import (
    CriterionVerdict,
    ExtractionStatus,
    HumanDecision,
    Recommendation,
)


class LLMOutputCriterion(BaseModel):
    """Single criterion verdict returned by the LLM."""

    id: str
    verdict: CriterionVerdict
    quote: str = ""
    explanation: str = ""


class LLMOutputSchema(BaseModel):
    """Strict JSON schema expected from the LLM evaluation call."""

    criteria: list[LLMOutputCriterion]
    relevant_experience_years: float | None = Field(default=None, ge=0.0)
    current_role: str | None = None
    highest_education: str | None = None
    languages: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    watchouts: list[str] = Field(default_factory=list)


class QuoteSpan(BaseModel):
    """Character offset span of a verified quote in extracted CV text."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    match_score: float = Field(ge=0.0, le=100.0)


class VerifiedCriterionResult(BaseModel):
    """Criterion verdict after deterministic quote verification."""

    id: str
    verdict: CriterionVerdict
    original_verdict: CriterionVerdict
    quote: str
    explanation: str
    verified: bool
    span: QuoteSpan | None = None


class EvaluationResult(BaseModel):
    """Stored evaluation for a candidate against a frozen criteria set."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    criteria_set_version: int
    model_used: str
    fallback_used: bool = False
    verdicts: list[VerifiedCriterionResult]
    score: float = Field(ge=0.0, le=100.0)
    recommendation: Recommendation
    formula_version: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    created_at: datetime


class DecisionCreate(BaseModel):
    """Human decision and optional verdict overrides for a candidate."""

    decision: HumanDecision
    note: str | None = Field(default=None, max_length=2000)
    verdict_overrides: dict[str, CriterionVerdict] = Field(default_factory=dict)


class DecisionResponse(BaseModel):
    """Persisted human decision record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    user_id: str
    decision: HumanDecision
    note: str | None
    verdict_overrides: dict[str, CriterionVerdict]
    decided_at: datetime


class CandidateSummary(BaseModel):
    """Candidate row in job ranking tables."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    filename: str
    extraction_status: ExtractionStatus
    score: float | None = None
    recommendation: Recommendation | None = None
    decision: HumanDecision = HumanDecision.PENDING
    mandatory_met: int = 0
    mandatory_total: int = 0
    model_used: str | None = None
    fallback_used: bool = False
    # Analysis lifecycle, so the UI can explain rows without a score.
    # done | queued | running | failed | not_analyzed
    analysis_status: str = "not_analyzed"
    # rate_limit | overloaded | timeout | auth | no_keys | all_failed | unknown
    analysis_error_code: str | None = None
    # Criteria grid version the displayed score was computed with, and whether
    # the grid was edited since (the score is then outdated).
    criteria_set_version: int | None = None
    is_stale: bool = False


class CandidateDetail(BaseModel):
    """Full candidate view including anonymized text, evaluation, and decision."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    filename: str
    sha256: str
    extraction_status: ExtractionStatus
    anonymized_text: str | None
    evaluation: EvaluationResult | None = None
    decision: DecisionResponse | None = None
    created_at: datetime
