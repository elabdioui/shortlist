# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for DevOps, Docker, CI, secret-key init, and repository hygiene."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_p2_3_repo_hygiene_gitignore_and_precommit() -> None:
    """Test artifacts must be gitignored, untracked, and blocked by pre-commit."""
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "frontend/test-results/" in gitignore
    assert "frontend/playwright-report/" in gitignore

    tracked = subprocess.check_output(
        ["git", "ls-files", "frontend/test-results"],
        cwd=ROOT,
        text=True,
    ).strip()
    assert tracked == "", f"Tracked test-results remain: {tracked}"

    precommit = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    for pattern in ("*.db", ".coverage", "data/", "test-results/"):
        assert pattern in precommit, f"Missing {pattern} in .pre-commit-config.yaml"


def test_p1_4_compose_no_default_secret_and_init_scripts_exist() -> None:
    """Compose must not embed an insecure default key, and init scripts must exist."""
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "dev-insecure-change-me-in-production" not in compose
    assert "SHORTLIST_SECRET_KEY" in compose

    init_sh = ROOT / "deploy" / "init.sh"
    init_ps1 = ROOT / "deploy" / "init.ps1"
    assert init_sh.is_file()
    assert init_ps1.is_file()
    assert "Fernet" in init_sh.read_text(encoding="utf-8")
    assert "Fernet" in init_ps1.read_text(encoding="utf-8")


def test_p0_1_and_p2_1_dockerfiles_and_ci_postgres_spacy() -> None:
    """Dockerfiles and CI must install spaCy models, postgres extra, and run PG tests."""
    for df_name in ("Dockerfile.api", "Dockerfile.worker"):
        df = (ROOT / "deploy" / df_name).read_text(encoding="utf-8")
        assert "fr_core_news_md" in df
        assert "en_core_web_md" in df
        assert "postgres" in df

    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "fr_core_news_md" in ci
    assert "en_core_web_md" in ci
    assert "postgres:16" in ci
