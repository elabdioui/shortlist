# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for P0-1 (spaCy NER startup check) and P1-4 (strict SHORTLIST_SECRET_KEY)."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from typer.testing import CliRunner

from shortlist.api.startup import validate_startup_requirements
from shortlist.cli import app
from shortlist.config import Settings


def test_secret_key_rejected_when_placeholder_or_invalid_unless_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHORTLIST_ALLOW_BLANK_NLP", "1")
    monkeypatch.delenv("SHORTLIST_ENV", raising=False)

    bad_placeholder = Settings(secret_key="dev-insecure-change-me-in-production")
    with pytest.raises(RuntimeError, match="SHORTLIST_SECRET_KEY"):
        validate_startup_requirements(bad_placeholder)

    bad_format = Settings(secret_key="not-a-valid-fernet-key")
    with pytest.raises(RuntimeError, match="SHORTLIST_SECRET_KEY"):
        validate_startup_requirements(bad_format)

    # Allowed when SHORTLIST_ENV=dev
    monkeypatch.setenv("SHORTLIST_ENV", "dev")
    validate_startup_requirements(bad_placeholder)

    # Valid Fernet key succeeds in production mode
    monkeypatch.delenv("SHORTLIST_ENV", raising=False)
    valid_settings = Settings(secret_key=Fernet.generate_key().decode("ascii"))
    validate_startup_requirements(valid_settings)


def test_spacy_models_required_unless_allow_blank_nlp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SHORTLIST_ALLOW_BLANK_NLP", raising=False)
    monkeypatch.setenv("SHORTLIST_ENV", "dev")
    monkeypatch.setattr("shortlist.api.startup.spacy.util.is_package", lambda _name: False)

    settings = Settings(secret_key=Fernet.generate_key().decode("ascii"))
    with pytest.raises(RuntimeError, match="fr_core_news_md"):
        validate_startup_requirements(settings)

    monkeypatch.setenv("SHORTLIST_ALLOW_BLANK_NLP", "1")
    validate_startup_requirements(settings)


def test_cli_gen_secret() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["gen-secret"])
    assert res.exit_code == 0
    key = res.stdout.strip()
    Fernet(key.encode("ascii"))  # Must be a valid Fernet key
