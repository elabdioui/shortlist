# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for P1-1: shared thread-safe KeyPool in WorkerRunner (RPM, RPD across restart)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from shortlist.api.crypto import encrypt_secret, mask_secret
from shortlist.db.base import Base
from shortlist.db.models import (
    AnalysisRun,
    AnalysisTask,
    APIKey,
    Candidate,
    CriteriaSet,
    Evaluation,
    Job,
    ModelProfile,
    Provider,
    UsageLog,
)
from shortlist.db.session import create_db_engine, get_session_factory
from shortlist.schemas.common import ExtractionStatus, KeyTier, ProviderType, RoutingStrategy
from shortlist.worker.queue import enqueue_run_tasks
from shortlist.worker.runner import WorkerRunner


def _seed_job_with_cvs(
    factory: sessionmaker[Session],
    tmp_path: Path,
    secret_key: str,
    *,
    num_cvs: int,
    rpm_limit: int | None = None,
    rpd_limit: int | None = None,
    initial_daily_requests: int = 0,
    now: datetime,
) -> tuple[str, str, str]:
    with factory() as db:
        prov = Provider(type=ProviderType.OPENAI.value, active=True)
        db.add(prov)
        db.flush()

        key = APIKey(
            provider_id=prov.id,
            label="Shared Key",
            encrypted_secret=encrypt_secret("sk-shared-key", secret_key),
            masked_secret=mask_secret("sk-shared-key"),
            allowed_models=["gpt-4o-mini"],
            priority=1,
            tier=KeyTier.PAID.value,
            rpm_limit=rpm_limit,
            rpd_limit=rpd_limit,
            concurrency=4,
        )
        db.add(key)
        db.flush()

        if initial_daily_requests > 0:
            db.add(
                UsageLog(
                    api_key_id=key.id,
                    usage_date=now.strftime("%Y-%m-%d"),
                    requests=initial_daily_requests,
                    input_tokens=100 * initial_daily_requests,
                    output_tokens=20 * initial_daily_requests,
                    cost_usd=0.001 * initial_daily_requests,
                )
            )

        profile = ModelProfile(
            name="shared-pool-profile",
            strategy=RoutingStrategy.PRIORITY.value,
            models=[{"provider": "openai", "model": "gpt-4o-mini"}],
        )
        db.add(profile)
        db.flush()

        job = Job(title="Buyer", description="Supply Chain Buyer", profile_id=profile.id)
        db.add(job)
        db.flush()

        db.add(
            CriteriaSet(
                job_id=job.id,
                version=1,
                criteria=[
                    {
                        "id": "c1",
                        "label": "Exp",
                        "description": "Supply chain experience",
                        "type": "mandatory",
                        "weight": 5,
                    }
                ],
                frozen_at=now,
            )
        )

        cand_ids: list[str] = []
        for i in range(num_cvs):
            cv_path = tmp_path / f"cv_{i}.txt"
            cv_text = f"Candidate {i}\n5 years Supply Chain Buyer at Corp {i}."
            cv_path.write_text(cv_text, encoding="utf-8")
            cand = Candidate(
                job_id=job.id,
                filename=f"cv_{i}.txt",
                stored_path=str(cv_path),
                sha256=f"{i:064x}",
                extracted_text=cv_text,
                anonymized_text=cv_text,
                extraction_status=ExtractionStatus.EXTRACTED.value,
            )
            db.add(cand)
            db.flush()
            cand_ids.append(cand.id)

        run = AnalysisRun(
            job_id=job.id,
            criteria_set_version=1,
            status="pending",
            total_count=num_cvs,
        )
        db.add(run)
        db.flush()
        enqueue_run_tasks(db, run.id, job.id, 1, cand_ids)
        db.commit()
        return job.id, run.id, key.id


def test_shared_keypool_rpm_limit_across_4_threads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With rpm_limit=2 and 6 tasks across 4 threads, only 2 succeed per minute window."""
    monkeypatch.delenv("SHORTLIST_FAKE_LLM", raising=False)
    secret_key = Fernet.generate_key().decode("ascii")
    engine = create_db_engine(f"sqlite:///{tmp_path / 'p1_1_rpm.db'}")
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = get_session_factory(engine)

    current_time = [datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)]

    def clock() -> datetime:
        return current_time[0]

    _job_id, run_id, _key_id = _seed_job_with_cvs(
        factory,
        tmp_path,
        secret_key,
        num_cvs=6,
        rpm_limit=2,
        now=current_time[0],
    )

    def fake_completion(**_kwargs: Any) -> dict[str, Any]:
        payload = {
            "criteria": [
                {
                    "id": "c1",
                    "verdict": "yes",
                    "quote": "5 years Supply Chain Buyer",
                    "explanation": "OK",
                }
            ],
            "relevant_experience_years": 5,
            "current_role": "Buyer",
            "highest_education": "Master",
            "languages": ["en"],
            "strengths": [],
            "watchouts": [],
        }
        return {
            "choices": [{"message": {"content": json.dumps(payload)}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
        }

    monkeypatch.setattr("shortlist.llm.router._default_litellm_completion", fake_completion)
    monkeypatch.setattr("shortlist.llm.router._default_litellm_cost", lambda _r, _m: 0.001)
    monkeypatch.setattr("shortlist.llm.router._default_unit_cost", lambda _p, _m: 0.00001)

    runner = WorkerRunner(
        factory,
        secret_key=secret_key,
        concurrency=4,
        clock=clock,
    )
    runner.run_until_idle()

    with factory() as db:
        eval_count = int(db.scalar(select(func.count(Evaluation.id))) or 0)
        assert eval_count == 2  # Only 2 allowed in the first 60s window!

        # RPM-blocked tasks are not failed: they are requeued with a "not before"
        # delay (leased_until) derived from the RPM window, and the run stays open.
        delayed = list(
            db.scalars(
                select(AnalysisTask).where(
                    AnalysisTask.run_id == run_id, AnalysisTask.status == "pending"
                )
            ).all()
        )
        assert len(delayed) == 4
        assert all(t.leased_until is not None for t in delayed)
        assert all("Retrying" in (t.last_error or "") for t in delayed)
        run = db.get(AnalysisRun, run_id)
        assert run is not None and run.status == "running"

        # Advance clock past 60s window and make the delayed tasks due now.
        current_time[0] = current_time[0] + timedelta(seconds=61)
        db.execute(
            update(AnalysisTask)
            .where(AnalysisTask.run_id == run_id, AnalysisTask.status == "pending")
            .values(leased_until=None)
        )
        db.commit()

    runner.run_until_idle()
    with factory() as db:
        eval_count = int(db.scalar(select(func.count(Evaluation.id))) or 0)
        assert eval_count == 4  # 2 more allowed in the second 60s window!


def test_shared_keypool_rpd_limit_across_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RPD usage from UsageLog is loaded at startup so rpd_limit is enforced across restarts."""
    monkeypatch.delenv("SHORTLIST_FAKE_LLM", raising=False)
    secret_key = Fernet.generate_key().decode("ascii")
    engine = create_db_engine(f"sqlite:///{tmp_path / 'p1_1_rpd.db'}")
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = get_session_factory(engine)

    now = datetime.now(UTC)
    _job_id, _run_id, _key_id = _seed_job_with_cvs(
        factory,
        tmp_path,
        secret_key,
        num_cvs=1,
        rpd_limit=2,
        initial_daily_requests=2,
        now=now,
    )

    runner = WorkerRunner(
        factory,
        secret_key=secret_key,
        concurrency=1,
        clock=lambda: now,
    )
    runner.run_until_idle()

    with factory() as db:
        eval_count = int(db.scalar(select(func.count(Evaluation.id))) or 0)
        assert eval_count == 0
        task = db.scalar(select(AnalysisTask))
        assert task is not None
        assert task.status == "failed"
        assert "exhausted" in (task.last_error or "").lower()
