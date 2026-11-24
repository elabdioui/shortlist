# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regressions found while screening real CVs (review-02): extraction, PII, quotes, routing."""

from __future__ import annotations

import threading
import time
from typing import Any

import fitz

from shortlist.core.anonymize.anonymizer import anonymize_text
from shortlist.core.evaluate.evaluator import (
    DEFAULT_EVAL_PROMPT_VERSION,
    build_evaluation_messages,
)
from shortlist.core.extract.normalizer import normalize_text
from shortlist.core.extract.pdf_extractor import extract_pdf
from shortlist.core.verify.verifier import verify_quote
from shortlist.llm.client import LLMMessage, LLMRequest
from shortlist.llm.pool import KeyPool, PooledKey
from shortlist.llm.router import AllKeysExhaustedError, LLMRouter
from shortlist.schemas.common import ProviderType
from shortlist.schemas.providers import ModelProfileEntry

CV = (
    "Stagiaire — Service Voiturier\n"
    "Immersion au sein du service Voiturier, infrastructure portuaire dédiée à l'import-export\n"
    "de véhicules neufs.\n"
    "Découverte du fonctionnement du service Conteneurs et des opérations de\n"
    "manutention associées.\n"
    "Observation des procédures logistiques et douanières liées au transit international de\n"
    "marchandises.\n"
)


def test_quote_with_ellipsis_is_verified_when_every_fragment_exists() -> None:
    span = verify_quote("Immersion au sein du service Voiturier ... de véhicules neufs", CV)
    assert span is not None
    assert CV[span.start : span.end].startswith("Immersion au sein")


def test_quote_stitching_nearby_sentences_is_verified() -> None:
    quote = (
        "Immersion au sein du service Voiturier, infrastructure portuaire dédiée à "
        "l'import-export de véhicules neufs. Observation des procédures logistiques et "
        "douanières liées au transit international de marchandises."
    )
    assert verify_quote(quote, CV) is not None


def test_quote_with_one_fabricated_fragment_is_rejected() -> None:
    quote = "Immersion au sein du service Voiturier ... expert SAP certifié depuis dix ans"
    assert verify_quote(quote, CV) is None


def test_all_caps_name_is_redacted_using_email_with_trailing_digits() -> None:
    text = (
        "PROFIL\nEXPÉRIENCES\nCASABLANCA\nFORMATIONS\nESITH\nLANGUES\nFrançais : courant.\n"
        "Anglais : courant.\n22 ans\nASMAE SAMYH\nMail: asmae.samyh15@gmail.com\n"
    )
    result = anonymize_text(text)
    assert "SAMYH" not in result.anonymized_text
    assert "ASMAE" not in result.anonymized_text


def test_standalone_bullet_glyphs_do_not_merge_lines() -> None:
    raw = "marchandises.\n\n●\n\n●\n\nStagiaire — Stage\n\n● Vente-conseil omnicanale"
    out = normalize_text(raw).text
    assert "- -" not in out
    assert "marchandises.\n\nStagiaire — Stage" in out
    assert "- Vente-conseil omnicanale" in out


def _sidebar_pdf() -> bytes:
    """Narrow left sidebar (contact) + wide main column starting higher (name, experience)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((196, 30), "MAIN_NAME Jane Roe", fontsize=16)
    page.insert_text((196, 160), "MAIN_EXP Site Manager Assistant at Aramex", fontsize=10)
    page.insert_text((525, 175), "MAIN_DATE Jun 2026", fontsize=8)
    page.insert_text(
        (196, 190), "MAIN_EXP2 Fulfillment assistant for several accounts", fontsize=10
    )
    page.insert_text((15, 140), "SIDE_CONTACT Phone", fontsize=10)
    page.insert_text((15, 200), "SIDE_LANG French Fluent", fontsize=10)
    page.insert_text((15, 260), "SIDE_TOOLS Excel advanced", fontsize=10)
    return doc.tobytes()


def test_sidebar_layout_reads_main_column_first_and_keeps_dates_with_roles() -> None:
    text = extract_pdf(_sidebar_pdf(), enable_ocr=False).text
    order = [
        text.index(tag)
        for tag in ("MAIN_NAME", "MAIN_EXP ", "MAIN_DATE", "MAIN_EXP2", "SIDE_CONTACT", "SIDE_LANG")
    ]
    assert order == sorted(order)


def test_worker_uses_strict_v3_evaluation_prompt_by_default() -> None:
    assert DEFAULT_EVAL_PROMPT_VERSION == "v3"
    messages = build_evaluation_messages("cv", "job", [])
    assert "absence of evidence is NEVER" in messages[0].content


def _router(pool: KeyPool, completion: Any, **kwargs: Any) -> LLMRouter:
    return LLMRouter(
        pool=pool,
        profile=[ModelProfileEntry(provider=ProviderType.GROQ, model="m")],
        completion_fn=completion,
        cost_fn=lambda _r, _m: 0.0,
        unit_cost_fn=lambda _p, _m: 0.0,
        **kwargs,
    )


def _ok(**_kwargs: Any) -> dict[str, Any]:
    time.sleep(0.2)
    return {"choices": [{"message": {"content": "{}"}}], "usage": {}}


def _request() -> LLMRequest:
    return LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m")


def test_router_waits_for_busy_slot_instead_of_failing() -> None:
    pool = KeyPool(
        [PooledKey(id="k", provider=ProviderType.GROQ, label="k", api_key="x", concurrency=1)]
    )
    router = _router(pool, _ok)
    errors: list[Exception] = []

    def call() -> None:
        try:
            router.complete_routed(_request())
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=call) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_rate_limit_exhaustion_is_retryable_but_daily_quota_is_not() -> None:
    class RateLimitError(Exception):
        status_code = 429

    def limited(**_kwargs: Any) -> Any:
        raise RateLimitError("quota")

    pool = KeyPool([PooledKey(id="k", provider=ProviderType.GROQ, label="k", api_key="x")])
    try:
        _router(pool, limited).complete_routed(_request())
    except AllKeysExhaustedError as exc:
        assert exc.retryable
    else:  # pragma: no cover
        raise AssertionError("expected exhaustion")

    pool2 = KeyPool(
        [PooledKey(id="k", provider=ProviderType.GROQ, label="k", api_key="x", rpd_limit=0)]
    )
    try:
        _router(pool2, _ok).complete_routed(_request())
    except AllKeysExhaustedError as exc:
        assert not exc.retryable
    else:  # pragma: no cover
        raise AssertionError("expected exhaustion")


def test_short_quote_accepted_only_on_exact_whole_word_match() -> None:
    cv = "LANGUAGES\nFrench \u2013 Fluent\nEnglish \u2013 Fluent\nOutils : SAP MM."
    span = verify_quote("English \u2013 Fluent", cv)
    assert span is not None and cv[span.start : span.end] == "English \u2013 Fluent"
    assert verify_quote("German \u2013 Fluent", cv) is None
    assert verify_quote("SAP MM", cv) is None  # too short even when exact


def test_naive_cooldown_from_sqlite_is_treated_as_utc() -> None:
    from datetime import UTC, datetime

    from shortlist.worker.llm_factory import _as_utc

    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = _as_utc(naive)
    assert aware is not None and aware.tzinfo is UTC
    assert aware < datetime(2027, 1, 1, tzinfo=UTC)
    assert _as_utc(None) is None
