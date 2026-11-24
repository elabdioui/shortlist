# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Criteria grid generation with anti-discrimination guardrails."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from shortlist.core.evaluate.evaluator import _strip_code_fences, load_prompt
from shortlist.llm.client import LLMClient, LLMMessage, LLMRequest
from shortlist.schemas.jobs import CriterionItem

_DISCRIMINATORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "age",
        re.compile(
            r"\b(?:age|âge|aged|âgé|moins de \d+ ans|plus de \d+ ans|under \d+|young|jeune)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "gender",
        re.compile(
            r"\b(?:gender|sexe|sex|female only|male only|femme uniquement|homme uniquement)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "origin_nationality",
        re.compile(
            r"\b(?:ethnic|ethnicity|race|origine|nationalité|nationality|native citizen)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "religion",
        re.compile(
            r"\b(?:religion|religious|religieux|religieuse|confession|muslim|christian|jewish)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "marital_family",
        re.compile(
            r"\b(?:marital status|situation familiale|célibataire|"
            r"marié|married|single|pregnant|enceinte)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "photo_appearance",
        re.compile(
            r"\b(?:photo obligatoire|photograph required|physical appearance|apparence physique)\b",
            re.IGNORECASE,
        ),
    ),
)


class _LLMCriteriaPayload(BaseModel):
    criteria: list[CriterionItem]
    rejected_discriminatory: list[str] = Field(default_factory=list)


class CriteriaGenerationResult(BaseModel):
    """Result of generating a screening criteria grid from a job description."""

    criteria: list[CriterionItem]
    rejected_discriminatory: list[str] = Field(default_factory=list)
    model_used: str
    prompt_version: str = "v1"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def detect_discriminatory_reason(label: str, description: str) -> str | None:
    """Return the protected category name if a criterion is discriminatory, else None."""
    combined = f"{label} {description}"
    for category, pattern in _DISCRIMINATORY_PATTERNS:
        if pattern.search(combined):
            return category
    return None


def generate_criteria(
    job_description: str,
    client: LLMClient,
    *,
    model: str = "fake-deterministic-v1",
    prompt_version: str = "v1",
) -> CriteriaGenerationResult:
    """Generate 5-12 measurable criteria from a job description at temperature=0."""
    system_prompt = load_prompt("criteria", prompt_version)
    user_prompt = f"Job description:\n{job_description.strip()}"

    response = client.complete(
        LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            model=model,
            temperature=0.0,
            response_format_json=True,
        )
    )

    payload = _LLMCriteriaPayload.model_validate_json(_strip_code_fences(response.content))

    filtered_criteria: list[CriterionItem] = []
    rejected = list(payload.rejected_discriminatory)
    for item in payload.criteria:
        reason = detect_discriminatory_reason(item.label, item.description)
        if reason is not None:
            rejected.append(f"Refused discriminatory criterion ({reason}): {item.label}")
        else:
            filtered_criteria.append(item)

    return CriteriaGenerationResult(
        criteria=filtered_criteria,
        rejected_discriminatory=rejected,
        model_used=response.model,
        prompt_version=prompt_version,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
    )
