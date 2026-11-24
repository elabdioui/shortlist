# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Thread-safe API key pool, local quota counters, and routing strategies."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from shortlist.schemas.common import KeyStatus, KeyTier, ProviderType, RoutingStrategy

BASE_COOLDOWN_SECONDS = 30
MAX_COOLDOWN_SECONDS = 480


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


@dataclass
class PooledKey:
    """Runtime representation of an API key in the router pool."""

    id: str
    provider: ProviderType
    label: str
    api_key: str = field(repr=False)
    base_url: str | None = None
    allowed_models: list[str] = field(default_factory=list)
    priority: int = 1
    tier: KeyTier = KeyTier.PAID
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    rpd_limit: int | None = None
    monthly_budget_usd: float | None = None
    concurrency: int = 4
    status: KeyStatus = KeyStatus.ACTIVE
    cooldown_until: datetime | None = None
    consecutive_429s: int = 0
    monthly_spend_usd: float = 0.0

    def supports_model(self, model: str) -> bool:
        """Return True if this key is permitted to call the given model."""
        if not self.allowed_models:
            return True
        return model in self.allowed_models


@dataclass
class _KeyCounters:
    """Sliding-window RPM/TPM, daily RPD, and in-flight concurrency counters."""

    minute_requests: deque[datetime] = field(default_factory=deque)
    minute_tokens: deque[tuple[datetime, int]] = field(default_factory=deque)
    daily_date: str = ""
    daily_requests: int = 0
    in_flight: int = 0

    def prune(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=60)
        while self.minute_requests and self.minute_requests[0] <= cutoff:
            self.minute_requests.popleft()
        while self.minute_tokens and self.minute_tokens[0][0] <= cutoff:
            self.minute_tokens.popleft()
        today = now.strftime("%Y-%m-%d")
        if self.daily_date != today:
            self.daily_date = today
            self.daily_requests = 0

    def current_rpm(self, now: datetime) -> int:
        self.prune(now)
        return len(self.minute_requests)

    def current_tpm(self, now: datetime) -> int:
        self.prune(now)
        return sum(tokens for _, tokens in self.minute_tokens)

    def current_rpd(self, now: datetime) -> int:
        self.prune(now)
        return self.daily_requests


class KeyPool:
    """Manages API keys, local rate/budget counters, cooldowns, and selection strategies."""

    def __init__(
        self,
        keys: list[PooledKey] | None = None,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._keys: dict[str, PooledKey] = {}
        self._counters: dict[str, _KeyCounters] = {}
        self._rr_cursors: dict[tuple[ProviderType, str], int] = {}
        self._lock = threading.Lock()
        self._clock = clock
        for key in keys or []:
            self.add_key(key)

    def now(self) -> datetime:
        """Return the pool clock's current time."""
        return self._clock()

    def add_key(self, key: PooledKey) -> None:
        """Register or replace a key in the pool."""
        with self._lock:
            self._keys[key.id] = key
            self._counters.setdefault(key.id, _KeyCounters())

    def get_key(self, key_id: str) -> PooledKey | None:
        """Return a key by ID if present."""
        with self._lock:
            return self._keys.get(key_id)

    def list_keys(self) -> list[PooledKey]:
        """Return all keys currently in the pool."""
        with self._lock:
            return list(self._keys.values())

    def _is_eligible_locked(
        self,
        key: PooledKey,
        model: str,
        estimated_tokens: int,
        now: datetime,
    ) -> bool:
        if not key.supports_model(model):
            return False

        if key.status == KeyStatus.INVALID or key.status == KeyStatus.PAUSED:
            return False

        if key.status == KeyStatus.COOLDOWN:
            if key.cooldown_until is not None and now < key.cooldown_until:
                return False
            key.status = KeyStatus.ACTIVE
            key.cooldown_until = None

        if key.monthly_budget_usd is not None and key.monthly_spend_usd >= key.monthly_budget_usd:
            return False

        counters = self._counters[key.id]
        if counters.in_flight >= key.concurrency:
            return False

        if key.rpm_limit is not None and counters.current_rpm(now) >= key.rpm_limit:
            return False

        if (
            key.tpm_limit is not None
            and counters.current_tpm(now) + estimated_tokens > key.tpm_limit
        ):
            return False

        return not (key.rpd_limit is not None and counters.current_rpd(now) >= key.rpd_limit)

    def select_candidates(
        self,
        provider: ProviderType,
        model: str,
        *,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
        estimated_tokens: int = 0,
        cost_fn: Callable[[ProviderType, str], float] | None = None,
    ) -> list[PooledKey]:
        """Return eligible keys for (provider, model) ordered by routing strategy."""
        with self._lock:
            now = self._clock()
            eligible = [
                k
                for k in self._keys.values()
                if k.provider == provider
                and self._is_eligible_locked(k, model, estimated_tokens, now)
            ]
            if not eligible:
                return []

            if strategy == RoutingStrategy.PRIORITY:
                return sorted(eligible, key=lambda k: (k.priority, k.id))

            if strategy == RoutingStrategy.ROUND_ROBIN:
                ordered = sorted(eligible, key=lambda k: (k.priority, k.id))
                cursor_key = (provider, model)
                idx = self._rr_cursors.get(cursor_key, 0) % len(ordered)
                self._rr_cursors[cursor_key] = idx + 1
                return ordered[idx:] + ordered[:idx]

            if strategy == RoutingStrategy.LOWEST_COST:
                unit_cost = cost_fn(provider, model) if cost_fn else 0.0
                return sorted(
                    eligible,
                    key=lambda k: (0 if k.tier == KeyTier.FREE else 1, unit_cost, k.priority, k.id),
                )

            return sorted(eligible, key=lambda k: (k.priority, k.id))

    def retry_hint_seconds(
        self,
        provider: ProviderType,
        model: str,
        estimated_tokens: int = 0,
    ) -> float | None:
        """Return seconds until a currently-ineligible key may become usable again.

        Only *temporary* blockers count: concurrency slots in use, per-minute
        RPM/TPM windows, and cooldowns after a 429. Permanent blockers (invalid
        or paused key, unsupported model, exhausted daily quota or monthly
        budget) return no hint. ``None`` means no key for this (provider, model)
        will recover soon, so waiting or requeueing is pointless.
        """
        with self._lock:
            now = self._clock()
            hints: list[float] = []
            for key in self._keys.values():
                if key.provider != provider or not key.supports_model(model):
                    continue
                if key.status in (KeyStatus.INVALID, KeyStatus.PAUSED):
                    continue
                if (
                    key.monthly_budget_usd is not None
                    and key.monthly_spend_usd >= key.monthly_budget_usd
                ):
                    continue
                counters = self._counters[key.id]
                if key.rpd_limit is not None and counters.current_rpd(now) >= key.rpd_limit:
                    continue

                wait = 0.0
                if (
                    key.status == KeyStatus.COOLDOWN
                    and key.cooldown_until is not None
                    and now < key.cooldown_until
                ):
                    wait = max(wait, (key.cooldown_until - now).total_seconds())
                if key.rpm_limit is not None and counters.current_rpm(now) >= key.rpm_limit:
                    oldest = counters.minute_requests[0]
                    wait = max(wait, 60.0 - (now - oldest).total_seconds())
                if (
                    key.tpm_limit is not None
                    and counters.minute_tokens
                    and counters.current_tpm(now) + estimated_tokens > key.tpm_limit
                ):
                    oldest_tok = counters.minute_tokens[0][0]
                    wait = max(wait, 60.0 - (now - oldest_tok).total_seconds())
                if counters.in_flight >= key.concurrency:
                    # A slot frees up when an in-flight call returns: poll soon.
                    wait = max(wait, 1.0)
                hints.append(max(1.0, wait))
            return min(hints) if hints else None

    def is_slot_contended(self, provider: ProviderType, model: str) -> bool:
        """Return True if some key is blocked *only* because all its slots are in flight."""
        with self._lock:
            now = self._clock()
            for key in self._keys.values():
                if key.provider != provider:
                    continue
                counters = self._counters[key.id]
                if counters.in_flight < key.concurrency:
                    continue
                counters.in_flight -= 1
                try:
                    if self._is_eligible_locked(key, model, 0, now):
                        return True
                finally:
                    counters.in_flight += 1
            return False

    def initialize_daily_count(self, key_id: str, count: int) -> None:
        """Initialize the daily request counter from persisted UsageLog at startup."""
        with self._lock:
            now = self._clock()
            counters = self._counters.setdefault(key_id, _KeyCounters())
            counters.prune(now)
            counters.daily_requests = max(counters.daily_requests, count)

    def refresh_keys(self, keys: list[PooledKey]) -> None:
        """Refresh key metadata from DB while preserving live counters and active cooldowns."""
        with self._lock:
            now = self._clock()
            incoming_ids = {k.id for k in keys}
            for existing_id in list(self._keys.keys()):
                if existing_id not in incoming_ids:
                    self._keys.pop(existing_id, None)
                    self._counters.pop(existing_id, None)

            for incoming in keys:
                prev = self._keys.get(incoming.id)
                if prev is not None:
                    incoming.consecutive_429s = prev.consecutive_429s
                    if (
                        prev.status == KeyStatus.COOLDOWN
                        and prev.cooldown_until is not None
                        and now < prev.cooldown_until
                        and incoming.status == KeyStatus.ACTIVE
                    ):
                        incoming.status = KeyStatus.COOLDOWN
                        incoming.cooldown_until = prev.cooldown_until
                self._keys[incoming.id] = incoming
                self._counters.setdefault(incoming.id, _KeyCounters())

    def try_acquire(self, key_id: str, model: str, estimated_tokens: int = 0) -> bool:
        """Atomically verify eligibility and increment concurrency/RPM/RPD counters."""
        with self._lock:
            key = self._keys.get(key_id)
            if key is None:
                return False
            now = self._clock()
            if not self._is_eligible_locked(key, model, estimated_tokens, now):
                return False
            counters = self._counters[key_id]
            counters.prune(now)
            counters.in_flight += 1
            counters.minute_requests.append(now)
            counters.daily_requests += 1
            return True

    def acquire(self, key_id: str) -> None:
        """Increment in-flight concurrency and RPM/RPD counters before a request."""
        with self._lock:
            now = self._clock()
            counters = self._counters[key_id]
            counters.prune(now)
            counters.in_flight += 1
            counters.minute_requests.append(now)
            counters.daily_requests += 1

    def release(
        self,
        key_id: str,
        *,
        total_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Decrement in-flight concurrency and record token/cost usage."""
        with self._lock:
            now = self._clock()
            counters = self._counters[key_id]
            counters.in_flight = max(0, counters.in_flight - 1)
            if total_tokens > 0:
                counters.minute_tokens.append((now, total_tokens))
            key = self._keys.get(key_id)
            if key is not None and cost_usd > 0.0:
                key.monthly_spend_usd = round(key.monthly_spend_usd + cost_usd, 8)

    def mark_success(self, key_id: str) -> None:
        """Reset consecutive 429 counter after a successful request."""
        with self._lock:
            key = self._keys.get(key_id)
            if key is not None:
                key.consecutive_429s = 0
                key.status = KeyStatus.ACTIVE
                key.cooldown_until = None

    def mark_cooldown(self, key_id: str, retry_after_seconds: float | None = None) -> datetime:
        """Put a key into cooldown using Retry-After or exponential backoff."""
        with self._lock:
            now = self._clock()
            key = self._keys[key_id]
            if retry_after_seconds is not None and retry_after_seconds > 0:
                delay = retry_after_seconds
            else:
                delay = min(
                    MAX_COOLDOWN_SECONDS,
                    BASE_COOLDOWN_SECONDS * (2 ** min(key.consecutive_429s, 4)),
                )
            key.consecutive_429s += 1
            key.status = KeyStatus.COOLDOWN
            key.cooldown_until = now + timedelta(seconds=delay)
            return key.cooldown_until

    def mark_invalid(self, key_id: str) -> None:
        """Mark a key as invalid (401/403) so it is never reused without human action."""
        with self._lock:
            key = self._keys.get(key_id)
            if key is not None:
                key.status = KeyStatus.INVALID
                key.cooldown_until = None
