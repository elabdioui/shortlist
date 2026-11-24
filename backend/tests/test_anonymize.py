# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for local PII anonymization, custom Moroccan recognizers, and Fernet encryption."""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from shortlist.core.anonymize import (
    anonymize_text,
    deanonymize_text,
    decrypt_pii_map,
    encrypt_pii_map,
)


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
