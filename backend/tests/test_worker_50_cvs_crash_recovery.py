# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Phase 3 Exit Criterion: 50 synthetic CVs end-to-end with mid-run worker crash recovery."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from shortlist.api.app import create_app
from shortlist.config import Settings
from shortlist.db.base import Base
from shortlist.db.models import AnalysisTask, Evaluation
from shortlist.db.session import create_db_engine, get_session_factory
from shortlist.worker.runner import WorkerRunner


def test_50_synthetic_cvs_crash_and_resume_without_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run 50 CVs with SHORTLIST_FAKE_LLM=1, simulate mid-run crash, resume, verify 50 evals."""
    monkeypatch.setenv("SHORTLIST_FAKE_LLM", "1")
    db_path = tmp_path / "test_50cvs.db"
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{db_path}",
        secret_key="test-secret-key-for-50cvs-suite-32bytes",
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

    job_res = client.post(
        "/api/jobs",
        json={
            "title": "Logistics Coordinator",
            "description": (
                "Coordinate supply chain operations, 3+ years experience, Master degree."
            ),
        },
    )
    job_id = job_res.json()["id"]

    crit_res = client.post(f"/api/jobs/{job_id}/criteria/generate")
    assert crit_res.status_code == 200
    criteria = crit_res.json()["criteria"]
    assert (
        client.put(f"/api/jobs/{job_id}/criteria", json={"criteria": criteria}).status_code == 200
    )

    # Build a ZIP containing 50 unique synthetic CVs.
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(1, 51):
            cv_text = (
                f"Candidate {i:02d} Nom\n"
                f"candidate{i:02d}@example.com\n"
                f"+21260000{i:04d}\n"
                f"{(i % 7) + 1} years of experience in Logistics and Supply Chain #{i}.\n"
                f"Master degree in Operations Management from University {i}.\n"
                f"Proficient in ERP, Excel, French and English.\n"
            )
            zf.writestr(f"cv_{i:02d}.txt", cv_text.encode("utf-8"))

    up_res = client.post(
        f"/api/jobs/{job_id}/candidates",
        files=[("files", ("cvs_50.zip", zip_buf.getvalue(), "application/zip"))],
    )
    assert up_res.status_code == 201
    assert len(up_res.json()["uploaded"]) == 50

    run_res = client.post(f"/api/jobs/{job_id}/runs")
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]
    assert run_res.json()["total_count"] == 50

    # Phase A: Worker 1 processes 20 tasks and then "crashes".
    worker1 = WorkerRunner(
        factory,
        secret_key=settings.secret_key,
        concurrency=2,
        force_fake_llm=True,
        worker_id="worker-crash-1",
    )
    processed_before_crash = worker1.run_until_idle(max_tasks=20)
    assert processed_before_crash == 20

    # Simulate 2 tasks left in "leased" state with expired lease when worker-1 died.
    with factory() as db:
        stale_ids = list(
            db.scalars(
                select(AnalysisTask.id)
                .where(AnalysisTask.run_id == run_id, AnalysisTask.status == "pending")
                .limit(2)
            ).all()
        )
        assert len(stale_ids) == 2
        db.execute(
            update(AnalysisTask)
            .where(AnalysisTask.id.in_(stale_ids))
            .values(
                status="leased",
                worker_id="worker-crash-1",
                leased_until=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        db.commit()

    # Phase B: Worker 2 starts up, recovers stale leases, and finishes all remaining tasks.
    worker2 = WorkerRunner(
        factory,
        secret_key=settings.secret_key,
        concurrency=4,
        force_fake_llm=True,
        worker_id="worker-resume-2",
    )
    processed_after_resume = worker2.run_until_idle()
    assert processed_after_resume == 30

    # Verify final run state and zero duplicate evaluations.
    final_run = client.get(f"/api/runs/{run_id}").json()
    assert final_run["status"] == "completed"
    assert final_run["processed_count"] == 50
    assert final_run["error_count"] == 0

    with factory() as db:
        eval_count = int(db.scalar(select(func.count(Evaluation.id))) or 0)
        distinct_cands = int(db.scalar(select(func.count(Evaluation.candidate_id.distinct()))) or 0)
        assert eval_count == 50
        assert distinct_cands == 50

    # Verify SSE endpoint emits final progress event and terminates cleanly.
    sse_res = client.get(f"/api/runs/{run_id}/events")
    assert sse_res.status_code == 200
    assert "event: progress" in sse_res.text
    assert '"processed_count":50' in sse_res.text

    # Verify ranking returns all 50 candidates.
    ranking = client.get(f"/api/jobs/{job_id}/ranking?limit=100").json()
    assert ranking["total"] == 50
    assert len(ranking["items"]) == 50
