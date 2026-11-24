# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""AI providers, encrypted API keys, key testing, and model profiles routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shortlist.api.auth import record_audit
from shortlist.api.crypto import decrypt_secret, encrypt_secret, mask_secret
from shortlist.api.deps import get_app_settings, get_db_session, require_roles
from shortlist.config import Settings
from shortlist.db.models import APIKey, ModelProfile, Provider, User
from shortlist.llm.pool import PooledKey
from shortlist.llm.router import check_api_key
from shortlist.schemas.common import KeyStatus, KeyTier, ProviderType, UserRole
from shortlist.schemas.providers import (
    APIKeyCreate,
    APIKeyResponse,
    APIKeyTestResult,
    APIKeyUpdate,
    ModelProfileCreate,
    ModelProfileResponse,
    ProviderCreate,
    ProviderResponse,
)
from shortlist.worker.fake_llm import is_fake_llm_enabled

router = APIRouter(tags=["providers"])


@router.get("/api/providers", response_model=list[ProviderResponse])
def list_providers(
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> list[ProviderResponse]:
    """List configured AI providers."""
    rows = db.scalars(select(Provider).order_by(Provider.created_at.asc())).all()
    return [ProviderResponse.model_validate(r) for r in rows]


@router.post(
    "/api/providers",
    response_model=ProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_provider(
    payload: ProviderCreate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> ProviderResponse:
    """Register an AI provider."""
    provider = Provider(
        type=payload.type.value,
        base_url=payload.base_url,
        active=payload.active,
    )
    db.add(provider)
    db.flush()
    record_audit(db, user.id, "provider.create", "provider", provider.id)
    db.commit()
    db.refresh(provider)
    return ProviderResponse.model_validate(provider)


@router.get("/api/keys", response_model=list[APIKeyResponse])
def list_keys(
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> list[APIKeyResponse]:
    """List API keys with masked secrets only."""
    rows = db.scalars(select(APIKey).order_by(APIKey.priority.asc(), APIKey.created_at.asc())).all()
    return [APIKeyResponse.model_validate(r) for r in rows]


@router.post(
    "/api/keys",
    response_model=APIKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_key(
    payload: APIKeyCreate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> APIKeyResponse:
    """Encrypt and store a new API key in the router pool."""
    provider = db.get(Provider, payload.provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")

    key = APIKey(
        provider_id=payload.provider_id,
        label=payload.label,
        encrypted_secret=encrypt_secret(payload.secret, settings.secret_key),
        masked_secret=mask_secret(payload.secret),
        allowed_models=list(payload.allowed_models),
        priority=payload.priority,
        tier=payload.tier.value,
        rpm_limit=payload.rpm_limit,
        tpm_limit=payload.tpm_limit,
        rpd_limit=payload.rpd_limit,
        monthly_budget_usd=payload.monthly_budget_usd,
        concurrency=payload.concurrency,
    )
    db.add(key)
    db.flush()
    record_audit(db, user.id, "key.create", "api_key", key.id, {"label": key.label})
    db.commit()
    db.refresh(key)
    return APIKeyResponse.model_validate(key)


@router.patch("/api/keys/{key_id}", response_model=APIKeyResponse)
def update_key(
    key_id: str,
    payload: APIKeyUpdate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> APIKeyResponse:
    """Update API key metadata, limits, priority, or status."""
    key = db.get(APIKey, key_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")

    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        if field_name in ("tier", "status") and value is not None:
            setattr(key, field_name, value.value)
        else:
            setattr(key, field_name, value)

    if payload.status is not None and payload.status.value == "active":
        key.cooldown_until = None

    record_audit(db, user.id, "key.update", "api_key", key.id)
    db.commit()
    db.refresh(key)
    return APIKeyResponse.model_validate(key)


@router.delete("/api/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(
    key_id: str,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> None:
    """Delete an API key from the pool."""
    key = db.get(APIKey, key_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    record_audit(db, user.id, "key.delete", "api_key", key.id, {"label": key.label})
    db.delete(key)
    db.commit()


@router.post("/api/keys/{key_id}/test", response_model=APIKeyTestResult)
def test_key(
    key_id: str,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> APIKeyTestResult:
    """Test an API key with a minimal LLM call (or deterministic mock in SHORTLIST_FAKE_LLM=1)."""
    key = db.get(APIKey, key_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    provider = db.get(Provider, key.provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")

    record_audit(db, user.id, "key.test", "api_key", key.id)
    db.commit()

    if is_fake_llm_enabled():
        model_name = key.allowed_models[0] if key.allowed_models else "fake-deterministic-v1"
        return APIKeyTestResult(ok=True, model=model_name, latency_ms=1)

    raw_secret = decrypt_secret(key.encrypted_secret, settings.secret_key)
    selected_model: str | None = key.allowed_models[0] if key.allowed_models else None
    pooled = PooledKey(
        id=key.id,
        provider=ProviderType(provider.type),
        label=key.label,
        api_key=raw_secret,
        base_url=provider.base_url,
        allowed_models=list(key.allowed_models or []),
        priority=key.priority,
        tier=KeyTier(key.tier),
        status=KeyStatus(key.status),
    )
    return check_api_key(pooled, model=selected_model)


@router.get("/api/profiles", response_model=list[ModelProfileResponse])
def list_profiles(
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> list[ModelProfileResponse]:
    """List configured model profiles."""
    rows = db.scalars(select(ModelProfile).order_by(ModelProfile.created_at.asc())).all()
    return [ModelProfileResponse.model_validate(r) for r in rows]


@router.post(
    "/api/profiles",
    response_model=ModelProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    payload: ModelProfileCreate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> ModelProfileResponse:
    """Create a model fallback profile."""
    if db.scalar(select(ModelProfile).where(ModelProfile.name == payload.name)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A model profile with this name already exists.",
        )

    profile = ModelProfile(
        name=payload.name,
        strategy=payload.strategy.value,
        models=[m.model_dump(mode="json") for m in payload.models],
    )
    db.add(profile)
    db.flush()
    record_audit(db, user.id, "profile.create", "model_profile", profile.id)
    db.commit()
    db.refresh(profile)
    return ModelProfileResponse.model_validate(profile)
