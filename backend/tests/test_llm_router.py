# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the multi-key LiteLLM router, quota counters, error handling, and VCR cassettes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from shortlist.core.evaluate import evaluate_cv
from shortlist.core.scoring import score_candidate
from shortlist.llm import (
    AllKeysExhaustedError,
    BudgetExceededError,
    KeyPool,
    LLMMessage,
    LLMRequest,
    LLMRouter,
    PooledKey,
    check_api_key,
    format_litellm_model,
    is_external_provider,
)
from shortlist.schemas.common import (
    CriterionType,
    KeyStatus,
    KeyTier,
    ProviderType,
    Recommendation,
    RoutingStrategy,
)
from shortlist.schemas.jobs import CriterionItem
from shortlist.schemas.providers import ModelProfileEntry

CASSETTES_DIR = Path(__file__).resolve().parent / "cassettes"


class _FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class _HTTPStatusError(RuntimeError):
    def __init__(
        self, message: str, status_code: int, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}


def _ok_completion(
    content: str = '{"ok": true}', in_tok: int = 10, out_tok: int = 5
) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": in_tok, "completion_tokens": out_tok},
    }


def _make_key(
    key_id: str,
    *,
    provider: ProviderType = ProviderType.GEMINI,
    priority: int = 1,
    tier: KeyTier = KeyTier.PAID,
    rpm_limit: int | None = None,
    tpm_limit: int | None = None,
    rpd_limit: int | None = None,
    monthly_budget_usd: float | None = None,
    allowed_models: list[str] | None = None,
) -> PooledKey:
    return PooledKey(
        id=key_id,
        provider=provider,
        label=f"Key {key_id}",
        api_key=f"secret-{key_id}",
        priority=priority,
        tier=tier,
        rpm_limit=rpm_limit,
        tpm_limit=tpm_limit,
        rpd_limit=rpd_limit,
        monthly_budget_usd=monthly_budget_usd,
        allowed_models=allowed_models or [],
    )


def test_provider_formatting_and_privacy_classification() -> None:
    assert format_litellm_model(ProviderType.OLLAMA, "llama3.2") == "ollama/llama3.2"
    assert (
        format_litellm_model(ProviderType.GEMINI, "gemini-2.0-flash") == "gemini/gemini-2.0-flash"
    )
    assert (
        format_litellm_model(ProviderType.GEMINI, "gemini/gemini-2.0-flash")
        == "gemini/gemini-2.0-flash"
    )
    assert format_litellm_model(ProviderType.OPENAI, "gpt-4o-mini") == "openai/gpt-4o-mini"
    assert (
        format_litellm_model(ProviderType.ANTHROPIC, "claude-3-5-haiku-latest")
        == "anthropic/claude-3-5-haiku-latest"
    )
    assert (
        format_litellm_model(ProviderType.MISTRAL, "mistral-small-latest")
        == "mistral/mistral-small-latest"
    )
    assert (
        format_litellm_model(ProviderType.GROQ, "llama-3.1-8b-instant")
        == "groq/llama-3.1-8b-instant"
    )
    assert (
        format_litellm_model(ProviderType.OPENROUTER, "meta-llama/llama-3-8b")
        == "openrouter/meta-llama/llama-3-8b"
    )
    assert (
        format_litellm_model(ProviderType.OPENAI_COMPATIBLE, "local-model") == "openai/local-model"
    )

    assert is_external_provider(ProviderType.OLLAMA) is False
    assert is_external_provider(ProviderType.OPENAI_COMPATIBLE, "http://localhost:1234/v1") is False
    assert (
        is_external_provider(ProviderType.OPENAI_COMPATIBLE, "https://api.example.com/v1") is True
    )
    assert is_external_provider(ProviderType.GEMINI) is True


def test_routing_strategies_priority_round_robin_cheapest() -> None:
    k1 = _make_key("k1", priority=1, tier=KeyTier.PAID)
    k2 = _make_key("k2", priority=2, tier=KeyTier.FREE)
    pool = KeyPool([k1, k2])

    prio = pool.select_candidates(
        ProviderType.GEMINI, "gemini-2.0-flash", strategy=RoutingStrategy.PRIORITY
    )
    assert [k.id for k in prio] == ["k1", "k2"]

    rr1 = pool.select_candidates(
        ProviderType.GEMINI, "gemini-2.0-flash", strategy=RoutingStrategy.ROUND_ROBIN
    )
    rr2 = pool.select_candidates(
        ProviderType.GEMINI, "gemini-2.0-flash", strategy=RoutingStrategy.ROUND_ROBIN
    )
    assert [k.id for k in rr1] == ["k1", "k2"]
    assert [k.id for k in rr2] == ["k2", "k1"]

    cheap = pool.select_candidates(
        ProviderType.GEMINI, "gemini-2.0-flash", strategy=RoutingStrategy.LOWEST_COST
    )
    assert [k.id for k in cheap] == ["k2", "k1"]


def test_rate_limit_429_cooldown_and_immediate_failover() -> None:
    clock = _FakeClock()
    k1 = _make_key("k1", priority=1)
    k2 = _make_key("k2", priority=2)
    pool = KeyPool([k1, k2], clock=clock)
    profile = [ModelProfileEntry(provider=ProviderType.GEMINI, model="gemini-2.0-flash")]

    calls: list[str] = []

    def fake_complete(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["api_key"])
        if kwargs["api_key"] == "secret-k1":
            raise _HTTPStatusError("rate limited", 429, headers={"Retry-After": "45"})
        return _ok_completion()

    router = LLMRouter(
        pool,
        profile,
        completion_fn=fake_complete,
        cost_fn=lambda _r, _m: 0.001,
        unit_cost_fn=lambda _p, _m: 0.0,
        sleep_fn=lambda _s: None,
    )
    resp = router.complete_routed(LLMRequest(messages=[LLMMessage(role="user", content="hi")]))
    assert resp.key_id == "k2"
    assert resp.fallback_used is False
    assert calls == ["secret-k1", "secret-k2"]
    assert k1.status == KeyStatus.COOLDOWN
    assert k1.cooldown_until == clock.now + timedelta(seconds=45)

    # After 45 seconds, k1 automatically reactivates
    clock.advance(46)
    candidates = pool.select_candidates(ProviderType.GEMINI, "gemini-2.0-flash")
    assert candidates[0].id == "k1"
    assert k1.status == KeyStatus.ACTIVE


def test_auth_401_403_marks_key_invalid_and_fails_over() -> None:
    k1 = _make_key("k1", provider=ProviderType.OPENAI, priority=1)
    k2 = _make_key("k2", provider=ProviderType.OPENAI, priority=2)
    pool = KeyPool([k1, k2])
    profile = [ModelProfileEntry(provider=ProviderType.OPENAI, model="gpt-4o-mini")]

    def fake_complete(**kwargs: Any) -> dict[str, Any]:
        if kwargs["api_key"] == "secret-k1":
            raise _HTTPStatusError("unauthorized", 401)
        return _ok_completion()

    router = LLMRouter(
        pool,
        profile,
        completion_fn=fake_complete,
        cost_fn=lambda _r, _m: 0.0,
        unit_cost_fn=lambda _p, _m: 0.0,
    )
    resp = router.complete_routed(LLMRequest(messages=[LLMMessage(role="user", content="hi")]))
    assert resp.key_id == "k2"
    assert k1.status == KeyStatus.INVALID
    assert [k.id for k in pool.select_candidates(ProviderType.OPENAI, "gpt-4o-mini")] == ["k2"]


def test_5xx_retries_twice_then_falls_back_to_next_model() -> None:
    k_gem = _make_key("k-gem", provider=ProviderType.GEMINI, priority=1)
    k_oll = _make_key("k-oll", provider=ProviderType.OLLAMA, priority=1)
    pool = KeyPool([k_gem, k_oll])
    profile = [
        ModelProfileEntry(provider=ProviderType.GEMINI, model="gemini-2.0-flash"),
        ModelProfileEntry(provider=ProviderType.OLLAMA, model="llama3.2"),
    ]

    attempts_by_model: list[str] = []

    def fake_complete(**kwargs: Any) -> dict[str, Any]:
        attempts_by_model.append(kwargs["model"])
        if kwargs["model"].startswith("gemini/"):
            raise _HTTPStatusError("service unavailable", 503)
        return _ok_completion()

    router = LLMRouter(
        pool,
        profile,
        completion_fn=fake_complete,
        cost_fn=lambda _r, _m: 0.0,
        unit_cost_fn=lambda _p, _m: 0.0,
        sleep_fn=lambda _s: None,
    )
    resp = router.complete_routed(LLMRequest(messages=[LLMMessage(role="user", content="hi")]))
    # 1 initial + 2 retries on gemini, then 1 success on ollama
    assert attempts_by_model == [
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.0-flash",
        "ollama/llama3.2",
    ]
    assert resp.provider == ProviderType.OLLAMA
    assert resp.model == "llama3.2"
    assert resp.fallback_used is True


def test_local_rpm_tpm_rpd_limits_and_budget_exceeded() -> None:
    clock = _FakeClock()
    k1 = _make_key("k1", rpm_limit=1, tpm_limit=100, rpd_limit=2)
    pool = KeyPool([k1], clock=clock)
    profile = [ModelProfileEntry(provider=ProviderType.GEMINI, model="gemini-2.0-flash")]

    router = LLMRouter(
        pool,
        profile,
        job_budget_remaining_usd=0.05,
        completion_fn=lambda **_kw: _ok_completion(in_tok=10, out_tok=5),
        cost_fn=lambda _r, _m: 0.03,
        unit_cost_fn=lambda _p, _m: 0.0,
        sleep_fn=lambda _s: None,
    )
    # First call succeeds (cost 0.03 -> remaining 0.02), RPM=1 hit
    router.complete_routed(LLMRequest(messages=[LLMMessage(role="user", content="hi")]))
    assert router.job_budget_remaining_usd == pytest.approx(0.02)

    # Immediate second call: k1 exhausted by RPM=1 -> AllKeysExhaustedError
    with pytest.raises(AllKeysExhaustedError):
        router.complete_routed(LLMRequest(messages=[LLMMessage(role="user", content="hi")]))

    # Advance 61s so RPM resets; second call succeeds (cost 0.03 -> remaining 0.0)
    clock.advance(61)
    router.complete_routed(LLMRequest(messages=[LLMMessage(role="user", content="hi")]))
    assert router.job_budget_remaining_usd == 0.0

    # Third call: budget is 0.0 -> BudgetExceededError
    clock.advance(61)
    with pytest.raises(BudgetExceededError):
        router.complete_routed(LLMRequest(messages=[LLMMessage(role="user", content="hi")]))


def test_invalid_json_repair_retry_then_manual_review() -> None:
    k1 = _make_key("k1")
    pool = KeyPool([k1])
    profile = [ModelProfileEntry(provider=ProviderType.GEMINI, model="gemini-2.0-flash")]

    router = LLMRouter(
        pool,
        profile,
        completion_fn=lambda **_kw: _ok_completion(content="not valid json"),
        cost_fn=lambda _r, _m: 0.0,
        unit_cost_fn=lambda _p, _m: 0.0,
    )
    criteria = [
        CriterionItem(
            id="c1",
            label="Python",
            description="3 years",
            type=CriterionType.MANDATORY,
            weight=5,
        )
    ]
    eval_res = evaluate_cv("CV text", "Job", criteria, router, model="gemini-2.0-flash")
    assert eval_res.invalid_json is True
    scoring = score_candidate(criteria, [], invalid_json=eval_res.invalid_json)
    assert scoring.recommendation == Recommendation.MANUAL_REVIEW


def test_check_api_key_success_and_secret_scrubbing() -> None:
    key = _make_key("k1")
    ok_res = check_api_key(key, completion_fn=lambda **_kw: _ok_completion("OK"))
    assert ok_res.ok is True
    assert ok_res.latency_ms is not None

    def failing(**_kw: Any) -> None:
        raise _HTTPStatusError(f"Invalid key {key.api_key}", 401)

    err_res = check_api_key(key, completion_fn=failing)
    assert err_res.ok is False
    assert err_res.error is not None
    assert "secret-k1" not in err_res.error
    assert "***" in err_res.error


@pytest.mark.parametrize(
    ("cassette_name", "provider", "model", "expected_text"),
    [
        ("openai_chat.yaml", ProviderType.OPENAI, "gpt-4o-mini", "OK_OPENAI"),
        ("gemini_chat.yaml", ProviderType.GEMINI, "gemini-2.0-flash", "OK_GEMINI"),
        ("ollama_chat.yaml", ProviderType.OLLAMA, "llama3.2", "OK_OLLAMA"),
    ],
)
def test_vcr_cassettes_replay_openai_gemini_ollama(
    cassette_name: str,
    provider: ProviderType,
    model: str,
    expected_text: str,
) -> None:
    """Replay synthetic/redacted VCR cassettes through real LiteLLM + LLMRouter."""
    cassette_path = CASSETTES_DIR / cassette_name
    assert cassette_path.is_file(), f"Missing VCR cassette: {cassette_path}"

    key = PooledKey(
        id=f"vcr-{provider.value}",
        provider=provider,
        label="VCR Test Key",
        api_key="sk-redacted-test-key",
        base_url="http://localhost:11434" if provider == ProviderType.OLLAMA else None,
    )
    pool = KeyPool([key])
    router = LLMRouter(
        pool,
        [ModelProfileEntry(provider=provider, model=model)],
    )

    import vcr
    import vcr.patch

    from shortlist.llm.router import _import_litellm

    litellm = _import_litellm()
    # Pre-warm LiteLLM encoding outside VCR so tiktoken does not fetch over HTTP.
    _ = litellm.encoding
    vcr.patch.CassettePatcherBuilder._aiohttp = lambda _self: ()  # type: ignore[method-assign]
    my_vcr = vcr.VCR(
        record_mode="none",
        match_on=["method", "scheme", "host", "port", "path"],
    )
    with my_vcr.use_cassette(str(cassette_path)):
        resp = router.complete_routed(
            LLMRequest(
                messages=[LLMMessage(role="user", content="Reply with OK.")],
                temperature=0.0,
                response_format_json=False,
            )
        )

    assert expected_text in resp.content
    assert resp.model == model
    assert resp.provider == provider
