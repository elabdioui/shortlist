# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Jobs CRUD, AI criteria generation/validation, and pre-run cost estimation routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shortlist.api.auth import record_audit
from shortlist.api.deps import get_app_settings, get_db_session, require_roles
from shortlist.api.schemas import CriteriaGenerateResponse
from shortlist.config import Settings
from shortlist.core.evaluate.criteria_generator import (
    detect_discriminatory_reason,
    generate_criteria,
)
from shortlist.db.models import AnalysisRun, Candidate, CriteriaSet, Job, ModelProfile, User
from shortlist.llm.providers import is_external_provider
from shortlist.schemas.common import JobStatus, ProviderType, RunStatus, UserRole
from shortlist.schemas.jobs import (
    CriteriaSetResponse,
    CriteriaSetUpdate,
    EstimateResponse,
    JobCreate,
    JobResponse,
    JobUpdate,
)
from shortlist.schemas.providers import ModelProfileEntry
from shortlist.worker.fake_llm import is_fake_llm_enabled
from shortlist.worker.llm_factory import build_llm_client_for_job
from shortlist.worker.queue import candidate_analysis_states

router = APIRouter(tags=["jobs"])


def _get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job


@router.get("/api/jobs", response_model=list[JobResponse])
def list_jobs(
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> list[JobResponse]:
    """List all recruitment jobs."""
    rows = db.scalars(select(Job).order_by(Job.created_at.desc())).all()
    return [JobResponse.model_validate(r) for r in rows]


@router.post("/api/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> JobResponse:
    """Create a new job posting."""
    if payload.review_threshold > payload.interview_threshold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="review_threshold cannot exceed interview_threshold.",
        )

    job = Job(
        title=payload.title,
        description=payload.description,
        profile_id=payload.profile_id,
        interview_threshold=payload.interview_threshold,
        review_threshold=payload.review_threshold,
        max_budget_usd=payload.max_budget_usd,
        status=JobStatus.DRAFT.value,
    )
    db.add(job)
    db.flush()
    record_audit(db, user.id, "job.create", "job", job.id, {"title": job.title})
    db.commit()
    db.refresh(job)
    return JobResponse.model_validate(job)


@router.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> JobResponse:
    """Retrieve a single job posting."""
    return JobResponse.model_validate(_get_job_or_404(db, job_id))


@router.patch("/api/jobs/{job_id}", response_model=JobResponse)
def update_job(
    job_id: str,
    payload: JobUpdate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> JobResponse:
    """Update job fields."""
    job = _get_job_or_404(db, job_id)
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        if field_name == "status" and value is not None:
            setattr(job, field_name, value.value)
        else:
            setattr(job, field_name, value)

    if job.review_threshold > job.interview_threshold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="review_threshold cannot exceed interview_threshold.",
        )

    record_audit(db, user.id, "job.update", "job", job.id)
    db.commit()
    db.refresh(job)
    return JobResponse.model_validate(job)


@router.delete("/api/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: str,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> None:
    """Delete a job posting and all its stored CV files and evaluations."""
    job = _get_job_or_404(db, job_id)
    stored_paths = db.scalars(select(Candidate.stored_path).where(Candidate.job_id == job_id)).all()
    for sp in stored_paths:
        path = Path(sp)
        if path.is_file():
            path.unlink(missing_ok=True)

    record_audit(db, user.id, "job.delete", "job", job.id, {"title": job.title})
    db.delete(job)
    db.commit()


@router.post("/api/jobs/{job_id}/criteria/generate", response_model=CriteriaGenerateResponse)
def generate_job_criteria(
    job_id: str,
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> CriteriaGenerateResponse:
    """Use the configured LLM (or FakeLLMClient) to propose 5-12 criteria."""
    job = _get_job_or_404(db, job_id)
    try:
        client, _pool, model_name = build_llm_client_for_job(db, job, settings.secret_key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    result = generate_criteria(job.description, client, model=model_name)
    return CriteriaGenerateResponse(
        criteria=result.criteria,
        rejected_discriminatory=result.rejected_discriminatory,
        model_used=result.model_used,
    )


@router.get("/api/jobs/{job_id}/criteria", response_model=CriteriaSetResponse)
def get_job_criteria(
    job_id: str,
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> CriteriaSetResponse:
    """Return the latest criteria set for a job."""
    _get_job_or_404(db, job_id)
    cset = db.scalar(
        select(CriteriaSet)
        .where(CriteriaSet.job_id == job_id)
        .order_by(CriteriaSet.version.desc())
        .limit(1)
    )
    if cset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No criteria set found for this job.",
        )
    return CriteriaSetResponse.model_validate(cset)


@router.put("/api/jobs/{job_id}/criteria", response_model=CriteriaSetResponse)
def save_job_criteria(
    job_id: str,
    payload: CriteriaSetUpdate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> CriteriaSetResponse:
    """Save and validate a job's criteria grid (rejecting discriminatory criteria)."""
    job = _get_job_or_404(db, job_id)
    for item in payload.criteria:
        reason = detect_discriminatory_reason(item.label, item.description)
        if reason is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Discriminatory criterion rejected ({reason}): {item.label}",
            )

    latest = db.scalar(
        select(CriteriaSet)
        .where(CriteriaSet.job_id == job_id)
        .order_by(CriteriaSet.version.desc())
        .limit(1)
    )

    serialized = [c.model_dump(mode="json") for c in payload.criteria]
    if latest is not None and latest.frozen_at is None:
        latest.criteria = serialized
        cset = latest
    else:
        next_version = 1 if latest is None else latest.version + 1
        cset = CriteriaSet(job_id=job.id, version=next_version, criteria=serialized)
        db.add(cset)

    if job.status == JobStatus.DRAFT.value:
        job.status = JobStatus.READY.value

    db.flush()
    record_audit(
        db,
        user.id,
        "criteria.save",
        "criteria_set",
        cset.id,
        {"job_id": job.id, "version": cset.version},
    )
    db.commit()
    db.refresh(cset)
    return CriteriaSetResponse.model_validate(cset)


@router.get("/api/jobs/{job_id}/estimate", response_model=EstimateResponse)
def estimate_job_run(
    job_id: str,
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> EstimateResponse:
    """Estimate token cost, duration, and external data status before starting a run."""
    job = _get_job_or_404(db, job_id)
    candidate_count = int(
        db.scalar(select(func.count(Candidate.id)).where(Candidate.job_id == job_id)) or 0
    )

    sends_external = False
    provider_label = "Local / Mock"
    if not is_fake_llm_enabled():
        profile = db.get(ModelProfile, job.profile_id) if job.profile_id else None
        if profile is None:
            profile = db.scalar(select(ModelProfile).order_by(ModelProfile.created_at.asc()))
        if profile is not None and profile.models:
            first_entry = ModelProfileEntry.model_validate(profile.models[0])
            sends_external = is_external_provider(ProviderType(first_entry.provider))
            provider_label = f"{first_entry.provider.value} ({first_entry.model})"

    cset = db.scalar(
        select(CriteriaSet)
        .where(CriteriaSet.job_id == job_id)
        .order_by(CriteriaSet.version.desc())
        .limit(1)
    )
    states = candidate_analysis_states(db, job_id, cset.version if cset else None)
    evaluated_count = sum(1 for st, _ in states.values() if st == "done")
    failed_count = sum(1 for st, _ in states.values() if st == "failed")
    pending_count = candidate_count - evaluated_count
    active_run_id = db.scalar(
        select(AnalysisRun.id)
        .where(
            AnalysisRun.job_id == job_id,
            AnalysisRun.status.in_([RunStatus.PENDING.value, RunStatus.RUNNING.value]),
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )

    # Conservative estimate for the CVs the next run will actually send:
    # ~2500 tokens per CV at ~$0.0005/CV for Flash-tier models, ~6s/CV
    # (LLM latency plus free-tier rate limits).
    estimated_cost = 0.0 if not sends_external else round(pending_count * 0.0005, 4)
    estimated_duration = pending_count * 6

    return EstimateResponse(
        job_id=job.id,
        candidate_count=candidate_count,
        duplicate_count=0,
        estimated_cost_usd=estimated_cost,
        estimated_duration_seconds=estimated_duration,
        sends_external_data=sends_external,
        provider_label=provider_label,
        pending_count=pending_count,
        evaluated_count=evaluated_count,
        failed_count=failed_count,
        criteria_count=len(cset.criteria) if cset else 0,
        criteria_version=cset.version if cset else None,
        active_run_id=active_run_id,
    )
