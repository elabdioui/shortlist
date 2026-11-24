# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Build an LLMClient (FakeLLMClient or DB-backed LLMRouter) for evaluation and criteria gen."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shortlist.db.models import APIKey, Job, ModelProfile, Provider, UsageLog
from shortlist.llm.client import LLMClient
from shortlist.llm.pool import KeyPool, PooledKey
from shortlist.llm.router import LLMRouter
from shortlist.schemas.common import KeyStatus, KeyTier, ProviderType, RoutingStrategy
from shortlist.schemas.providers import ModelProfileEntry
from shortlist.worker.fake_llm import build_deterministic_fake_llm, is_fake_llm_enabled


def _current_month_spend(db: Session, api_key_id: str) -> float:
    month_prefix = datetime.now(UTC).strftime("%Y-%m")
    total = db.scalar(
        select(func.coalesce(func.sum(UsageLog.cost_usd), 0.0)).where(
            UsageLog.api_key_id == api_key_id,
            UsageLog.usage_date.like(f"{month_prefix}%"),
        )
    )
    return float(total or 0.0)


def build_key_pool_from_db(db: Session, secret_key: str) -> KeyPool:
    """Load active providers and encrypted API keys from the database into a KeyPool."""
    from shortlist.api.crypto import decrypt_secret

    rows = db.execute(
        select(APIKey, Provider)
        .join(Provider, APIKey.provider_id == Provider.id)
        .where(Provider.active.is_(True))
    ).all()

    pooled_keys: list[PooledKey] = []
    for key_row, provider_row in rows:
        raw_secret = decrypt_secret(key_row.encrypted_secret, secret_key)
        pooled_keys.append(
            PooledKey(
                id=key_row.id,
                provider=ProviderType(provider_row.type),
                label=key_row.label,
                api_key=raw_secret,
                base_url=provider_row.base_url,
                allowed_models=list(key_row.allowed_models or []),
                priority=key_row.priority,
                tier=KeyTier(key_row.tier),
                rpm_limit=key_row.rpm_limit,
                tpm_limit=key_row.tpm_limit,
                rpd_limit=key_row.rpd_limit,
                monthly_budget_usd=key_row.monthly_budget_usd,
                concurrency=key_row.concurrency,
                status=KeyStatus(key_row.status),
                cooldown_until=key_row.cooldown_until,
                monthly_spend_usd=_current_month_spend(db, key_row.id),
            )
        )
    return KeyPool(pooled_keys)


def sync_pool_states_to_db(db: Session, pool: KeyPool) -> None:
    """Persist any cooldown or invalidation updates from KeyPool back to APIKey rows."""
    for pooled in pool.list_keys():
        key_row = db.get(APIKey, pooled.id)
        if key_row is None:
            continue
        if key_row.status != pooled.status.value or key_row.cooldown_until != pooled.cooldown_until:
            key_row.status = pooled.status.value
            key_row.cooldown_until = pooled.cooldown_until


def build_llm_client_for_job(
    db: Session,
    job: Job | None,
    secret_key: str,
    *,
    force_fake: bool = False,
    remaining_budget_usd: float | None = None,
) -> tuple[LLMClient, KeyPool | None, str]:
    """Return (LLMClient, optional KeyPool, primary_model_name) for a job or global default."""
    if force_fake or is_fake_llm_enabled():
        return build_deterministic_fake_llm(), None, "fake-deterministic-v1"

    pool = build_key_pool_from_db(db, secret_key)
    profile_row: ModelProfile | None = None
    if job is not None and job.profile_id:
        profile_row = db.get(ModelProfile, job.profile_id)
    if profile_row is None:
        profile_row = db.scalar(select(ModelProfile).order_by(ModelProfile.created_at.asc()))

    if profile_row is not None and profile_row.models:
        entries = [ModelProfileEntry.model_validate(m) for m in profile_row.models]
        strategy = RoutingStrategy(profile_row.strategy)
    else:
        # Fallback: construct a single-step profile from the first active key's provider.
        keys = pool.list_keys()
        if not keys:
            raise RuntimeError("No active AI provider keys or model profiles configured.")
        first_key = keys[0]
        default_model = first_key.allowed_models[0] if first_key.allowed_models else "gpt-4o-mini"
        entries = [ModelProfileEntry(provider=first_key.provider, model=default_model)]
        strategy = RoutingStrategy.PRIORITY

    router = LLMRouter(
        pool=pool,
        profile=entries,
        strategy=strategy,
        job_budget_remaining_usd=remaining_budget_usd,
    )
    return router, pool, entries[0].model
