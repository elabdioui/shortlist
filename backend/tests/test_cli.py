# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the Shortlist Typer CLI (`shortlist`)."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from typer.testing import CliRunner

from shortlist.cli import app


def test_cli_version() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["version"])
    assert res.exit_code == 0
    assert "shortlist" in res.stdout


def test_cli_screen_fake_llm(tmp_path: Path) -> None:
    cv_dir = tmp_path / "cvs"
    cv_dir.mkdir()
    (cv_dir / "alice.txt").write_text(
        "Alice Martin\nalice@example.com\n5 years Supply Chain Buyer.\nMaster degree.\n",
        encoding="utf-8",
    )
    (cv_dir / "bob.txt").write_text(
        "Bob Dupont\nbob@example.com\n2 years Warehouse Associate.\n",
        encoding="utf-8",
    )
    job_file = tmp_path / "job.txt"
    job_file.write_text("Supply Chain Buyer with 3+ years experience.", encoding="utf-8")
    out_xlsx = tmp_path / "ranking.xlsx"

    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "screen",
            str(cv_dir),
            "--job",
            str(job_file),
            "--profile",
            "economique",
            "--out",
            str(out_xlsx),
            "--fake-llm",
        ],
    )
    assert res.exit_code == 0, res.stdout
    assert out_xlsx.is_file()
    wb = load_workbook(out_xlsx)
    ws = wb["Shortlist Ranking"]
    assert ws.max_row == 3  # header + 2 CVs


def test_cli_eval_with_dataset(tmp_path: Path) -> None:
    import json

    job_dir = tmp_path / "eval" / "supply_chain"
    cvs_dir = job_dir / "cvs"
    cvs_dir.mkdir(parents=True)
    (job_dir / "job.txt").write_text(
        "Supply Chain Buyer with 3+ years experience.", encoding="utf-8"
    )
    (job_dir / "criteria.json").write_text(
        json.dumps(
            [
                {
                    "id": "c1",
                    "label": "Experience",
                    "description": "3+ years in supply chain",
                    "type": "mandatory",
                    "weight": 5,
                }
            ]
        ),
        encoding="utf-8",
    )
    (cvs_dir / "cv1.txt").write_text(
        "Alice Martin\nalice@example.com\n5 years Supply Chain Buyer.\n",
        encoding="utf-8",
    )
    (cvs_dir / "cv2.txt").write_text(
        "Bob Dupont\nbob@example.com\n2 years Warehouse Associate.\n",
        encoding="utf-8",
    )
    (job_dir / "annotations.json").write_text(
        json.dumps(
            {
                "cv1.txt": {"expected_verdicts": {"c1": "yes"}, "expected_rank": 1},
                "cv2.txt": {"expected_verdicts": {"c1": "not_found"}, "expected_rank": 2},
            }
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    res = runner.invoke(
        app,
        ["eval", "--profile", "economique", "--eval-dir", str(tmp_path / "eval"), "--fake-llm"],
    )
    assert res.exit_code == 0, res.stdout
    payload = json.loads(res.stdout)
    assert payload["status"] == "ok"
    assert payload["jobs_evaluated"] == 1
    assert "per_criterion_agreement" in payload
    assert "spearman_correlation" in payload
    assert "verified_quote_rate" in payload


def test_cli_eval_stub(tmp_path: Path) -> None:
    runner = CliRunner()
    res = runner.invoke(
        app,
        ["eval", "--profile", "economique", "--eval-dir", str(tmp_path / "missing"), "--fake-llm"],
    )
    assert res.exit_code == 0
    assert "no_dataset" in res.stdout
