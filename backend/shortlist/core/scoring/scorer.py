# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deterministic weighted scoring and recommendation engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from shortlist.schemas.candidates import VerifiedCriterionResult
from shortlist.schemas.common import CriterionType, CriterionVerdict, Recommendation
from shortlist.schemas.jobs import CriterionItem

FORMULA_VERSION = "v1"

DEFAULT_INTERVIEW_THRESHOLD = 70.0
DEFAULT_REVIEW_THRESHOLD = 45.0

VERDICT_VALUES: dict[CriterionVerdict, float] = {
    CriterionVerdict.YES: 1.0,
    CriterionVerdict.PARTIAL: 0.5,
    CriterionVerdict.NO: 0.0,
    CriterionVerdict.NOT_FOUND: 0.0,
    CriterionVerdict.UNPROVEN: 0.0,
}


@dataclass(frozen=True, slots=True)
class ScoringResult:
    """Deterministic score and recommendation computed from verified verdicts."""

    score: float
    recommendation: Recommendation
    formula_version: str
    mandatory_met: int
    mandatory_total: int


def compute_score(
    criteria: Sequence[CriterionItem],
    verdicts: Sequence[VerifiedCriterionResult],
) -> float:
    """Compute weighted percentage score: 100 * sum(w_i * v_i) / sum(w_i)."""
    if not criteria:
        return 0.0

    verdict_by_id = {v.id: v.verdict for v in verdicts}
    total_weight = sum(c.weight for c in criteria)
    if total_weight <= 0:
        return 0.0

    weighted_sum = 0.0
    for criterion in criteria:
        verdict = verdict_by_id.get(criterion.id, CriterionVerdict.NOT_FOUND)
        weighted_sum += criterion.weight * VERDICT_VALUES[verdict]

    return round(100.0 * weighted_sum / total_weight, 2)


def compute_recommendation(
    score: float,
    criteria: Sequence[CriterionItem],
    verdicts: Sequence[VerifiedCriterionResult],
    *,
    interview_threshold: float = DEFAULT_INTERVIEW_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    extraction_failed: bool = False,
    invalid_json: bool = False,
    hidden_text_detected: bool = False,
) -> Recommendation:
    """Derive deterministic recommendation from score, mandatory verdicts, and safety flags."""
    if extraction_failed or invalid_json or hidden_text_detected:
        return Recommendation.MANUAL_REVIEW

    verdict_by_id = {v.id: v.verdict for v in verdicts}
    mandatory_verdicts = [
        verdict_by_id.get(c.id, CriterionVerdict.NOT_FOUND)
        for c in criteria
        if c.type == CriterionType.MANDATORY
    ]

    if any(v == CriterionVerdict.NO for v in mandatory_verdicts):
        return Recommendation.NOT_RETAINED

    if score < review_threshold:
        return Recommendation.NOT_RETAINED

    if any(
        v in (CriterionVerdict.PARTIAL, CriterionVerdict.NOT_FOUND, CriterionVerdict.UNPROVEN)
        for v in mandatory_verdicts
    ):
        return Recommendation.REVIEW

    if score < interview_threshold:
        return Recommendation.REVIEW

    return Recommendation.INTERVIEW


def score_candidate(
    criteria: Sequence[CriterionItem],
    verdicts: Sequence[VerifiedCriterionResult],
    *,
    interview_threshold: float = DEFAULT_INTERVIEW_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    extraction_failed: bool = False,
    invalid_json: bool = False,
    hidden_text_detected: bool = False,
) -> ScoringResult:
    """Compute score, recommendation, mandatory counts, and formula version."""
    score = compute_score(criteria, verdicts)
    recommendation = compute_recommendation(
        score,
        criteria,
        verdicts,
        interview_threshold=interview_threshold,
        review_threshold=review_threshold,
        extraction_failed=extraction_failed,
        invalid_json=invalid_json,
        hidden_text_detected=hidden_text_detected,
    )

    verdict_by_id = {v.id: v.verdict for v in verdicts}
    mandatory_criteria = [c for c in criteria if c.type == CriterionType.MANDATORY]
    mandatory_met = sum(
        1 for c in mandatory_criteria if verdict_by_id.get(c.id) == CriterionVerdict.YES
    )

    return ScoringResult(
        score=score,
        recommendation=recommendation,
        formula_version=FORMULA_VERSION,
        mandatory_met=mandatory_met,
        mandatory_total=len(mandatory_criteria),
    )
