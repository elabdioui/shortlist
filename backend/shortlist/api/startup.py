# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Runtime startup validation for secret keys and spaCy NER models."""

from __future__ import annotations

import os

import spacy.util
from cryptography.fernet import Fernet

from shortlist.config import Settings

_INSECURE_PLACEHOLDER = "dev-insecure-change-me-in-production"
_REQUIRED_SPACY_MODELS = ("fr_core_news_md", "en_core_web_md")


def validate_startup_requirements(settings: Settings) -> None:
    """Validate SHORTLIST_SECRET_KEY and spaCy NER models before serving traffic."""
    env_mode = os.environ.get("SHORTLIST_ENV", "").strip().lower()
    if env_mode != "dev":
        secret = settings.secret_key.strip()
        if not secret or secret == _INSECURE_PLACEHOLDER:
            raise RuntimeError(
                "SHORTLIST_SECRET_KEY must be set to a valid Fernet key "
                "(generate one with `shortlist gen-secret`, or set SHORTLIST_ENV=dev)."
            )
        try:
            Fernet(secret.encode("ascii"))
        except Exception as exc:
            raise RuntimeError(
                "SHORTLIST_SECRET_KEY is not a valid Fernet key "
                "(generate one with `shortlist gen-secret`, or set SHORTLIST_ENV=dev)."
            ) from exc

    allow_blank = os.environ.get("SHORTLIST_ALLOW_BLANK_NLP", "").strip() == "1"
    if not allow_blank:
        missing = [m for m in _REQUIRED_SPACY_MODELS if not spacy.util.is_package(m)]
        if missing:
            raise RuntimeError(
                f"Required spaCy NER model(s) missing: {', '.join(missing)}. "
                "Install them or set SHORTLIST_ALLOW_BLANK_NLP=1 for development."
            )
