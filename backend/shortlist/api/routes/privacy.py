# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Privacy retention settings, manual/scheduled purge, audit logs, and usage logs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shortlist.api.auth import record_audit
from shortlist.api.deps import get_db_session, require_roles
from shortlist.api.schemas import (
    AuditLogResponse,
    PrivacySettingsResponse,
    PrivacySettingsUpdate,
    PurgeResultResponse,
    UsageLogResponse,
)
from shortlist.db.models import AuditLog, Candidate, Job, PrivacySetting, UsageLog, User
from shortlist.schemas.common import JobStatus, PaginatedResponse, UserRole

router = APIRouter(tags=["privacy"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _get_or_create_privacy_settings(db: Session) -> PrivacySetting:
    settings = db.get(PrivacySetting, "default")
    if settings is None:
        settings = PrivacySetting(
            id="default",
            anonymization_level="max",
            retention_days=180,
            auto_purge_enabled=True,
        )
        db.add(settings)
        db.flush()
    return settings


def execute_retention_purge(db: Session, retention_days: int) -> PurgeResultResponse:
    """Delete completed/archived jobs and their CVs older than retention_days."""
    cutoff = _utcnow() - timedelta(days=retention_days)
    expired_jobs = db.scalars(
        select(Job).where(
            Job.status.in_([JobStatus.COMPLETED.value, JobStatus.ARCHIVED.value]),
            Job.updated_at < cutoff,
        )
    ).all()

    deleted_jobs = 0
    deleted_candidates = 0
    deleted_files = 0

    for job in expired_jobs:
        candidates = db.scalars(select(Candidate).where(Candidate.job_id == job.id)).all()
        for cand in candidates:
            deleted_candidates += 1
            path = Path(cand.stored_path)
            if path.is_file():
                path.unlink(missing_ok=True)
                deleted_files += 1
        db.delete(job)
        deleted_jobs += 1

    return PurgeResultResponse(
        deleted_jobs=deleted_jobs,
        deleted_candidates=deleted_candidates,
        deleted_files=deleted_files,
    )


@router.get("/api/settings/privacy", response_model=PrivacySettingsResponse)
def get_privacy_settings(
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> PrivacySettingsResponse:
    """Return global privacy and retention settings."""
    settings = _get_or_create_privacy_settings(db)
    db.commit()
    return PrivacySettingsResponse.model_validate(settings)


@router.put("/api/settings/privacy", response_model=PrivacySettingsResponse)
def update_privacy_settings(
    payload: PrivacySettingsUpdate,
    user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
) -> PrivacySettingsResponse:
    """Update global privacy and retention settings (admin only)."""
    settings = _get_or_create_privacy_settings(db)
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(settings, field_name, value)

    record_audit(db, user.id, "privacy.update", "privacy_settings", "default", updates)
    db.commit()
    db.refresh(settings)
    return PrivacySettingsResponse.model_validate(settings)


@router.post("/api/settings/privacy/purge", response_model=PurgeResultResponse)
def purge_expired_data(
    user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
) -> PurgeResultResponse:
    """Manually trigger retention purge for expired completed/archived jobs (admin only)."""
    settings = _get_or_create_privacy_settings(db)
    result = execute_retention_purge(db, settings.retention_days)
    settings.last_purge_at = _utcnow()
    record_audit(
        db,
        user.id,
        "privacy.purge",
        "privacy_settings",
        "default",
        result.model_dump(),
    )
    db.commit()
    return result


@router.get("/api/audit-logs", response_model=PaginatedResponse[AuditLogResponse])
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
) -> PaginatedResponse[AuditLogResponse]:
    """List paginated audit log entries (admin only)."""
    total = int(db.scalar(select(func.count(AuditLog.id))) or 0)
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return PaginatedResponse[AuditLogResponse](
        items=[AuditLogResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/usage-logs", response_model=list[UsageLogResponse])
def list_usage_logs(
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> list[UsageLogResponse]:
    """List daily token and cost usage logs per API key."""
    rows = db.scalars(select(UsageLog).order_by(UsageLog.usage_date.desc())).all()
    return [UsageLogResponse.model_validate(r) for r in rows]
