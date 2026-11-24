# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Evidence verification package."""

from shortlist.core.verify.verifier import (
    DEFAULT_MATCH_THRESHOLD,
    MIN_QUOTE_CHARS,
    MIN_QUOTE_WORDS,
    verify_criterion,
    verify_evaluation,
    verify_quote,
)

__all__ = [
    "DEFAULT_MATCH_THRESHOLD",
    "MIN_QUOTE_CHARS",
    "MIN_QUOTE_WORDS",
    "verify_criterion",
    "verify_evaluation",
    "verify_quote",
]
