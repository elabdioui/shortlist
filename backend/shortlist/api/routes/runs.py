# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Screening run lifecycle, SSE progress stream, candidate ranking, and Excel/CSV export."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from shortlist.api.auth import record_audit
from shortlist.api.deps import get_db_session, require_roles
from shortlist.api.export import ExportRow, export_ranking_csv, export_ranking_xlsx
from shortlist.api.schemas import RunStartRequest
from shortlist.db.models import (
    AnalysisRun,
    Candidate,
    CriteriaSet,
    Decision,
    Evaluation,
    Job,
    User,
)
from shortlist.db.session import get_session_factory
from shortlist.schemas.candidates import CandidateSummary, VerifiedCriterionResult
from shortlist.schemas.common import (
    CriterionType,
    CriterionVerdict,
    ExtractionStatus,
    HumanDecision,
    JobStatus,
    PaginatedResponse,
    Recommendation,
    RunStatus,
    UserRole,
)
from shortlist.schemas.jobs import CriterionItem
from shortlist.schemas.runs import AnalysisRunResponse, RunEvent
from shortlist.worker.queue import enqueue_run_tasks

router = APIRouter(tags=["runs"])

_TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.COMPLETED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
        RunStatus.PAUSED_BUDGET.value,
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _load_job_ranking_data(
    db: Session,
    job_id: str,
) -> tuple[Job, list[CriterionItem], list[ExportRow]]:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    cset = db.scalar(
        select(CriteriaSet)
        .where(CriteriaSet.job_id == job_id)
        .order_by(CriteriaSet.version.desc())
        .limit(1)
    )
    criteria = [CriterionItem.model_validate(c) for c in (cset.criteria if cset else [])]
    mandatory_ids = [c.id for c in criteria if c.type == CriterionType.MANDATORY]

    candidates = db.scalars(
        select(Candidate).where(Candidate.job_id == job_id).order_by(Candidate.created_at.asc())
    ).all()

    rows: list[ExportRow] = []
    for cand in candidates:
        latest_eval = db.scalar(
            select(Evaluation)
            .where(Evaluation.candidate_id == cand.id)
            .order_by(Evaluation.created_at.desc())
            .limit(1)
        )
        latest_dec = db.scalar(
            select(Decision)
            .where(Decision.candidate_id == cand.id)
            .order_by(Decision.decided_at.desc())
            .limit(1)
        )

        verdicts: list[VerifiedCriterionResult] = []
        mandatory_met = 0
        if latest_eval is not None:
            verdicts = [
                VerifiedCriterionResult.model_validate(v) for v in latest_eval.verified_verdicts
            ]
            verdict_map = {v.id: v.verdict for v in verdicts}
            mandatory_met = sum(
                1 for cid in mandatory_ids if verdict_map.get(cid) == CriterionVerdict.YES
            )

        rows.append(
            ExportRow(
                rank=0,
                filename=cand.filename,
                score=latest_eval.score if latest_eval else None,
                recommendation=Recommendation(latest_eval.recommendation) if latest_eval else None,
                decision=HumanDecision(latest_dec.decision)
                if latest_dec
                else HumanDecision.PENDING,
                note=latest_dec.note if latest_dec else None,
                mandatory_met=mandatory_met,
                mandatory_total=len(mandatory_ids),
                model_used=latest_eval.model_used if latest_eval else None,
                fallback_used=latest_eval.fallback_used if latest_eval else False,
                verdicts=verdicts,
            )
        )

    rows.sort(key=lambda r: (r.score is None, -(r.score or 0.0), r.filename.lower()))
    ranked_rows = [
        ExportRow(
            rank=idx,
            filename=r.filename,
            score=r.score,
            recommendation=r.recommendation,
            decision=r.decision,
            note=r.note,
            mandatory_met=r.mandatory_met,
            mandatory_total=r.mandatory_total,
            model_used=r.model_used,
            fallback_used=r.fallback_used,
            verdicts=r.verdicts,
        )
        for idx, r in enumerate(rows, start=1)
    ]
    return job, criteria, ranked_rows


@router.post(
    "/api/jobs/{job_id}/runs",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_analysis_run(
    job_id: str,
    _payload: RunStartRequest | None = None,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> AnalysisRunResponse:
    """Freeze criteria if needed, create an AnalysisRun, and enqueue pending candidates."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    cset = db.scalar(
        select(CriteriaSet)
        .where(CriteriaSet.job_id == job_id)
        .order_by(CriteriaSet.version.desc())
        .limit(1)
    )
    if cset is None or not cset.criteria:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job must have at least one criterion before starting a run.",
        )

    if cset.frozen_at is None:
        cset.frozen_at = _utcnow()

    candidate_ids = list(
        db.scalars(
            select(Candidate.id)
            .where(Candidate.job_id == job_id)
            .order_by(Candidate.created_at.asc())
        ).all()
    )

    run = AnalysisRun(
        job_id=job.id,
        criteria_set_version=cset.version,
        status=RunStatus.PENDING.value,
        processed_count=0,
        total_count=len(candidate_ids),
        cumulative_cost_usd=0.0,
        error_count=0,
    )
    db.add(run)
    db.flush()

    enqueued = enqueue_run_tasks(db, run.id, job.id, cset.version, candidate_ids)
    run.total_count = enqueued
    if enqueued == 0:
        run.status = RunStatus.COMPLETED.value
        run.finished_at = _utcnow()
        job.status = JobStatus.COMPLETED.value
    else:
        job.status = JobStatus.RUNNING.value

    record_audit(
        db,
        user.id,
        "run.start",
        "analysis_run",
        run.id,
        {"job_id": job.id, "enqueued": enqueued},
    )
    db.commit()
    db.refresh(run)
    return AnalysisRunResponse.model_validate(run)


@router.get("/api/runs/{run_id}", response_model=AnalysisRunResponse)
def get_run(
    run_id: str,
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> AnalysisRunResponse:
    """Return current status and progress of an analysis run."""
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return AnalysisRunResponse.model_validate(run)


@router.get("/api/runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
) -> StreamingResponse:
    """Stream Server-Sent Events (SSE) for an analysis run until it reaches a terminal state."""
    factory = getattr(request.app.state, "session_factory", None) or get_session_factory()
    session_factory = cast(sessionmaker[Session], factory)

    with session_factory() as db:
        initial = db.get(AnalysisRun, run_id)
        if initial is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    async def _event_stream() -> AsyncGenerator[str, None]:
        last_signature: tuple[str, int, int, float] | None = None
        while True:
            if await request.is_disconnected():
                break

            with session_factory() as db:
                run = db.get(AnalysisRun, run_id)
                if run is None:
                    break
                sig = (run.status, run.processed_count, run.total_count, run.cumulative_cost_usd)
                if sig != last_signature:
                    event = RunEvent(
                        run_id=run.id,
                        status=RunStatus(run.status),
                        processed_count=run.processed_count,
                        total_count=run.total_count,
                        cumulative_cost_usd=run.cumulative_cost_usd,
                    )
                    yield f"event: progress\ndata: {event.model_dump_json()}\n\n"
                    last_signature = sig

                if run.status in _TERMINAL_RUN_STATUSES:
                    break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/jobs/{job_id}/ranking", response_model=PaginatedResponse[CandidateSummary])
def get_job_ranking(
    job_id: str,
    recommendation: Recommendation | None = Query(default=None),
    decision: HumanDecision | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> PaginatedResponse[CandidateSummary]:
    """Return filterable, paginated candidate ranking for a job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    cset = db.scalar(
        select(CriteriaSet)
        .where(CriteriaSet.job_id == job_id)
        .order_by(CriteriaSet.version.desc())
        .limit(1)
    )
    criteria = [CriterionItem.model_validate(c) for c in (cset.criteria if cset else [])]
    mandatory_ids = [c.id for c in criteria if c.type == CriterionType.MANDATORY]

    candidates = db.scalars(select(Candidate).where(Candidate.job_id == job_id)).all()
    summaries: list[CandidateSummary] = []

    for cand in candidates:
        if search and search.lower() not in cand.filename.lower():
            continue

        latest_eval = db.scalar(
            select(Evaluation)
            .where(Evaluation.candidate_id == cand.id)
            .order_by(Evaluation.created_at.desc())
            .limit(1)
        )
        latest_dec = db.scalar(
            select(Decision)
            .where(Decision.candidate_id == cand.id)
            .order_by(Decision.decided_at.desc())
            .limit(1)
        )

        rec_val = Recommendation(latest_eval.recommendation) if latest_eval else None
        dec_val = HumanDecision(latest_dec.decision) if latest_dec else HumanDecision.PENDING

        if recommendation is not None and rec_val != recommendation:
            continue
        if decision is not None and dec_val != decision:
            continue

        mandatory_met = 0
        if latest_eval is not None:
            verdicts = [
                VerifiedCriterionResult.model_validate(v) for v in latest_eval.verified_verdicts
            ]
            verdict_map = {v.id: v.verdict for v in verdicts}
            mandatory_met = sum(
                1 for cid in mandatory_ids if verdict_map.get(cid) == CriterionVerdict.YES
            )

        summaries.append(
            CandidateSummary(
                id=cand.id,
                job_id=cand.job_id,
                filename=cand.filename,
                extraction_status=ExtractionStatus(cand.extraction_status),
                score=latest_eval.score if latest_eval else None,
                recommendation=rec_val,
                decision=dec_val,
                mandatory_met=mandatory_met,
                mandatory_total=len(mandatory_ids),
                model_used=latest_eval.model_used if latest_eval else None,
                fallback_used=latest_eval.fallback_used if latest_eval else False,
            )
        )

    summaries.sort(key=lambda s: (s.score is None, -(s.score or 0.0), s.filename.lower()))
    total = len(summaries)
    page_items = summaries[offset : offset + limit]
    return PaginatedResponse[CandidateSummary](
        items=page_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/jobs/{job_id}/export")
def export_job_ranking(
    job_id: str,
    format: str = Query(default="xlsx", pattern="^(xlsx|csv)$"),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> Response:
    """Export job candidate ranking with decisions and justifications as .xlsx or .csv."""
    job, criteria, rows = _load_job_ranking_data(db, job_id)
    record_audit(db, user.id, f"export.{format}", "job", job.id, {"count": len(rows)})
    db.commit()

    if format == "csv":
        content = export_ranking_csv(rows, criteria)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="shortlist-{job.id}.csv"'},
        )

    content = export_ranking_xlsx(job.title, rows, criteria)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="shortlist-{job.id}.xlsx"'},
    )
