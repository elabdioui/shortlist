# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM abstraction and routing package."""

from shortlist.llm.client import FakeLLMClient, LLMClient, LLMMessage, LLMRequest, LLMResponse
from shortlist.llm.pool import KeyPool, PooledKey
from shortlist.llm.providers import (
    classify_llm_error,
    extract_retry_after_seconds,
    format_litellm_model,
    is_external_provider,
)
from shortlist.llm.router import (
    AllKeysExhaustedError,
    BudgetExceededError,
    LLMRouter,
    RoutedLLMResponse,
    check_api_key,
)

__all__ = [
    "AllKeysExhaustedError",
    "BudgetExceededError",
    "FakeLLMClient",
    "KeyPool",
    "LLMClient",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMRouter",
    "PooledKey",
    "RoutedLLMResponse",
    "check_api_key",
    "classify_llm_error",
    "extract_retry_after_seconds",
    "format_litellm_model",
    "is_external_provider",
]
