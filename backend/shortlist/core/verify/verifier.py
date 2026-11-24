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
MIN_QUOTE_WORDS = 4
MIN_QUOTE_CHARS = 20


def _is_sufficient_quote(
    quote: str,
    min_words: int = MIN_QUOTE_WORDS,
    min_chars: int = MIN_QUOTE_CHARS,
) -> bool:
    stripped = quote.strip()
    if not stripped:
        return False
    return len(stripped.split()) >= min_words or len(stripped) >= min_chars


def _normalize_with_offset_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to single spaces and map each char back to original index."""
    norm_chars: list[str] = []
    orig_indices: list[int] = []
    in_space = False

    for idx, ch in enumerate(text):
        if ch.isspace():
            if norm_chars and not in_space:
                norm_chars.append(" ")
                orig_indices.append(idx)
                in_space = True
        else:
            norm_chars.append(ch)
            orig_indices.append(idx)
            in_space = False

    if norm_chars and norm_chars[-1] == " ":
        norm_chars.pop()
        orig_indices.pop()

    return "".join(norm_chars), orig_indices


def verify_quote(
    quote: str,
    cv_text: str,
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
    min_words: int = MIN_QUOTE_WORDS,
    min_chars: int = MIN_QUOTE_CHARS,
) -> QuoteSpan | None:
    """Locate a quote in CV text using rapidfuzz partial_ratio >= threshold.

    Matches against whitespace-normalized CV text and maps the matched range
    back to exact character offsets in the original `cv_text`.
    """
    if not cv_text or not _is_sufficient_quote(quote, min_words=min_words, min_chars=min_chars):
        return None

    norm_quote = " ".join(quote.split())
    norm_cv, orig_indices = _normalize_with_offset_map(cv_text)
    if not norm_cv or not norm_quote:
        return None

    alignment = fuzz.partial_ratio_alignment(
        norm_quote,
        norm_cv,
        score_cutoff=threshold,
    )

    if alignment is None:
        lowered_cv = norm_cv.lower()
        lowered_quote = norm_quote.lower()
        if len(lowered_cv) == len(norm_cv):
            alignment = fuzz.partial_ratio_alignment(
                lowered_quote,
                lowered_cv,
                score_cutoff=threshold,
            )

    if alignment is None or alignment.dest_end <= alignment.dest_start:
        return None

    orig_start = orig_indices[int(alignment.dest_start)]
    orig_end = orig_indices[int(alignment.dest_end) - 1] + 1

    return QuoteSpan(
        start=orig_start,
        end=orig_end,
        match_score=round(float(alignment.score), 2),
    )


def verify_criterion(
    criterion: LLMOutputCriterion,
    cv_text: str,
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
    min_words: int = MIN_QUOTE_WORDS,
    min_chars: int = MIN_QUOTE_CHARS,
) -> VerifiedCriterionResult:
    """Verify a single LLM criterion verdict against CV text.

    Any YES, PARTIAL, or NO verdict whose quote is missing, too short, or
    unverified (< threshold) is downgraded to CriterionVerdict.UNPROVEN.
    """
    if criterion.verdict in (CriterionVerdict.YES, CriterionVerdict.PARTIAL, CriterionVerdict.NO):
        span = verify_quote(
            criterion.quote,
            cv_text,
            threshold=threshold,
            min_words=min_words,
            min_chars=min_chars,
        )
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
    min_words: int = MIN_QUOTE_WORDS,
    min_chars: int = MIN_QUOTE_CHARS,
) -> list[VerifiedCriterionResult]:
    """Verify all criterion verdicts in an LLM evaluation output."""
    return [
        verify_criterion(
            c,
            cv_text,
            threshold=threshold,
            min_words=min_words,
            min_chars=min_chars,
        )
        for c in output.criteria
    ]
