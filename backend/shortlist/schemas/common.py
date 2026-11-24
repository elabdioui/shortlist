# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared enums and base response schemas."""

from enum import StrEnum

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Healthcheck response payload."""

    status: str = Field(default="ok", examples=["ok"])
    version: str = Field(examples=["0.1.0"])


class PaginatedResponse[T](BaseModel):
    """Standard paginated list wrapper."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class UserRole(StrEnum):
    """Application user roles."""

    ADMIN = "admin"
    RECRUITER = "recruiter"
    READER = "reader"


class ProviderType(StrEnum):
    """Supported LLM providers via LiteLLM."""

    OLLAMA = "ollama"
    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MISTRAL = "mistral"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    OPENAI_COMPATIBLE = "openai_compatible"


class KeyTier(StrEnum):
    """Billing tier of an API key."""

    FREE = "free"
    PAID = "paid"


class KeyStatus(StrEnum):
    """Operational status of an API key in the router pool."""

    ACTIVE = "active"
    PAUSED = "paused"
    COOLDOWN = "cooldown"
    INVALID = "invalid"


class RoutingStrategy(StrEnum):
    """Key selection strategy for a model profile."""

    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"
    LOWEST_COST = "lowest_cost"


class CriterionType(StrEnum):
    """Whether a screening criterion is mandatory or bonus."""

    MANDATORY = "mandatory"
    BONUS = "bonus"


class CriterionVerdict(StrEnum):
    """Evaluation verdict for a single criterion."""

    YES = "yes"
    PARTIAL = "partial"
    NO = "no"
    NOT_FOUND = "not_found"
    UNPROVEN = "unproven"


class Recommendation(StrEnum):
    """Deterministic recommendation derived from score and mandatory verdicts."""

    INTERVIEW = "interview"
    REVIEW = "review"
    NOT_RETAINED = "not_retained"
    MANUAL_REVIEW = "manual_review"


class HumanDecision(StrEnum):
    """Recruiter's final human decision on a candidate."""

    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    PENDING = "pending"


class ExtractionStatus(StrEnum):
    """Status of CV text extraction."""

    PENDING = "pending"
    EXTRACTED = "extracted"
    OCR_EXTRACTED = "ocr_extracted"
    FAILED = "failed"
    HIDDEN_TEXT_FLAGGED = "hidden_text_flagged"


class JobStatus(StrEnum):
    """Lifecycle status of a job posting."""

    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class RunStatus(StrEnum):
    """Lifecycle status of an analysis run."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED_BUDGET = "paused_budget"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
