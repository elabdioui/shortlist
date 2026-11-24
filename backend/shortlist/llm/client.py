# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM client protocol and deterministic fake client for testing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """Single chat message sent to an LLM provider."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    """Normalized LLM completion request."""

    messages: list[LLMMessage]
    model: str = "fake-deterministic-v1"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    response_format_json: bool = True
    max_tokens: int | None = Field(default=None, ge=1)


class LLMResponse(BaseModel):
    """Normalized LLM completion response with token/cost accounting."""

    content: str
    model: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)


class LLMClient(Protocol):
    """Protocol implemented by real LiteLLM router and deterministic fake clients."""

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute a synchronous chat completion request."""
        ...


class FakeLLMClient:
    """Deterministic fake LLM client for offline and CI testing.

    Records every outgoing LLMRequest so tests can inspect payloads (e.g. to
    assert no PII leaves the local boundary).
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        handler: Callable[[LLMRequest], str] | None = None,
        model_name: str = "fake-deterministic-v1",
    ) -> None:
        self._responses = list(responses) if responses is not None else []
        self._handler = handler
        self._model_name = model_name
        self.recorded_requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Record request and return the next scripted or handler-generated response."""
        self.recorded_requests.append(request)

        if self._handler is not None:
            content = self._handler(request)
        elif self._responses:
            content = self._responses.pop(0)
        else:
            raise RuntimeError("FakeLLMClient has no remaining scripted responses and no handler.")

        input_tokens = sum(max(1, len(m.content) // 4) for m in request.messages)
        output_tokens = max(1, len(content) // 4)

        return LLMResponse(
            content=content,
            model=request.model or self._model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
        )
