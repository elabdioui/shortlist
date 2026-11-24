# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deterministic evidence verification against extracted CV text."""

from __future__ import annotations

import re

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
# Shorter quotes are accepted only on an exact, whole-word match.
MIN_EXACT_SHORT_CHARS = 10
# Fragments shorter than this inside a multi-part quote are too generic to verify.
MIN_FRAGMENT_CHARS = 12

# LLMs often elide text ("A ... B") or stitch two nearby sentences together even
# when told not to. Such quotes are split here and every fragment must be found.
_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3,}|…|\[\.\.\.\]|\(\.\.\.\))\s*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n+")
_FRAGMENT_STRIP_CHARS = " \t\r\n-\u2022\u2013\u2014"


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


def _split_fragments(quote: str) -> list[str]:
    """Split an elided or stitched quote into its verbatim fragments."""
    parts: list[str] = []
    for chunk in _ELLIPSIS_RE.split(quote):
        parts.extend(p.strip(_FRAGMENT_STRIP_CHARS) for p in _SENTENCE_SPLIT_RE.split(chunk))
    return [p for p in parts if p]


def verify_quote(
    quote: str,
    cv_text: str,
    *,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
    min_words: int = MIN_QUOTE_WORDS,
    min_chars: int = MIN_QUOTE_CHARS,
) -> QuoteSpan | None:
    """Locate a quote in CV text, tolerating ellipses and stitched sentences.

    The whole quote is tried first. If it does not match, it is split on
    ellipses and sentence/line boundaries; the quote is then verified only if
    *every* fragment of meaningful length matches the CV on its own and the
    fragments together are long enough. The returned span covers the
    fragments when they are close together, otherwise the longest fragment.
    """
    span = _match_quote(
        quote, cv_text, threshold=threshold, min_words=min_words, min_chars=min_chars
    )
    if span is not None or not cv_text:
        return span

    short_span = _exact_short_match(quote, cv_text)
    if short_span is not None:
        return short_span

    fragments = _split_fragments(quote)
    if len(fragments) < 2:
        return None
    meaningful = [f for f in fragments if len(f) >= MIN_FRAGMENT_CHARS]
    if not meaningful or sum(len(f) for f in meaningful) < min_chars:
        return None
    # Short leftover pieces (e.g. a lone "and") must not hide an unverifiable part.
    if sum(len(f) for f in fragments if len(f) < MIN_FRAGMENT_CHARS) > 20:
        return None

    spans: list[QuoteSpan] = []
    for frag in meaningful:
        frag_span = _match_quote(frag, cv_text, threshold=threshold, min_words=1, min_chars=1)
        if frag_span is None:
            return None
        spans.append(frag_span)

    start = min(sp.start for sp in spans)
    end = max(sp.end for sp in spans)
    score = round(min(sp.match_score for sp in spans), 2)
    quoted_len = sum(sp.end - sp.start for sp in spans)
    if end - start <= quoted_len + 400:
        return QuoteSpan(start=start, end=end, match_score=score)
    longest = max(spans, key=lambda sp: sp.end - sp.start)
    return QuoteSpan(start=longest.start, end=longest.end, match_score=score)


def _exact_short_match(quote: str, cv_text: str) -> QuoteSpan | None:
    """Accept a short quote (e.g. "English - Fluent") only if it appears verbatim.

    Fuzzy matching of short strings is unreliable, so quotes under the normal
    length minimum are rejected, except when they occur exactly (ignoring case
    and whitespace) as whole words in the CV and still carry some content:
    at least MIN_EXACT_SHORT_CHARS characters and two words.
    """
    norm_quote = " ".join(quote.split())
    if len(norm_quote) < MIN_EXACT_SHORT_CHARS or len(norm_quote.split()) < 2:
        return None
    norm_cv, orig_indices = _normalize_with_offset_map(cv_text)
    match = re.search(rf"(?<!\w){re.escape(norm_quote)}(?!\w)", norm_cv, re.IGNORECASE)
    if match is None:
        return None
    return QuoteSpan(
        start=orig_indices[match.start()],
        end=orig_indices[match.end() - 1] + 1,
        match_score=100.0,
    )


def _match_quote(
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
