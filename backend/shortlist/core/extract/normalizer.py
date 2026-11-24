# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Text normalization, language detection, and controlled token truncation."""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_APPROX_TOKENS = 6000
CHARS_PER_TOKEN = 4

_SOFT_HYPHEN_BREAK_RE = re.compile(r"([A-Za-zÀ-ÿ])-\n([a-zà-ÿ])")
# Horizontal whitespace only: a bullet must never swallow the newlines before it.
_BULLET_RE = re.compile(r"^[ \t]*[•▪◦‣●\uf0a7□■\u2013\u2014][ \t]*", re.MULTILINE)
# Bullet glyphs extracted as their own PDF block leave lines holding only "-".
_LONE_BULLET_LINE_RE = re.compile(r"^[ \t]*-[ \t]*$\n?", re.MULTILINE)
_MULTI_SPACE_RE = re.compile(r"[ \t\f\v]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

_FRENCH_STOPWORDS = frozenset(
    {
        "de",
        "la",
        "le",
        "les",
        "et",
        "en",
        "des",
        "du",
        "pour",
        "avec",
        "dans",
        "sur",
        "une",
        "un",
        "au",
        "aux",
        "expérience",
        "formation",
        "compétences",
        "poste",
        "gestion",
        "ans",
    }
)

_ENGLISH_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "of",
        "to",
        "in",
        "for",
        "with",
        "on",
        "an",
        "as",
        "at",
        "by",
        "from",
        "experience",
        "education",
        "skills",
        "management",
        "years",
        "role",
        "team",
    }
)


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Normalized CV text with truncation metadata."""

    text: str
    truncated: bool
    truncation_warning: str | None
    approx_tokens: int


def detect_language(text: str) -> str:
    """Detect whether CV text is primarily French ('fr'), English ('en'), or 'unknown'."""
    tokens = re.findall(r"[A-Za-zÀ-ÿ]+", text.lower())
    if not tokens:
        return "unknown"

    fr_hits = sum(1 for t in tokens if t in _FRENCH_STOPWORDS)
    en_hits = sum(1 for t in tokens if t in _ENGLISH_STOPWORDS)

    if fr_hits == 0 and en_hits == 0:
        return "unknown"
    return "fr" if fr_hits >= en_hits else "en"


def normalize_text(
    text: str,
    *,
    max_tokens: int = MAX_APPROX_TOKENS,
) -> NormalizationResult:
    """Clean whitespace, hyphenation, and bullets, and truncate at ~max_tokens."""
    if not text:
        return NormalizationResult(
            text="",
            truncated=False,
            truncation_warning=None,
            approx_tokens=0,
        )

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _SOFT_HYPHEN_BREAK_RE.sub(r"\1\2", cleaned)
    cleaned = _BULLET_RE.sub("- ", cleaned)
    cleaned = "\n".join(_MULTI_SPACE_RE.sub(" ", line).strip() for line in cleaned.split("\n"))
    cleaned = _LONE_BULLET_LINE_RE.sub("", cleaned)
    cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned).strip()

    max_chars = max_tokens * CHARS_PER_TOKEN
    truncated = False
    warning: str | None = None

    if len(cleaned) > max_chars:
        cutoff = cleaned.rfind(" ", 0, max_chars)
        if cutoff < max_chars // 2:
            cutoff = max_chars
        cleaned = cleaned[:cutoff].rstrip()
        truncated = True
        warning = (
            f"CV text exceeded ~{max_tokens} tokens and was truncated to {len(cleaned)} characters."
        )

    approx_tokens = max(1, len(cleaned) // CHARS_PER_TOKEN) if cleaned else 0
    return NormalizationResult(
        text=cleaned,
        truncated=truncated,
        truncation_warning=warning,
        approx_tokens=approx_tokens,
    )
