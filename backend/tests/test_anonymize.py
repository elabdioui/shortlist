# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for local PII anonymization, custom Moroccan recognizers, and Fernet encryption."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from cryptography.fernet import InvalidToken

from shortlist.core.anonymize import (
    MissingNLPModelError,
    anonymize_text,
    deanonymize_text,
    decrypt_pii_map,
    encrypt_pii_map,
    ensure_nlp_models_available,
)
from shortlist.core.evaluate import evaluate_cv
from shortlist.llm import FakeLLMClient, LLMRequest
from shortlist.schemas.candidates import LLMOutputCriterion, LLMOutputSchema
from shortlist.schemas.common import CriterionType, CriterionVerdict
from shortlist.schemas.jobs import CriterionItem

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"


def test_anonymize_moroccan_and_standard_pii() -> None:
    raw_cv = (
        "Salma Bennani\n"
        "Téléphone : +212 612345678 / 07 12 34 56 78\n"
        "CIN : AB123456\n"
        "Email : salma.bennani@example.ma\n"
        "LinkedIn : https://www.linkedin.com/in/salma-bennani\n"
        "GitHub : github.com/salma-dev\n"
        "Adresse : 24 Boulevard d'Anfa, 20000 Casablanca\n"
        "Né(e) le 14/05/1995 (29 ans)\n"
        "Situation familiale : Célibataire\n"
        "Nationalité : Marocaine\n"
        "Expérience : 5 ans en tant qu'acheteur industriel.\n"
    )

    res = anonymize_text(raw_cv, language="fr")
    anon = res.anonymized_text

    # None of the sensitive values should remain in anonymized text
    for sensitive in (
        "Salma Bennani",
        "+212 612345678",
        "07 12 34 56 78",
        "AB123456",
        "salma.bennani@example.ma",
        "linkedin.com/in/salma-bennani",
        "github.com/salma-dev",
        "Boulevard d'Anfa",
        "20000 Casablanca",
        "14/05/1995",
        "29 ans",
        "Célibataire",
        "Marocaine",
    ):
        assert sensitive not in anon, f"PII leaked in anonymized text: {sensitive}"

    # Non-PII professional content must remain intact
    assert "5 ans en tant qu'acheteur industriel" in anon

    # Reversible mapping restores original text
    assert deanonymize_text(anon, res.mapping) == raw_cv


def test_anonymize_extra_names_and_empty_text() -> None:
    empty = anonymize_text("")
    assert empty.anonymized_text == ""
    assert empty.mapping == {}

    text = "Le candidat Youssef El Amrani a géré 12 fournisseurs."
    res = anonymize_text(text, language="fr", extra_names=["Youssef El Amrani"])
    assert "Youssef El Amrani" not in res.anonymized_text
    assert deanonymize_text(res.anonymized_text, res.mapping) == text


def test_fernet_encrypt_decrypt_pii_map() -> None:
    mapping = {"[PERSON_1]": "Salma Bennani", "[CIN_1]": "AB123456"}
    secret = "test-shortlist-secret-key-32-bytes"

    token = encrypt_pii_map(mapping, secret)
    assert "Salma Bennani" not in token
    assert "AB123456" not in token

    decrypted = decrypt_pii_map(token, secret)
    assert decrypted == mapping

    with pytest.raises(InvalidToken):
        decrypt_pii_map(token, "wrong-secret-key")


def test_p0_1_fail_loudly_when_ner_models_missing() -> None:
    with patch("shortlist.core.anonymize.anonymizer.spacy.util.is_package", return_value=False):
        with pytest.raises(MissingNLPModelError):
            ensure_nlp_models_available(allow_blank_nlp=False)

        # Should not raise when explicitly allowed
        ensure_nlp_models_available(allow_blank_nlp=True)


def test_p0_1_pii_cases_yaml_and_outgoing_leak_check() -> None:
    raw_yaml = (FIXTURES_DIR / "pii_cases.yaml").read_text(encoding="utf-8")
    cases = yaml.safe_load(raw_yaml)["cases"]
    assert len(cases) >= 25

    criteria = [
        CriterionItem(
            id="c1",
            label="Relevant experience",
            description="Relevant work experience",
            type=CriterionType.MANDATORY,
            weight=5,
        )
    ]

    for case in cases:
        res = anonymize_text(case["text"], language=case["language"])
        for sensitive in case["must_redact"]:
            assert sensitive not in res.anonymized_text, (
                f"[{case['id']}] PII leaked: {sensitive!r} in {res.anonymized_text!r}"
            )
        for preserved in case["must_preserve"]:
            assert preserved in res.anonymized_text, (
                f"[{case['id']}] Over-redacted: {preserved!r} missing from {res.anonymized_text!r}"
            )
        for prefix in case.get("expected_placeholders", []):
            assert prefix in res.anonymized_text, (
                f"[{case['id']}] Expected placeholder {prefix!r} in {res.anonymized_text!r}"
            )

        # Outgoing LLM payload interception
        client = FakeLLMClient(
            handler=lambda _req: LLMOutputSchema(
                criteria=[
                    LLMOutputCriterion(
                        id="c1",
                        verdict=CriterionVerdict.NOT_FOUND,
                        quote="",
                        explanation="Not found.",
                    )
                ]
            ).model_dump_json()
        )
        evaluate_cv(res.anonymized_text, "Job", criteria, client)
        payload = "\n".join(m.content for req in client.recorded_requests for m in req.messages)
        for sensitive in case["must_redact"]:
            assert sensitive not in payload, (
                f"[{case['id']}] PII leaked in LLM payload: {sensitive}"
            )


def test_p0_1_all_30_eval_cvs_no_pii_leak_in_outgoing_llm_payload() -> None:
    cv_files = sorted(EVAL_DIR.glob("*/cvs/*.txt"))
    assert len(cv_files) == 30

    criteria = [
        CriterionItem(
            id="c1",
            label="Experience",
            description="Relevant experience",
            type=CriterionType.MANDATORY,
            weight=5,
        )
    ]

    for cv_path in cv_files:
        raw_text = cv_path.read_text(encoding="utf-8")
        # First line of every eval CV is the candidate's full name
        candidate_name = raw_text.splitlines()[0].strip()
        res = anonymize_text(raw_text, language="fr")

        def _handler(req: LLMRequest) -> str:
            return LLMOutputSchema(
                criteria=[
                    LLMOutputCriterion(
                        id="c1",
                        verdict=CriterionVerdict.NOT_FOUND,
                        quote="",
                        explanation="Not found.",
                    )
                ]
            ).model_dump_json()

        client = FakeLLMClient(handler=_handler)
        evaluate_cv(res.anonymized_text, "Job", criteria, client)
        payload = "\n".join(m.content for req in client.recorded_requests for m in req.messages)
        assert candidate_name not in payload, (
            f"[{cv_path.name}] Candidate name {candidate_name!r} leaked in LLM payload"
        )
        assert "@" not in payload, f"[{cv_path.name}] Email leaked in LLM payload"
        assert "+212" not in payload, f"[{cv_path.name}] +212 phone leaked in LLM payload"
