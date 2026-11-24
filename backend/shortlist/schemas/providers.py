# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""AI provider, API key, and model profile schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shortlist.schemas.common import KeyStatus, KeyTier, ProviderType, RoutingStrategy


class ProviderCreate(BaseModel):
    """Payload to register an AI provider."""

    type: ProviderType
    base_url: str | None = Field(default=None, max_length=512)
    active: bool = True


class ProviderResponse(BaseModel):
    """Public provider representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: ProviderType
    base_url: str | None
    active: bool


class APIKeyCreate(BaseModel):
    """Payload to add an encrypted API key to the pool."""

    provider_id: str
    label: str = Field(min_length=1, max_length=100)
    secret: str = Field(min_length=1, max_length=512)
    allowed_models: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=1, le=100)
    tier: KeyTier = KeyTier.PAID
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    rpd_limit: int | None = Field(default=None, ge=1)
    monthly_budget_usd: float | None = Field(default=None, ge=0.0)
    concurrency: int = Field(default=4, ge=1, le=32)


class APIKeyUpdate(BaseModel):
    """Partial update for an existing API key."""

    label: str | None = Field(default=None, min_length=1, max_length=100)
    allowed_models: list[str] | None = None
    priority: int | None = Field(default=None, ge=1, le=100)
    tier: KeyTier | None = None
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    rpd_limit: int | None = Field(default=None, ge=1)
    monthly_budget_usd: float | None = Field(default=None, ge=0.0)
    concurrency: int | None = Field(default=None, ge=1, le=32)
    status: KeyStatus | None = None


class APIKeyResponse(BaseModel):
    """Public API key representation (masked secret only, never raw)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_id: str
    label: str
    masked_secret: str
    allowed_models: list[str]
    priority: int
    tier: KeyTier
    rpm_limit: int | None
    tpm_limit: int | None
    rpd_limit: int | None
    monthly_budget_usd: float | None
    concurrency: int
    status: KeyStatus
    cooldown_until: datetime | None


class APIKeyTestResult(BaseModel):
    """Result of testing an API key with a minimal LLM call."""

    ok: bool
    model: str | None = None
    latency_ms: int | None = None
    error: str | None = None


class ModelProfileEntry(BaseModel):
    """Single provider+model step in a fallback chain."""

    provider: ProviderType
    model: str = Field(min_length=1, max_length=128)


class ModelProfileCreate(BaseModel):
    """Payload to create a model profile."""

    name: str = Field(min_length=1, max_length=100)
    strategy: RoutingStrategy = RoutingStrategy.PRIORITY
    models: list[ModelProfileEntry] = Field(min_length=1)


class ModelProfileResponse(BaseModel):
    """Public model profile representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    strategy: RoutingStrategy
    models: list[ModelProfileEntry]
