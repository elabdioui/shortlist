# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SQLAlchemy 2.0 ORM models for all Shortlist database tables."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shortlist.db.base import Base, new_uuid, utcnow
from shortlist.schemas.common import (
    ExtractionStatus,
    HumanDecision,
    JobStatus,
    KeyStatus,
    KeyTier,
    ProviderType,
    Recommendation,
    RoutingStrategy,
    RunStatus,
    UserRole,
)


class User(Base):
    """Application user account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=UserRole.RECRUITER.value)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="fr")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Provider(Base):
    """Configured AI provider."""

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default=ProviderType.GEMINI.value)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    api_keys: Mapped[list["APIKey"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )


class APIKey(Base):
    """Encrypted API key in the provider router pool."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    masked_secret: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_models: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default=KeyTier.PAID.value)
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpd_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=KeyStatus.ACTIVE.value)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    provider: Mapped["Provider"] = relationship(back_populates="api_keys")


class ModelProfile(Base):
    """Ordered model fallback chain and routing strategy."""

    __tablename__ = "model_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    strategy: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RoutingStrategy.PRIORITY.value
    )
    models: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    """Recruitment job posting and screening configuration."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("model_profiles.id", ondelete="SET NULL"), nullable=True
    )
    interview_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=70.0)
    review_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=45.0)
    max_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobStatus.DRAFT.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    criteria_sets: Mapped[list["CriteriaSet"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class CriteriaSet(Base):
    """Versioned screening criteria grid for a job."""

    __tablename__ = "criteria_sets"
    __table_args__ = (UniqueConstraint("job_id", "version", name="uq_criteria_job_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped["Job"] = relationship(back_populates="criteria_sets")


class Candidate(Base):
    """Uploaded CV file and its extracted/anonymized representations."""

    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    anonymized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_pii_map: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExtractionStatus.PENDING.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped["Job"] = relationship(back_populates="candidates")
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["Decision"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class Evaluation(Base):
    """LLM evaluation output, verified quotes, and deterministic score."""

    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "criteria_set_version", name="uq_evaluation_candidate_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criteria_set_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    verified_verdicts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(
        String(32), nullable=False, default=Recommendation.REVIEW.value
    )
    formula_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="evaluations")


class Decision(Base):
    """Human recruiter decision and optional verdict overrides."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(
        String(32), nullable=False, default=HumanDecision.PENDING.value
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict_overrides: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="decisions")


class AnalysisRun(Base):
    """Persistent batch analysis run for crash recovery and SSE progress."""

    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RunStatus.PENDING.value)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cumulative_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped["Job"] = relationship(back_populates="analysis_runs")


class UsageLog(Base):
    """Daily token and cost ledger per API key."""

    __tablename__ = "usage_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    api_key_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True
    )
    usage_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class AuditLog(Base):
    """Audit trail for views, exports, and deletions."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisTask(Base):
    """DB-backed worker queue item for crash-resumable CV evaluation."""

    __tablename__ = "analysis_tasks"
    __table_args__ = (UniqueConstraint("run_id", "candidate_id", name="uq_task_run_candidate"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    leased_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PrivacySetting(Base):
    """Global privacy and data retention settings."""

    __tablename__ = "privacy_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    anonymization_level: Mapped[str] = mapped_column(String(16), nullable=False, default="max")
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    auto_purge_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_purge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
