# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for jobs, criteria, CV upload/dedup/erasure, decisions, privacy purge, and export."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy.orm import Session, sessionmaker

from shortlist.api.app import create_app
from shortlist.config import Settings
from shortlist.db.base import Base
from shortlist.db.models import Job
from shortlist.db.session import create_db_engine, get_session_factory
from shortlist.worker.runner import WorkerRunner


@pytest.fixture()
def env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, sessionmaker[Session], Settings]:
    monkeypatch.setenv("SHORTLIST_FAKE_LLM", "1")
    db_path = tmp_path / "test_jobs.db"
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{db_path}",
        secret_key="test-secret-key-for-jobs-suite-32bytes",
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
    return client, factory, settings


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_full_job_lifecycle_decisions_and_exports(
    env: tuple[TestClient, sessionmaker[Session], Settings],
) -> None:
    client, factory, settings = env

    # 1. Create job
    job_res = client.post(
        "/api/jobs",
        json={
            "title": "Supply Chain Buyer",
            "description": "Looking for a Supply Chain Buyer with 3+ years experience and Excel.",
        },
    )
    assert job_res.status_code == 201
    job_id = job_res.json()["id"]

    # 2. Generate criteria via FakeLLMClient
    gen = client.post(f"/api/jobs/{job_id}/criteria/generate")
    assert gen.status_code == 200
    criteria = gen.json()["criteria"]
    assert len(criteria) == 5

    # Discriminatory criterion rejected
    bad_crit = client.put(
        f"/api/jobs/{job_id}/criteria",
        json={
            "criteria": [
                {
                    "id": "c1",
                    "label": "Young candidate",
                    "description": "Must be under 30 years old",
                    "type": "mandatory",
                    "weight": 5,
                }
            ]
        },
    )
    assert bad_crit.status_code == 422

    # Save valid criteria
    save_crit = client.put(f"/api/jobs/{job_id}/criteria", json={"criteria": criteria})
    assert save_crit.status_code == 200

    # 3. Upload CVs (ZIP + duplicate detection)
    cv1 = (
        b"Jean Dupont\njean.dupont@example.com\n+212612345678\n"
        b"5 years as Supply Chain Buyer in manufacturing.\n"
        b"Master in Logistics and Supply Chain Management.\n"
        b"Fluent in French and English.\n"
    )
    cv2 = (
        b"Amina El Amrani\namina@example.com\n"
        b"4 years in procurement and supplier management.\n"
        b"Bachelor in Business Administration.\n"
    )
    zip_bytes = _make_zip({"cv1.txt": cv1, "cv2.txt": cv2, "cv1_dup.txt": cv1})
    up = client.post(
        f"/api/jobs/{job_id}/candidates",
        files=[("files", ("batch.zip", zip_bytes, "application/zip"))],
    )
    assert up.status_code == 201
    up_data = up.json()
    assert len(up_data["uploaded"]) == 2
    assert up_data["duplicates_skipped"] == ["cv1_dup.txt"]

    cand_id = up_data["uploaded"][0]["id"]

    # 4. Anonymized preview hides email and phone
    preview = client.get(f"/api/candidates/{cand_id}/anonymized-preview")
    assert preview.status_code == 200
    anon_text = preview.json()["anonymized_text"]
    assert "jean.dupont@example.com" not in anon_text
    assert "+212612345678" not in anon_text

    # File serving works
    file_res = client.get(f"/api/candidates/{cand_id}/file")
    assert file_res.status_code == 200
    assert b"Supply Chain Buyer" in file_res.content

    # Estimate works
    est = client.get(f"/api/jobs/{job_id}/estimate")
    assert est.status_code == 200
    assert est.json()["candidate_count"] == 2

    # 5. Start run and process with WorkerRunner
    run_res = client.post(f"/api/jobs/{job_id}/runs")
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]

    runner = WorkerRunner(
        factory, secret_key=settings.secret_key, concurrency=2, force_fake_llm=True
    )
    processed = runner.run_until_idle()
    assert processed == 2

    run_status = client.get(f"/api/runs/{run_id}").json()
    assert run_status["status"] == "completed"
    assert run_status["processed_count"] == 2

    # 6. Ranking & detail
    ranking = client.get(f"/api/jobs/{job_id}/ranking").json()
    assert ranking["total"] == 2
    detail = client.get(f"/api/candidates/{cand_id}").json()
    assert detail["evaluation"] is not None

    # 7. Decision with verdict override recomputes score deterministically
    all_yes = {c["id"]: "yes" for c in criteria}
    dec = client.post(
        f"/api/candidates/{cand_id}/decision",
        json={"decision": "shortlisted", "note": "Strong profile", "verdict_overrides": all_yes},
    )
    assert dec.status_code == 200
    updated_detail = client.get(f"/api/candidates/{cand_id}").json()
    assert updated_detail["evaluation"]["score"] == 100.0
    assert updated_detail["evaluation"]["recommendation"] == "interview"

    # 8. Export XLSX and CSV
    xlsx_res = client.get(f"/api/jobs/{job_id}/export?format=xlsx")
    assert xlsx_res.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx_res.content))
    ws = wb["Shortlist Ranking"]
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref is not None
    assert ws.cell(row=2, column=1).value == 1

    csv_res = client.get(f"/api/jobs/{job_id}/export?format=csv")
    assert csv_res.status_code == 200
    assert "Strong profile" in csv_res.content.decode("utf-8-sig")

    # 9. Candidate erasure
    del_res = client.delete(f"/api/candidates/{cand_id}")
    assert del_res.status_code == 204
    assert client.get(f"/api/candidates/{cand_id}").status_code == 404


def test_privacy_settings_and_retention_purge(
    env: tuple[TestClient, sessionmaker[Session], Settings],
) -> None:
    client, factory, _settings = env

    # Update privacy settings
    put_res = client.put(
        "/api/settings/privacy",
        json={"anonymization_level": "max", "retention_days": 30, "auto_purge_enabled": True},
    )
    assert put_res.status_code == 200
    assert put_res.json()["retention_days"] == 30

    # Create a completed job backdated 60 days
    job_res = client.post(
        "/api/jobs",
        json={"title": "Old Job", "description": "Expired job"},
    )
    old_job_id = job_res.json()["id"]
    with factory() as db:
        job = db.get(Job, old_job_id)
        assert job is not None
        job.status = "completed"
        job.updated_at = datetime.now(UTC) - timedelta(days=60)
        db.commit()

    purge = client.post("/api/settings/privacy/purge")
    assert purge.status_code == 200
    assert purge.json()["deleted_jobs"] == 1
    assert client.get(f"/api/jobs/{old_job_id}").status_code == 404
