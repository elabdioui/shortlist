# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Test-first suite for P1-1 thread-safe KeyPool, atomic try_acquire, and DB refresh."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from shortlist.llm.pool import KeyPool, PooledKey
from shortlist.schemas.common import KeyStatus, ProviderType


class _FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 24, 15, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def test_p1_1_concurrent_rpm_limit_enforced_across_threads() -> None:
    clock = _FakeClock()
    key = PooledKey(
        id="k1",
        provider=ProviderType.GEMINI,
        label="Primary",
        api_key="secret-1",
        rpm_limit=2,
        concurrency=4,
    )
    pool = KeyPool([key], clock=clock)

    def worker_attempt(_idx: int) -> bool:
        acquired = pool.try_acquire("k1", "gemini-2.0-flash", estimated_tokens=10)
        if acquired:
            pool.release("k1", total_tokens=10, cost_usd=0.001)
        return acquired

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(worker_attempt, range(6)))

    assert sum(1 for r in results if r) == 2

    # Advance past 60s window -> 2 more requests allowed
    clock.advance(61)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results_after = list(executor.map(worker_attempt, range(4)))
    assert sum(1 for r in results_after if r) == 2


def test_p1_1_refresh_keys_preserves_live_counters_and_daily_init() -> None:
    clock = _FakeClock()
    key = PooledKey(
        id="k1",
        provider=ProviderType.OPENAI,
        label="Key 1",
        api_key="secret-1",
        rpm_limit=5,
        rpd_limit=10,
    )
    pool = KeyPool([key], clock=clock)
    pool.initialize_daily_count("k1", 8)
    assert pool.try_acquire("k1", "gpt-4o-mini", estimated_tokens=10) is True
    pool.release("k1", total_tokens=10, cost_usd=0.0)

    # Refresh from DB with updated priority/label; live daily count (9) must be preserved
    updated = PooledKey(
        id="k1",
        provider=ProviderType.OPENAI,
        label="Key 1 Renamed",
        api_key="secret-1",
        priority=2,
        rpm_limit=5,
        rpd_limit=10,
    )
    pool.refresh_keys([updated])

    refreshed = pool.get_key("k1")
    assert refreshed is not None
    assert refreshed.label == "Key 1 Renamed"
    assert refreshed.status == KeyStatus.ACTIVE

    # 10th request succeeds, 11th is blocked by rpd_limit=10
    assert pool.try_acquire("k1", "gpt-4o-mini", estimated_tokens=10) is True
    pool.release("k1", total_tokens=10, cost_usd=0.0)
    assert pool.try_acquire("k1", "gpt-4o-mini", estimated_tokens=10) is False
