# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider formatting, privacy classification, and LiteLLM error mapping."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from shortlist.schemas.common import ProviderType

_PROVIDER_PREFIXES: dict[ProviderType, str] = {
    ProviderType.OLLAMA: "ollama",
    ProviderType.GEMINI: "gemini",
    ProviderType.OPENAI: "openai",
    ProviderType.ANTHROPIC: "anthropic",
    ProviderType.MISTRAL: "mistral",
    ProviderType.GROQ: "groq",
    ProviderType.OPENROUTER: "openrouter",
    ProviderType.OPENAI_COMPATIBLE: "openai",
}

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "ollama"})

ErrorCategory = Literal["rate_limit", "auth", "transient", "other"]


def format_litellm_model(provider: ProviderType, model: str) -> str:
    """Return the canonical LiteLLM `<prefix>/<model>` identifier."""
    cleaned = model.strip()
    prefix = _PROVIDER_PREFIXES[provider]
    if cleaned.startswith(f"{prefix}/") or (
        provider == ProviderType.OLLAMA and cleaned.startswith("ollama_chat/")
    ):
        return cleaned
    return f"{prefix}/{cleaned}"


def is_external_provider(provider: ProviderType, base_url: str | None = None) -> bool:
    """Return True if sending data to this provider leaves the local machine."""
    if provider == ProviderType.OLLAMA:
        return False
    if provider == ProviderType.OPENAI_COMPATIBLE and base_url:
        host = (urlparse(base_url).hostname or "").lower()
        return host not in _LOCAL_HOSTS
    return True


def extract_retry_after_seconds(exc: Exception) -> float | None:
    """Extract numeric Retry-After header (in seconds) from an exception if present."""
    headers: Any = getattr(exc, "headers", None)
    if headers is None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) if response is not None else None

    if not headers:
        return None

    for key in ("Retry-After", "retry-after"):
        val = headers.get(key) if hasattr(headers, "get") else None
        if val is not None:
            try:
                parsed = float(str(val).strip())
                if parsed > 0:
                    return parsed
            except ValueError:
                return None
    return None


def classify_llm_error(exc: Exception) -> ErrorCategory:
    """Classify an LLM exception as rate_limit (429), auth (401/403), transient (5xx), or other."""
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        if status_code == 429:
            return "rate_limit"
        if status_code in (401, 403):
            return "auth"
        if status_code == 408 or 500 <= status_code < 600:
            return "transient"

    name = type(exc).__name__.lower()
    if "ratelimit" in name or "429" in name:
        return "rate_limit"
    if "authentication" in name or "permissiondenied" in name or "401" in name or "403" in name:
        return "auth"
    if any(
        tok in name
        for tok in (
            "timeout",
            "apiconnection",
            "serviceunavailable",
            "internalserver",
            "badgateway",
            "500",
            "502",
            "503",
            "504",
        )
    ):
        return "transient"

    return "other"
