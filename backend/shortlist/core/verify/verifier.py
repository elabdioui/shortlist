# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deterministic evidence verification against extracted CV text."""

from __future__ import annotations

from rapidfuzz import fuzz

from shortlist.schemas.candidates import (
    LLMOutputCriterion,
    LLMOutputSchema,
    QuoteSpan,
    VerifiedCriterionResult,
)
from shortlist.schemas.common import CriterionVerdict

DEFAULT_MATCH_THRESHOLD = 90.0


def verify_quote(
    quote: str,
    cv_text: str,
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> QuoteSpan | None:
    """Locate a quote in CV text using rapidfuzz partial_ratio >= threshold.

    Returns QuoteSpan(start, end, match_score) when found, or None otherwise.
    """
    cleaned_quote = quote.strip()
    if not cleaned_quote or not cv_text:
        return None

    alignment = fuzz.partial_ratio_alignment(
        cleaned_quote,
        cv_text,
        score_cutoff=threshold,
    )

    if alignment is None:
        lowered_cv = cv_text.lower()
        lowered_quote = cleaned_quote.lower()
        if len(lowered_cv) == len(cv_text):
            alignment = fuzz.partial_ratio_alignment(
                lowered_quote,
                lowered_cv,
                score_cutoff=threshold,
            )

    if alignment is None:
        return None

    return QuoteSpan(
        start=int(alignment.dest_start),
        end=int(alignment.dest_end),
        match_score=round(float(alignment.score), 2),
    )


def verify_criterion(
    criterion: LLMOutputCriterion,
    cv_text: str,
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> VerifiedCriterionResult:
    """Verify a single LLM criterion verdict against CV text.

    Any YES or PARTIAL verdict whose quote cannot be verified (>= threshold)
    is downgraded to CriterionVerdict.UNPROVEN and flagged as unverified.
    """
    if criterion.verdict in (CriterionVerdict.YES, CriterionVerdict.PARTIAL):
        span = verify_quote(criterion.quote, cv_text, threshold=threshold)
        if span is None:
            return VerifiedCriterionResult(
                id=criterion.id,
                verdict=CriterionVerdict.UNPROVEN,
                original_verdict=criterion.verdict,
                quote=criterion.quote,
                explanation=criterion.explanation,
                verified=False,
                span=None,
            )
        return VerifiedCriterionResult(
            id=criterion.id,
            verdict=criterion.verdict,
            original_verdict=criterion.verdict,
            quote=criterion.quote,
            explanation=criterion.explanation,
            verified=True,
            span=span,
        )

    if criterion.verdict == CriterionVerdict.NO and criterion.quote.strip():
        span = verify_quote(criterion.quote, cv_text, threshold=threshold)
        return VerifiedCriterionResult(
            id=criterion.id,
            verdict=CriterionVerdict.NO,
            original_verdict=CriterionVerdict.NO,
            quote=criterion.quote,
            explanation=criterion.explanation,
            verified=span is not None,
            span=span,
        )

    return VerifiedCriterionResult(
        id=criterion.id,
        verdict=criterion.verdict,
        original_verdict=criterion.verdict,
        quote=criterion.quote,
        explanation=criterion.explanation,
        verified=False,
        span=None,
    )


def verify_evaluation(
    output: LLMOutputSchema,
    cv_text: str,
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> list[VerifiedCriterionResult]:
    """Verify all criterion verdicts in an LLM evaluation output."""
    return [verify_criterion(c, cv_text, threshold=threshold) for c in output.criteria]
