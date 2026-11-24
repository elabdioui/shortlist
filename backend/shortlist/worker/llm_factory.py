# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Build and refresh a shared LLMClient/KeyPool for evaluation and criteria generation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shortlist.api.crypto import decrypt_secret
from shortlist.db.models import APIKey, Job, ModelProfile, Provider, UsageLog
from shortlist.llm.client import LLMClient
from shortlist.llm.pool import KeyPool, PooledKey, utcnow
from shortlist.llm.router import LLMRouter
from shortlist.schemas.common import KeyStatus, KeyTier, ProviderType, RoutingStrategy
from shortlist.schemas.providers import ModelProfileEntry
from shortlist.worker.fake_llm import build_deterministic_fake_llm, is_fake_llm_enabled


def _current_month_spend(db: Session, api_key_id: str, now: datetime) -> float:
    month_prefix = now.strftime("%Y-%m")
    total = db.scalar(
        select(func.coalesce(func.sum(UsageLog.cost_usd), 0.0)).where(
            UsageLog.api_key_id == api_key_id,
            UsageLog.usage_date.like(f"{month_prefix}%"),
        )
    )
    return float(total or 0.0)


def _today_request_count(db: Session, api_key_id: str, now: datetime) -> int:
    today = now.strftime("%Y-%m-%d")
    total = db.scalar(
        select(func.coalesce(func.sum(UsageLog.requests), 0)).where(
            UsageLog.api_key_id == api_key_id,
            UsageLog.usage_date == today,
        )
    )
    return int(total or 0)


def _load_pooled_keys(
    db: Session,
    secret_key: str,
    now: datetime,
) -> tuple[list[PooledKey], dict[str, int]]:
    rows = db.execute(
        select(APIKey, Provider)
        .join(Provider, APIKey.provider_id == Provider.id)
        .where(Provider.active.is_(True))
    ).all()

    pooled_keys: list[PooledKey] = []
    daily_counts: dict[str, int] = {}
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
                monthly_spend_usd=_current_month_spend(db, key_row.id, now),
            )
        )
        daily_counts[key_row.id] = _today_request_count(db, key_row.id, now)
    return pooled_keys, daily_counts


def build_key_pool_from_db(
    db: Session,
    secret_key: str,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> KeyPool:
    """Load active providers and encrypted API keys into a KeyPool, restoring daily RPD."""
    now = clock()
    pooled_keys, daily_counts = _load_pooled_keys(db, secret_key, now)
    pool = KeyPool(pooled_keys, clock=clock)
    for key_id, count in daily_counts.items():
        if count > 0:
            pool.initialize_daily_count(key_id, count)
    return pool


def refresh_key_pool_from_db(
    db: Session,
    pool: KeyPool,
    secret_key: str,
    *,
    now: datetime | None = None,
) -> None:
    """Refresh an existing shared KeyPool from DB while preserving live counters."""
    current = now or datetime.now(UTC)
    pooled_keys, _daily_counts = _load_pooled_keys(db, secret_key, current)
    pool.refresh_keys(pooled_keys)


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
    shared_pool: KeyPool | None = None,
) -> tuple[LLMClient, KeyPool | None, str]:
    """Return (LLMClient, optional KeyPool, primary_model_name) for a job or global default."""
    if force_fake or is_fake_llm_enabled():
        return build_deterministic_fake_llm(), None, "fake-deterministic-v1"

    pool = shared_pool if shared_pool is not None else build_key_pool_from_db(db, secret_key)
    profile_row: ModelProfile | None = None
    if job is not None and job.profile_id:
        profile_row = db.get(ModelProfile, job.profile_id)
    if profile_row is None:
        profile_row = db.scalar(select(ModelProfile).order_by(ModelProfile.created_at.asc()))

    if profile_row is not None and profile_row.models:
        entries = [ModelProfileEntry.model_validate(m) for m in profile_row.models]
        strategy = RoutingStrategy(profile_row.strategy)
    else:
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
