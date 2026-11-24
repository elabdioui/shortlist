# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deterministic FakeLLMClient factory for offline mode (SHORTLIST_FAKE_LLM=1)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from shortlist.core.evaluate.evaluator import CV_END_DELIMITER, CV_START_DELIMITER
from shortlist.llm.client import FakeLLMClient, LLMRequest

_CRITERIA_JSON_RE = re.compile(
    r"Screening criteria \(JSON\):\s*(\[.*?\])\s*\n\nCandidate CV",
    re.DOTALL,
)


def is_fake_llm_enabled() -> bool:
    """Return True when SHORTLIST_FAKE_LLM=1 is set in the environment."""
    return os.environ.get("SHORTLIST_FAKE_LLM", "").strip() in ("1", "true", "TRUE", "yes")


def _extract_cv_snippet(cv_text: str, seed_idx: int) -> str:
    """Pick a deterministic verbatim non-empty line or phrase from the CV text."""
    lines = [line.strip() for line in cv_text.splitlines() if len(line.strip()) >= 12]
    if not lines:
        lines = [line.strip() for line in cv_text.splitlines() if line.strip()]
    if not lines:
        return ""
    chosen = lines[seed_idx % len(lines)]
    return chosen[:160]


def _handle_criteria_request() -> str:
    """Return a deterministic 5-criterion grid JSON."""
    payload = {
        "criteria": [
            {
                "id": "c1",
                "label": "Relevant professional experience",
                "description": "At least 3 years of relevant experience in the target role.",
                "type": "mandatory",
                "weight": 5,
            },
            {
                "id": "c2",
                "label": "Higher education degree",
                "description": "Bachelor or Master degree in a relevant discipline.",
                "type": "mandatory",
                "weight": 4,
            },
            {
                "id": "c3",
                "label": "Core technical or domain skills",
                "description": "Demonstrated mastery of key tools and domain practices.",
                "type": "mandatory",
                "weight": 4,
            },
            {
                "id": "c4",
                "label": "Working languages",
                "description": "Proficiency in French and/or English.",
                "type": "bonus",
                "weight": 2,
            },
            {
                "id": "c5",
                "label": "Project or team leadership",
                "description": "Experience coordinating projects, suppliers, or teams.",
                "type": "bonus",
                "weight": 2,
            },
        ],
        "rejected_discriminatory": [],
    }
    return json.dumps(payload, ensure_ascii=False)


def _handle_evaluation_request(user_prompt: str) -> str:
    """Return a deterministic LLMOutputSchema JSON with verbatim CV quotes."""
    start_idx = user_prompt.find(CV_START_DELIMITER)
    end_idx = user_prompt.find(CV_END_DELIMITER)
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        cv_text = user_prompt[start_idx + len(CV_START_DELIMITER) : end_idx].strip()
    else:
        cv_text = user_prompt

    criteria_list: list[dict[str, Any]] = []
    match = _CRITERIA_JSON_RE.search(user_prompt)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, list):
                criteria_list = parsed
        except json.JSONDecodeError:
            criteria_list = []

    if not criteria_list:
        criteria_list = [{"id": "c1", "type": "mandatory", "weight": 5}]

    digest = hashlib.sha256(cv_text.encode("utf-8")).digest()
    criteria_results: list[dict[str, str]] = []

    for idx, crit in enumerate(criteria_list):
        cid = str(crit.get("id", f"c{idx + 1}"))
        selector = digest[idx % len(digest)] % 10
        snippet = _extract_cv_snippet(cv_text, idx)

        if selector < 6 and snippet:
            verdict = "yes"
            quote = snippet
            explanation = f"CV provides direct evidence for criterion {cid}."
        elif selector < 8 and snippet:
            verdict = "partial"
            quote = snippet
            explanation = f"CV shows partial alignment for criterion {cid}."
        else:
            verdict = "not_found"
            quote = ""
            explanation = f"No explicit evidence found for criterion {cid}."

        criteria_results.append(
            {
                "id": cid,
                "verdict": verdict,
                "quote": quote,
                "explanation": explanation,
            }
        )

    years = float((digest[0] % 9) + 1)
    payload = {
        "criteria": criteria_results,
        "relevant_experience_years": years,
        "current_role": "Specialist",
        "highest_education": "Master",
        "languages": ["français", "anglais"],
        "strengths": ["Relevant domain background"],
        "watchouts": [],
    }
    return json.dumps(payload, ensure_ascii=False)


def build_deterministic_fake_llm() -> FakeLLMClient:
    """Create a deterministic FakeLLMClient handling criteria generation and CV evaluation."""

    def _handler(request: LLMRequest) -> str:
        user_msg = next((m.content for m in request.messages if m.role == "user"), "")
        if CV_START_DELIMITER in user_msg:
            return _handle_evaluation_request(user_msg)
        return _handle_criteria_request()

    return FakeLLMClient(handler=_handler, model_name="fake-deterministic-v1")
