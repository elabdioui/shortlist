# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for P0-2: API key attribution, UsageLog accounting, fallback_used, and budget skip."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
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
from shortlist.worker.queue import enqueue_run_tasks, process_task


def _setup_db(tmp_path: Path) -> tuple[sessionmaker[Session], str]:
    secret_key = Fernet.generate_key().decode("ascii")
    db_path = tmp_path / "p0_2.db"
    engine = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return get_session_factory(engine), secret_key


def test_key_failover_usage_log_and_budget_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Key A 429 -> failover to Key B -> Evaluation.api_key_id == B & UsageLog populated."""
    monkeypatch.delenv("SHORTLIST_FAKE_LLM", raising=False)
    factory, secret_key = _setup_db(tmp_path)

    cv_path = tmp_path / "cv1.txt"
    cv_text = "Alice Martin\n5 years Supply Chain Buyer at Acme Corp.\nMaster in Logistics."
    cv_path.write_text(cv_text, encoding="utf-8")

    cv2_path = tmp_path / "cv2.txt"
    cv2_text = "Bob Dupont\n4 years Procurement Specialist at Beta Inc.\nBachelor in Business."
    cv2_path.write_text(cv2_text, encoding="utf-8")

    with factory() as db:
        prov_a = Provider(type=ProviderType.OPENAI.value, active=True)
        prov_b = Provider(type=ProviderType.GEMINI.value, active=True)
        db.add_all([prov_a, prov_b])
        db.flush()

        key_a = APIKey(
            provider_id=prov_a.id,
            label="Key A",
            encrypted_secret=encrypt_secret("sk-key-a-secret", secret_key),
            masked_secret=mask_secret("sk-key-a-secret"),
            allowed_models=["gpt-4o-mini"],
            priority=1,
            tier=KeyTier.PAID.value,
        )
        key_b = APIKey(
            provider_id=prov_b.id,
            label="Key B",
            encrypted_secret=encrypt_secret("gm-key-b-secret", secret_key),
            masked_secret=mask_secret("gm-key-b-secret"),
            allowed_models=["gemini-2.0-flash"],
            priority=1,
            tier=KeyTier.PAID.value,
            monthly_budget_usd=0.01,
        )
        db.add_all([key_a, key_b])
        db.flush()

        profile = ModelProfile(
            name="failover-profile",
            strategy=RoutingStrategy.PRIORITY.value,
            models=[
                {"provider": "openai", "model": "gpt-4o-mini"},
                {"provider": "gemini", "model": "gemini-2.0-flash"},
            ],
        )
        db.add(profile)
        db.flush()

        job = Job(title="Buyer", description="Supply Chain Buyer", profile_id=profile.id)
        db.add(job)
        db.flush()

        cset = CriteriaSet(
            job_id=job.id,
            version=1,
            criteria=[
                {
                    "id": "c1",
                    "label": "Experience",
                    "description": "Supply chain experience",
                    "type": "mandatory",
                    "weight": 5,
                }
            ],
            frozen_at=datetime.now(UTC),
        )
        db.add(cset)

        cand1 = Candidate(
            job_id=job.id,
            filename="cv1.txt",
            stored_path=str(cv_path),
            sha256="a" * 64,
            extracted_text=cv_text,
            anonymized_text=cv_text,
            extraction_status=ExtractionStatus.EXTRACTED.value,
        )
        cand2 = Candidate(
            job_id=job.id,
            filename="cv2.txt",
            stored_path=str(cv2_path),
            sha256="b" * 64,
            extracted_text=cv2_text,
            anonymized_text=cv2_text,
            extraction_status=ExtractionStatus.EXTRACTED.value,
        )
        db.add_all([cand1, cand2])
        db.flush()

        run = AnalysisRun(job_id=job.id, status="pending", total_count=2)
        db.add(run)
        db.flush()
        enqueue_run_tasks(db, run.id, job.id, 1, [cand1.id, cand2.id])
        db.commit()

        key_a_id = key_a.id
        key_b_id = key_b.id
        run_id = run.id
        cand1_id = cand1.id
        cand2_id = cand2.id

    def fake_completion(**kwargs: Any) -> dict[str, Any]:
        if kwargs.get("api_key") == "sk-key-a-secret":
            exc = RuntimeError("429 Too Many Requests")
            exc.status_code = 429  # type: ignore[attr-defined]
            raise exc
        payload = {
            "criteria": [
                {
                    "id": "c1",
                    "verdict": "yes",
                    "quote": "5 years Supply Chain Buyer at Acme Corp.",
                    "explanation": "Matches requirement.",
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
            "usage": {"prompt_tokens": 120, "completion_tokens": 45},
        }

    def fake_cost(_resp: Any, _model: str) -> float:
        return 0.015  # Exceeds Key B's $0.01 monthly_budget_usd after task 1!

    monkeypatch.setattr("shortlist.llm.router._default_litellm_completion", fake_completion)
    monkeypatch.setattr("shortlist.llm.router._default_litellm_cost", fake_cost)
    monkeypatch.setattr("shortlist.llm.router._default_unit_cost", lambda _p, _m: 0.00001)

    with factory() as db:
        tasks = list(
            db.scalars(
                select(AnalysisTask)
                .where(AnalysisTask.run_id == run_id)
                .order_by(AnalysisTask.created_at.asc())
            ).all()
        )
        task1_id, task2_id = tasks[0].id, tasks[1].id

    # Process task 1: Key A hits 429 -> Key B succeeds with fallback_used=True
    with factory() as db:
        process_task(db, task1_id, secret_key=secret_key)

    with factory() as db:
        ev1 = db.scalar(select(Evaluation).where(Evaluation.candidate_id == cand1_id))
        assert ev1 is not None
        assert ev1.api_key_id == key_b_id
        assert ev1.model_used == "gemini-2.0-flash"
        assert ev1.fallback_used is True
        assert ev1.input_tokens == 120
        assert ev1.output_tokens == 45
        assert ev1.cost_usd == pytest.approx(0.015)

        usage_b = db.scalar(select(UsageLog).where(UsageLog.api_key_id == key_b_id))
        assert usage_b is not None
        assert usage_b.requests == 1
        assert usage_b.input_tokens == 120
        assert usage_b.output_tokens == 45
        assert usage_b.cost_usd == pytest.approx(0.015)

        key_a_row = db.get(APIKey, key_a_id)
        assert key_a_row is not None
        assert key_a_row.status == "cooldown"

    # Process task 2: Key A is in cooldown and Key B's monthly budget ($0.01 <= $0.015) is exhausted
    with factory() as db:
        process_task(db, task2_id, secret_key=secret_key)

    with factory() as db:
        task2 = db.get(AnalysisTask, task2_id)
        assert task2 is not None
        # Key A's cooldown is temporary, so the task is requeued with a delay
        # (leased_until = "not before") instead of failing for good.
        assert task2.status == "pending"
        assert task2.leased_until is not None
        assert "Retrying" in (task2.last_error or "")
        assert db.scalar(select(Evaluation).where(Evaluation.candidate_id == cand2_id)) is None


def test_invalid_json_attempt_records_usage_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed LLM evaluation (invalid JSON) that consumed tokens still records UsageLog."""
    monkeypatch.delenv("SHORTLIST_FAKE_LLM", raising=False)
    factory, secret_key = _setup_db(tmp_path)

    cv_path = tmp_path / "cv1.txt"
    cv_path.write_text("Alice Martin\n5 years Supply Chain Buyer.", encoding="utf-8")

    with factory() as db:
        prov = Provider(type=ProviderType.OPENAI.value, active=True)
        db.add(prov)
        db.flush()

        key = APIKey(
            provider_id=prov.id,
            label="Key 1",
            encrypted_secret=encrypt_secret("sk-key-1-secret", secret_key),
            masked_secret=mask_secret("sk-key-1-secret"),
            allowed_models=["gpt-4o-mini"],
            priority=1,
            tier=KeyTier.PAID.value,
        )
        db.add(key)
        db.flush()

        profile = ModelProfile(
            name="p1",
            strategy=RoutingStrategy.PRIORITY.value,
            models=[{"provider": "openai", "model": "gpt-4o-mini"}],
        )
        db.add(profile)
        db.flush()

        job = Job(title="Buyer", description="Buyer", profile_id=profile.id)
        db.add(job)
        db.flush()

        cset = CriteriaSet(
            job_id=job.id,
            version=1,
            criteria=[
                {
                    "id": "c1",
                    "label": "Exp",
                    "description": "Experience",
                    "type": "mandatory",
                    "weight": 5,
                }
            ],
            frozen_at=datetime.now(UTC),
        )
        db.add(cset)

        cand = Candidate(
            job_id=job.id,
            filename="cv1.txt",
            stored_path=str(cv_path),
            sha256="c" * 64,
            extracted_text="Alice Martin\n5 years Supply Chain Buyer.",
            anonymized_text="Alice Martin\n5 years Supply Chain Buyer.",
            extraction_status=ExtractionStatus.EXTRACTED.value,
        )
        db.add(cand)
        db.flush()

        run = AnalysisRun(job_id=job.id, status="pending", total_count=1)
        db.add(run)
        db.flush()
        enqueue_run_tasks(db, run.id, job.id, 1, [cand.id])
        db.commit()
        task_id = db.scalar(select(AnalysisTask.id).where(AnalysisTask.run_id == run.id))
        assert task_id is not None
        key_id = key.id
        cand_id = cand.id

    def fake_bad_json(**_kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "NOT VALID JSON"}}],
            "usage": {"prompt_tokens": 80, "completion_tokens": 15},
        }

    monkeypatch.setattr("shortlist.llm.router._default_litellm_completion", fake_bad_json)
    monkeypatch.setattr("shortlist.llm.router._default_litellm_cost", lambda _r, _m: 0.002)
    monkeypatch.setattr("shortlist.llm.router._default_unit_cost", lambda _p, _m: 0.00001)

    with factory() as db:
        process_task(db, task_id, secret_key=secret_key)

    with factory() as db:
        ev = db.scalar(select(Evaluation).where(Evaluation.candidate_id == cand_id))
        assert ev is not None
        assert ev.api_key_id == key_id
        assert ev.recommendation == "manual_review"
        assert ev.input_tokens == 160  # 2 attempts (initial + 1 JSON retry)
        assert ev.output_tokens == 30
        assert ev.cost_usd == pytest.approx(0.004)

        usage = db.scalar(select(UsageLog).where(UsageLog.api_key_id == key_id))
        assert usage is not None
        assert usage.input_tokens == 160
        assert usage.output_tokens == 30
        assert usage.cost_usd == pytest.approx(0.004)
