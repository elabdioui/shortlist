# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Quota-aware multi-key LLM router backed by LiteLLM."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from shortlist.llm.client import LLMRequest, LLMResponse
from shortlist.llm.pool import KeyPool, PooledKey
from shortlist.llm.providers import (
    classify_llm_error,
    extract_retry_after_seconds,
    format_litellm_model,
)
from shortlist.schemas.common import ProviderType, RoutingStrategy
from shortlist.schemas.providers import APIKeyTestResult, ModelProfileEntry

MAX_TRANSIENT_RETRIES = 2
# How long a request waits for a busy concurrency slot before falling back.
MAX_SLOT_WAIT_SECONDS = 45.0
SLOT_POLL_SECONDS = 0.5

_DEFAULT_TEST_MODELS: dict[ProviderType, str] = {
    ProviderType.OLLAMA: "llama3.2",
    ProviderType.GEMINI: "gemini-2.0-flash-lite",
    ProviderType.OPENAI: "gpt-4o-mini",
    ProviderType.ANTHROPIC: "claude-3-5-haiku-latest",
    ProviderType.MISTRAL: "mistral-small-latest",
    ProviderType.GROQ: "llama-3.1-8b-instant",
    ProviderType.OPENROUTER: "openai/gpt-4o-mini",
    ProviderType.OPENAI_COMPATIBLE: "gpt-4o-mini",
}

CompletionFn = Callable[..., Any]
CostFn = Callable[[Any, str], float]
UnitCostFn = Callable[[ProviderType, str], float]


class BudgetExceededError(RuntimeError):
    """Raised when the estimated or remaining job budget would be exceeded."""


class AllKeysExhaustedError(RuntimeError):
    """Raised when every key and fallback model in the profile failed or is unavailable."""

    def __init__(self, attempts: list[str], retry_after_seconds: float | None = None) -> None:
        self.attempts = attempts
        # Seconds after which retrying is likely to succeed (rate limits, 5xx,
        # busy keys). None means the failure is permanent (invalid keys,
        # daily quota, unsupported model) and retrying will not help.
        self.retry_after_seconds = retry_after_seconds
        summary = "; ".join(attempts) if attempts else "No eligible keys in pool."
        super().__init__(f"All keys and fallback models exhausted: {summary}")

    @property
    def retryable(self) -> bool:
        """True if the exhaustion is temporary and the request may be retried later."""
        return self.retry_after_seconds is not None


class RoutedLLMResponse(LLMResponse):
    """LLMResponse enriched with routing metadata."""

    provider: ProviderType
    key_id: str
    fallback_used: bool = False
    attempt_count: int = 1


def _import_litellm() -> Any:
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import litellm

    litellm.telemetry = False
    return litellm


def _default_litellm_completion(**kwargs: Any) -> Any:
    litellm = _import_litellm()
    return litellm.completion(**kwargs)


def _default_litellm_cost(response: Any, model: str) -> float:
    litellm = _import_litellm()
    try:
        return float(litellm.completion_cost(completion_response=response, model=model))
    except Exception:
        return 0.0


def _default_unit_cost(provider: ProviderType, model: str) -> float:
    litellm = _import_litellm()

    litellm_model = format_litellm_model(provider, model)
    info = litellm.model_cost.get(litellm_model) or litellm.model_cost.get(model)
    if isinstance(info, dict):
        in_cost = float(info.get("input_cost_per_token", 0.0) or 0.0)
        out_cost = float(info.get("output_cost_per_token", 0.0) or 0.0)
        return in_cost + out_cost
    return 0.0


def _extract_response_fields(response: Any) -> tuple[str, int, int]:
    """Extract (content, input_tokens, output_tokens) from a LiteLLM response object or dict."""
    if isinstance(response, dict):
        choices = response.get("choices", [])
        content = ""
        if choices:
            msg = choices[0].get("message", {})
            content = str(msg.get("content", "") or "")
        usage = response.get("usage", {}) or {}
        in_tok = int(usage.get("prompt_tokens", 0) or 0)
        out_tok = int(usage.get("completion_tokens", 0) or 0)
        return content, in_tok, out_tok

    choices = getattr(response, "choices", [])
    content = ""
    if choices:
        message = getattr(choices[0], "message", None)
        content = str(getattr(message, "content", "") or "")
    usage = getattr(response, "usage", None)
    in_tok = int(getattr(usage, "prompt_tokens", 0) or 0) if usage is not None else 0
    out_tok = int(getattr(usage, "completion_tokens", 0) or 0) if usage is not None else 0
    return content, in_tok, out_tok


def _sanitize_error(exc: Exception, secret: str) -> str:
    msg = f"{type(exc).__name__}: {exc}"
    if secret:
        msg = msg.replace(secret, "***")
    return msg


class LLMRouter:
    """Multi-key, quota-aware LiteLLM router implementing LLMClient."""

    def __init__(
        self,
        pool: KeyPool,
        profile: list[ModelProfileEntry],
        *,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY,
        job_budget_remaining_usd: float | None = None,
        completion_fn: CompletionFn | None = None,
        cost_fn: CostFn | None = None,
        unit_cost_fn: UnitCostFn | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        request_timeout_seconds: float = 60.0,
        max_slot_wait_seconds: float = MAX_SLOT_WAIT_SECONDS,
    ) -> None:
        self._pool = pool
        self._profile = profile
        self._strategy = strategy
        self._job_budget_remaining_usd = job_budget_remaining_usd
        self._completion_fn = completion_fn or _default_litellm_completion
        self._cost_fn = cost_fn or _default_litellm_cost
        self._unit_cost_fn = unit_cost_fn or _default_unit_cost
        self._sleep_fn = sleep_fn
        self._timeout = request_timeout_seconds
        self._max_slot_wait = max_slot_wait_seconds

    @property
    def job_budget_remaining_usd(self) -> float | None:
        """Remaining USD budget for the current job, if configured."""
        return self._job_budget_remaining_usd

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute a routed completion request (LLMClient protocol)."""
        return self.complete_routed(request)

    def complete_routed(self, request: LLMRequest) -> RoutedLLMResponse:
        """Execute a completion across the profile's fallback chain and key pool."""
        estimated_tokens = sum(max(1, len(m.content) // 4) for m in request.messages)
        attempts: list[str] = []
        retry_hints: list[float] = []
        total_attempts = 0

        for step_idx, step in enumerate(self._profile):
            fallback_used = step_idx > 0
            unit_cost = self._unit_cost_fn(step.provider, step.model)
            estimated_cost = unit_cost * estimated_tokens

            if self._job_budget_remaining_usd is not None and (
                self._job_budget_remaining_usd <= 0.0
                or estimated_cost > self._job_budget_remaining_usd
            ):
                raise BudgetExceededError(
                    f"Job budget exhausted (remaining=${self._job_budget_remaining_usd:.4f}, "
                    f"estimated=${estimated_cost:.4f})."
                )

            # Other worker threads may hold every concurrency slot of this
            # step's keys. Wait briefly for a slot instead of skipping straight
            # to a fallback model (or failing the whole task).
            waited = 0.0
            candidates = self._pool.select_candidates(
                step.provider,
                step.model,
                strategy=self._strategy,
                estimated_tokens=estimated_tokens,
                cost_fn=self._unit_cost_fn,
            )
            while (
                not candidates
                and waited < self._max_slot_wait
                and self._pool.is_slot_contended(step.provider, step.model)
            ):
                self._sleep_fn(SLOT_POLL_SECONDS)
                waited += SLOT_POLL_SECONDS
                candidates = self._pool.select_candidates(
                    step.provider,
                    step.model,
                    strategy=self._strategy,
                    estimated_tokens=estimated_tokens,
                    cost_fn=self._unit_cost_fn,
                )
            if not candidates:
                attempts.append(f"{step.provider.value}/{step.model}: no eligible keys")
                hint = self._pool.retry_hint_seconds(step.provider, step.model, estimated_tokens)
                if hint is not None:
                    retry_hints.append(hint)
                continue

            litellm_model = format_litellm_model(step.provider, step.model)
            for key in candidates:
                for retry_idx in range(MAX_TRANSIENT_RETRIES + 1):
                    if not self._pool.try_acquire(key.id, step.model, estimated_tokens):
                        break
                    total_attempts += 1
                    call_tokens = 0
                    call_cost = 0.0
                    try:
                        kwargs: dict[str, Any] = {
                            "model": litellm_model,
                            "messages": [
                                {"role": m.role, "content": m.content} for m in request.messages
                            ],
                            "temperature": request.temperature,
                            "timeout": self._timeout,
                        }
                        if key.api_key and step.provider != ProviderType.OLLAMA:
                            kwargs["api_key"] = key.api_key
                        if key.base_url:
                            kwargs["api_base"] = key.base_url
                        if request.max_tokens is not None:
                            kwargs["max_tokens"] = request.max_tokens
                        if request.response_format_json:
                            kwargs["response_format"] = {"type": "json_object"}

                        raw_resp = self._completion_fn(**kwargs)
                        content, in_tok, out_tok = _extract_response_fields(raw_resp)
                        call_tokens = in_tok + out_tok
                        call_cost = self._cost_fn(raw_resp, litellm_model)
                        self._pool.mark_success(key.id)
                        if self._job_budget_remaining_usd is not None:
                            self._job_budget_remaining_usd = max(
                                0.0, round(self._job_budget_remaining_usd - call_cost, 8)
                            )

                        return RoutedLLMResponse(
                            content=content,
                            model=step.model,
                            provider=step.provider,
                            key_id=key.id,
                            fallback_used=fallback_used,
                            attempt_count=total_attempts,
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                            cost_usd=call_cost,
                        )
                    except Exception as exc:
                        category = classify_llm_error(exc)
                        attempts.append(
                            f"{step.provider.value}/{step.model} key={key.id}: "
                            f"{_sanitize_error(exc, key.api_key)}"
                        )
                        if category == "rate_limit":
                            retry_after = extract_retry_after_seconds(exc)
                            until = self._pool.mark_cooldown(key.id, retry_after)
                            retry_hints.append(max(1.0, (until - self._pool_now()).total_seconds()))
                            break
                        if category == "auth":
                            self._pool.mark_invalid(key.id)
                            break
                        if category == "transient":
                            if retry_idx < MAX_TRANSIENT_RETRIES:
                                self._sleep_fn(min(2.0**retry_idx, 4.0))
                                continue
                            # Provider overloaded (5xx/timeout): worth retrying later.
                            retry_hints.append(30.0)
                        break
                    finally:
                        self._pool.release(key.id, total_tokens=call_tokens, cost_usd=call_cost)

        raise AllKeysExhaustedError(
            attempts,
            retry_after_seconds=min(retry_hints) if retry_hints else None,
        )

    def _pool_now(self) -> Any:
        return self._pool.now()


def check_api_key(
    key: PooledKey,
    *,
    model: str | None = None,
    completion_fn: CompletionFn | None = None,
    timeout_seconds: float = 15.0,
) -> APIKeyTestResult:
    """Execute a minimal LLM call to verify an API key's connectivity and validity."""
    target_model = model or (
        key.allowed_models[0] if key.allowed_models else _DEFAULT_TEST_MODELS[key.provider]
    )
    litellm_model = format_litellm_model(key.provider, target_model)
    fn = completion_fn or _default_litellm_completion

    start = time.monotonic()
    try:
        kwargs: dict[str, Any] = {
            "model": litellm_model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "temperature": 0.0,
            "max_tokens": 8,
            "timeout": timeout_seconds,
        }
        if key.api_key and key.provider != ProviderType.OLLAMA:
            kwargs["api_key"] = key.api_key
        if key.base_url:
            kwargs["api_base"] = key.base_url

        fn(**kwargs)
        latency_ms = max(1, int((time.monotonic() - start) * 1000))
        return APIKeyTestResult(ok=True, model=target_model, latency_ms=latency_ms)
    except Exception as exc:
        latency_ms = max(1, int((time.monotonic() - start) * 1000))
        return APIKeyTestResult(
            ok=False,
            model=target_model,
            latency_ms=latency_ms,
            error=_sanitize_error(exc, key.api_key),
        )
