# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for P1-2: AnalysisRun.criteria_set_version isolation on mid-run grid edits."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from shortlist.api.app import create_app
from shortlist.config import Settings
from shortlist.db.base import Base
from shortlist.db.models import Evaluation
from shortlist.db.session import create_db_engine, get_session_factory
from shortlist.worker.runner import WorkerRunner


def test_mid_run_criteria_edit_creates_new_version_without_affecting_running_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing criteria mid-run creates v2 while the running run finishes all CVs on v1."""
    monkeypatch.setenv("SHORTLIST_FAKE_LLM", "1")
    monkeypatch.setenv("SHORTLIST_ALLOW_BLANK_NLP", "1")
    db_path = tmp_path / "p1_2.db"
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{db_path}",
        secret_key=Fernet.generate_key().decode("ascii"),
        environment="test",
    )
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = get_session_factory(engine)
    app = create_app(settings_override=settings, session_factory=factory)
    client = TestClient(app)

    setup = client.post(
        "/api/auth/setup",
        json={"email": "admin@example.com", "password": "StrongPassword123!"},
    )
    assert setup.status_code == 201
    client.headers.update({"X-CSRF-Token": setup.json()["csrf_token"]})

    job_id = client.post(
        "/api/jobs",
        json={"title": "Buyer", "description": "Supply Chain Buyer"},
    ).json()["id"]

    crit_v1 = [
        {
            "id": "c1",
            "label": "Experience",
            "description": "Supply chain experience",
            "type": "mandatory",
            "weight": 5,
        }
    ]
    assert client.put(f"/api/jobs/{job_id}/criteria", json={"criteria": crit_v1}).status_code == 200

    up = client.post(
        f"/api/jobs/{job_id}/candidates",
        files=[
            ("files", ("cv1.txt", b"Alice\n5 years Supply Chain Buyer.", "text/plain")),
            ("files", ("cv2.txt", b"Bob\n4 years Supply Chain Buyer.", "text/plain")),
        ],
    )
    assert up.status_code == 201

    run1 = client.post(f"/api/jobs/{job_id}/runs")
    assert run1.status_code == 201
    run1_data = run1.json()
    assert run1_data["criteria_set_version"] == 1
    run1_id = run1_data["id"]

    # Process only 1 of 2 tasks.
    worker = WorkerRunner(
        factory,
        secret_key=settings.secret_key,
        concurrency=1,
        force_fake_llm=True,
    )
    assert worker.run_until_idle(max_tasks=1) == 1

    # Edit criteria mid-run -> must create version 2 without mutating version 1.
    crit_v2 = [
        *crit_v1,
        {
            "id": "c2",
            "label": "Degree",
            "description": "Master degree",
            "type": "bonus",
            "weight": 3,
        },
    ]
    put_v2 = client.put(f"/api/jobs/{job_id}/criteria", json={"criteria": crit_v2})
    assert put_v2.status_code == 200
    assert put_v2.json()["version"] == 2

    # Finish remaining task of run1 -> must still use criteria_set_version == 1.
    assert worker.run_until_idle() == 1
    assert client.get(f"/api/runs/{run1_id}").json()["status"] == "completed"

    with factory() as db:
        evals_v1 = list(db.scalars(select(Evaluation)).all())
        assert len(evals_v1) == 2
        assert all(e.criteria_set_version == 1 for e in evals_v1)

    # Starting a new run now uses criteria_set_version == 2.
    run2 = client.post(f"/api/jobs/{job_id}/runs")
    assert run2.status_code == 201
    assert run2.json()["criteria_set_version"] == 2
    assert run2.json()["total_count"] == 2
