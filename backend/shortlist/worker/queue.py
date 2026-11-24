# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""DB-backed persistent task queue with atomic leasing and crash recovery."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shortlist.core.anonymize.anonymizer import anonymize_text
from shortlist.core.evaluate.evaluator import evaluate_cv
from shortlist.core.extract.pipeline import extract_cv
from shortlist.core.scoring.scorer import FORMULA_VERSION, score_candidate
from shortlist.core.verify.verifier import verify_evaluation
from shortlist.db.models import (
    AnalysisRun,
    AnalysisTask,
    Candidate,
    CriteriaSet,
    Evaluation,
    Job,
    UsageLog,
)
from shortlist.llm.router import BudgetExceededError, LLMRouter
from shortlist.schemas.common import ExtractionStatus, JobStatus, RunStatus
from shortlist.schemas.jobs import CriterionItem
from shortlist.worker.llm_factory import build_llm_client_for_job, sync_pool_states_to_db

logger = logging.getLogger("shortlist.worker.queue")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def enqueue_run_tasks(
    db: Session,
    run_id: str,
    job_id: str,
    criteria_version: int,
    candidate_ids: list[str],
) -> int:
    """Create pending AnalysisTask rows for candidates not yet evaluated for criteria_version."""
    already_evaluated = set(
        db.scalars(
            select(Evaluation.candidate_id).where(
                Evaluation.candidate_id.in_(candidate_ids),
                Evaluation.criteria_set_version == criteria_version,
            )
        ).all()
    )
    existing_tasks = set(
        db.scalars(select(AnalysisTask.candidate_id).where(AnalysisTask.run_id == run_id)).all()
    )

    added = 0
    for cid in candidate_ids:
        if cid in already_evaluated or cid in existing_tasks:
            continue
        db.add(
            AnalysisTask(
                run_id=run_id,
                job_id=job_id,
                candidate_id=cid,
                status="pending",
            )
        )
        added += 1
    db.flush()
    return added


def recover_stale_tasks(db: Session, now: datetime | None = None) -> int:
    """Reset leased tasks whose lease has expired back to pending."""
    current = now or _utcnow()
    result = cast(
        CursorResult[Any],
        db.execute(
            update(AnalysisTask)
            .where(
                AnalysisTask.status == "leased",
                AnalysisTask.leased_until.is_not(None),
                AnalysisTask.leased_until < current,
            )
            .values(
                status="pending",
                worker_id=None,
                leased_until=None,
                updated_at=current,
            )
        ),
    )
    db.commit()
    return int(result.rowcount or 0)


def claim_next_task(
    db: Session,
    worker_id: str,
    *,
    lease_seconds: int = 120,
) -> str | None:
    """Atomically claim the next pending AnalysisTask and return its ID, or None."""
    now = _utcnow()
    candidate_task = db.execute(
        select(AnalysisTask.id, AnalysisTask.run_id)
        .join(AnalysisRun, AnalysisTask.run_id == AnalysisRun.id)
        .where(
            AnalysisTask.status == "pending",
            AnalysisRun.status.in_([RunStatus.PENDING.value, RunStatus.RUNNING.value]),
        )
        .order_by(AnalysisTask.created_at.asc())
        .limit(1)
    ).first()

    if candidate_task is None:
        return None

    task_id, run_id = candidate_task
    lease_until = now + timedelta(seconds=lease_seconds)

    res = cast(
        CursorResult[Any],
        db.execute(
            update(AnalysisTask)
            .where(
                AnalysisTask.id == task_id,
                AnalysisTask.status == "pending",
            )
            .values(
                status="leased",
                worker_id=worker_id,
                leased_until=lease_until,
                attempts=AnalysisTask.attempts + 1,
                updated_at=now,
            )
        ),
    )
    if (res.rowcount or 0) != 1:
        db.rollback()
        return None

    run_row = db.get(AnalysisRun, run_id)
    if run_row is not None and run_row.status == RunStatus.PENDING.value:
        run_row.status = RunStatus.RUNNING.value
        if run_row.started_at is None:
            run_row.started_at = now
        job_row = db.get(Job, run_row.job_id)
        if job_row is not None and job_row.status != JobStatus.RUNNING.value:
            job_row.status = JobStatus.RUNNING.value

    db.commit()
    return str(task_id)


def _record_usage(
    db: Session,
    api_key_id: str | None,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    if api_key_id is None:
        return
    today = _utcnow().strftime("%Y-%m-%d")
    usage = db.scalar(
        select(UsageLog).where(
            UsageLog.api_key_id == api_key_id,
            UsageLog.usage_date == today,
        )
    )
    if usage is None:
        usage = UsageLog(
            api_key_id=api_key_id,
            usage_date=today,
            requests=1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        db.add(usage)
    else:
        usage.requests += 1
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.cost_usd = round(usage.cost_usd + cost_usd, 8)


def _refresh_run_progress(db: Session, run_id: str) -> None:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        return

    done_count = int(
        db.scalar(
            select(func.count(AnalysisTask.id)).where(
                AnalysisTask.run_id == run_id,
                AnalysisTask.status.in_(["completed", "failed"]),
            )
        )
        or 0
    )
    failed_count = int(
        db.scalar(
            select(func.count(AnalysisTask.id)).where(
                AnalysisTask.run_id == run_id,
                AnalysisTask.status == "failed",
            )
        )
        or 0
    )
    remaining_count = int(
        db.scalar(
            select(func.count(AnalysisTask.id)).where(
                AnalysisTask.run_id == run_id,
                AnalysisTask.status.in_(["pending", "leased"]),
            )
        )
        or 0
    )

    total_cost = float(
        db.scalar(
            select(func.coalesce(func.sum(Evaluation.cost_usd), 0.0))
            .join(Candidate, Evaluation.candidate_id == Candidate.id)
            .where(Candidate.job_id == run.job_id)
        )
        or 0.0
    )

    run.processed_count = done_count
    run.error_count = failed_count
    run.cumulative_cost_usd = round(total_cost, 6)

    if remaining_count == 0 and run.status in (RunStatus.PENDING.value, RunStatus.RUNNING.value):
        run.status = RunStatus.COMPLETED.value
        run.finished_at = _utcnow()
        job = db.get(Job, run.job_id)
        if job is not None:
            job.status = JobStatus.COMPLETED.value


def reconcile_active_runs(db: Session) -> int:
    """Refresh progress and finalize any active or under-counted runs."""
    active_run_ids = list(
        db.scalars(
            select(AnalysisRun.id).where(
                or_(
                    AnalysisRun.status.in_([RunStatus.PENDING.value, RunStatus.RUNNING.value]),
                    AnalysisRun.processed_count < AnalysisRun.total_count,
                )
            )
        ).all()
    )
    for rid in active_run_ids:
        _refresh_run_progress(db, rid)
    if active_run_ids:
        db.commit()
    return len(active_run_ids)


def process_task(
    db: Session,
    task_id: str,
    *,
    secret_key: str,
    force_fake_llm: bool = False,
) -> None:
    """Execute extraction, anonymization, LLM evaluation, verification, and scoring for a task."""
    task = db.get(AnalysisTask, task_id)
    if task is None:
        return

    run = db.get(AnalysisRun, task.run_id)
    job = db.get(Job, task.job_id)
    candidate = db.get(Candidate, task.candidate_id)
    if run is None or job is None or candidate is None:
        task.status = "failed"
        task.last_error = "Missing run, job, or candidate record."
        db.commit()
        return

    criteria_set = db.scalar(
        select(CriteriaSet)
        .where(CriteriaSet.job_id == job.id)
        .order_by(CriteriaSet.version.desc())
        .limit(1)
    )
    if criteria_set is None:
        task.status = "failed"
        task.last_error = "Job has no criteria set."
        _refresh_run_progress(db, run.id)
        db.commit()
        return

    criteria_items = [CriterionItem.model_validate(c) for c in criteria_set.criteria]

    # Idempotency guard: if already evaluated for this criteria version, skip LLM call.
    existing_eval = db.scalar(
        select(Evaluation).where(
            Evaluation.candidate_id == candidate.id,
            Evaluation.criteria_set_version == criteria_set.version,
        )
    )
    if existing_eval is not None:
        task.status = "completed"
        task.worker_id = None
        task.leased_until = None
        _refresh_run_progress(db, run.id)
        db.commit()
        return

    try:
        # 1. Extract text if pending.
        if candidate.extraction_status == ExtractionStatus.PENDING.value:
            file_bytes = Path(candidate.stored_path).read_bytes()
            ext_res = extract_cv(file_bytes, candidate.filename)
            candidate.extracted_text = ext_res.text
            candidate.extraction_status = ext_res.status.value
            db.flush()

        # 2. Anonymize locally if needed.
        if candidate.anonymized_text is None and candidate.extracted_text:
            anon_res = anonymize_text(candidate.extracted_text)
            candidate.anonymized_text = anon_res.anonymized_text
            candidate.encrypted_pii_map = anon_res.encrypt_mapping(secret_key)
            db.flush()

        hidden_detected = candidate.extraction_status == ExtractionStatus.HIDDEN_TEXT_FLAGGED.value
        extraction_failed = (
            candidate.extraction_status == ExtractionStatus.FAILED.value
            or not (candidate.anonymized_text or "").strip()
        )

        if extraction_failed or hidden_detected:
            scoring = score_candidate(
                criteria_items,
                [],
                interview_threshold=job.interview_threshold,
                review_threshold=job.review_threshold,
                extraction_failed=extraction_failed,
                hidden_text_detected=hidden_detected,
            )
            evaluation = Evaluation(
                candidate_id=candidate.id,
                criteria_set_version=criteria_set.version,
                model_used="none",
                api_key_id=None,
                fallback_used=False,
                raw_json={},
                verified_verdicts=[],
                score=scoring.score,
                recommendation=scoring.recommendation.value,
                formula_version=FORMULA_VERSION,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
            )
            db.add(evaluation)
        else:
            remaining_budget: float | None = None
            if job.max_budget_usd is not None:
                remaining_budget = max(0.0, job.max_budget_usd - run.cumulative_cost_usd)

            client, pool, primary_model = build_llm_client_for_job(
                db,
                job,
                secret_key,
                force_fake=force_fake_llm,
                remaining_budget_usd=remaining_budget,
            )

            eval_res = evaluate_cv(
                candidate.anonymized_text or "",
                job.description,
                criteria_items,
                client,
                model=primary_model,
            )

            if pool is not None:
                sync_pool_states_to_db(db, pool)

            fallback_used = False
            api_key_id: str | None = None
            if isinstance(client, LLMRouter) and eval_res.model_used != primary_model:
                fallback_used = True

            if eval_res.invalid_json or eval_res.output is None:
                scoring = score_candidate(
                    criteria_items,
                    [],
                    interview_threshold=job.interview_threshold,
                    review_threshold=job.review_threshold,
                    invalid_json=True,
                )
                raw_json: dict[str, Any] = {"error": eval_res.error or "Invalid JSON"}
                verified_payload: list[dict[str, Any]] = []
            else:
                verified = verify_evaluation(eval_res.output, candidate.anonymized_text or "")
                scoring = score_candidate(
                    criteria_items,
                    verified,
                    interview_threshold=job.interview_threshold,
                    review_threshold=job.review_threshold,
                )
                raw_json = eval_res.output.model_dump(mode="json")
                verified_payload = [v.model_dump(mode="json") for v in verified]

            evaluation = Evaluation(
                candidate_id=candidate.id,
                criteria_set_version=criteria_set.version,
                model_used=eval_res.model_used,
                api_key_id=api_key_id,
                fallback_used=fallback_used,
                raw_json=raw_json,
                verified_verdicts=verified_payload,
                score=scoring.score,
                recommendation=scoring.recommendation.value,
                formula_version=scoring.formula_version,
                input_tokens=eval_res.input_tokens,
                output_tokens=eval_res.output_tokens,
                cost_usd=eval_res.cost_usd,
            )
            db.add(evaluation)
            _record_usage(
                db,
                api_key_id,
                eval_res.input_tokens,
                eval_res.output_tokens,
                eval_res.cost_usd,
            )

        try:
            db.flush()
        except IntegrityError:
            # Another worker already inserted the evaluation concurrently.
            db.rollback()
            task = db.get(AnalysisTask, task_id)
            if task is None:
                return

        task.status = "completed"
        task.worker_id = None
        task.leased_until = None
        task.last_error = None
        db.commit()
        _refresh_run_progress(db, run.id)
        db.commit()

    except BudgetExceededError as exc:
        db.rollback()
        task = db.get(AnalysisTask, task_id)
        run = db.get(AnalysisRun, task.run_id) if task else None
        if task is not None:
            task.status = "pending"
            task.worker_id = None
            task.leased_until = None
            task.last_error = str(exc)
        if run is not None:
            run.status = RunStatus.PAUSED_BUDGET.value
            run.errors = [
                *list(run.errors or []),
                {"candidate_id": candidate.id, "error": str(exc)},
            ]
        db.commit()
    except Exception as exc:
        logger.exception("Failed processing task %s", task_id)
        db.rollback()
        task = db.get(AnalysisTask, task_id)
        run = db.get(AnalysisRun, task.run_id) if task else None
        if task is not None:
            task.status = "failed"
            task.worker_id = None
            task.leased_until = None
            task.last_error = f"{type(exc).__name__}: {exc}"
        if run is not None:
            run.errors = [
                *list(run.errors or []),
                {"candidate_id": candidate.id, "error": str(exc)},
            ]
            _refresh_run_progress(db, run.id)
        db.commit()
