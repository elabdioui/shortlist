# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deterministic scoring and recommendation package."""

from shortlist.core.scoring.scorer import (
    DEFAULT_INTERVIEW_THRESHOLD,
    DEFAULT_REVIEW_THRESHOLD,
    FORMULA_VERSION,
    VERDICT_VALUES,
    ScoringResult,
    compute_recommendation,
    compute_score,
    score_candidate,
)

__all__ = [
    "DEFAULT_INTERVIEW_THRESHOLD",
    "DEFAULT_REVIEW_THRESHOLD",
    "FORMULA_VERSION",
    "VERDICT_VALUES",
    "ScoringResult",
    "compute_recommendation",
    "compute_score",
    "score_candidate",
]
