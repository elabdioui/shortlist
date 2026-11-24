# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Local PII anonymization pipeline using Microsoft Presidio and spaCy."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

import spacy
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngine, SpacyNlpEngine

from shortlist.core.anonymize.crypto import decrypt_pii_map, encrypt_pii_map
from shortlist.core.anonymize.recognizers import build_custom_recognizers

logger = logging.getLogger(__name__)

_ENTITY_PLACEHOLDER_PREFIX: dict[str, str] = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "MA_CIN": "CIN",
    "PROFILE_URL": "URL",
    "STREET_ADDRESS": "ADDRESS",
    "AGE_OR_DOB": "AGE_DOB",
    "MARITAL_STATUS": "MARITAL_STATUS",
    "NATIONALITY": "NATIONALITY",
}

_SUPPORTED_ENTITIES = list(_ENTITY_PLACEHOLDER_PREFIX.keys())

_NON_NAME_HEADER_WORDS = frozenset(
    {
        "cv",
        "curriculum",
        "vitae",
        "resume",
        "résumé",
        "profil",
        "profile",
        "experience",
        "expérience",
        "experiences",
        "expériences",
        "formation",
        "education",
        "competences",
        "compétences",
        "skills",
        "summary",
        "objectif",
        "objective",
        "ingénieur",
        "ingenieur",
        "engineer",
        "manager",
        "director",
        "directeur",
        "acheteur",
        "developer",
        "développeur",
        "supply",
        "chain",
        "logistics",
        "logistique",
    }
)

_HEADER_NAME_RE = re.compile(
    r"^[A-ZÀ-Ÿ][A-Za-zÀ-ÿ'-]{1,25}(?:\s+[A-ZÀ-Ÿ][A-Za-zÀ-ÿ'-]{1,25}){1,2}$"
)


@dataclass(frozen=True, slots=True)
class AnonymizationResult:
    """Result of local PII anonymization."""

    anonymized_text: str
    mapping: dict[str, str]
    entities_found: list[str]
    ner_model_loaded: bool

    def encrypt_mapping(self, secret_key: str) -> str:
        """Encrypt the reversible PII mapping using Fernet."""
        return encrypt_pii_map(self.mapping, secret_key)


class _BlankSpacyNlpEngine(SpacyNlpEngine):
    """SpacyNlpEngine backed by blank spaCy pipelines when full models are absent."""

    def load(self) -> None:
        self.nlp = cast(
            Any,
            {
                "fr": spacy.blank("fr"),
                "en": spacy.blank("en"),
            },
        )


@lru_cache(maxsize=1)
def _build_analyzer_engine() -> tuple[AnalyzerEngine, bool]:
    """Initialize Presidio AnalyzerEngine with spaCy models or graceful blank fallback."""
    fr_available = spacy.util.is_package("fr_core_news_md")
    en_available = spacy.util.is_package("en_core_web_md")

    nlp_engine: NlpEngine
    ner_loaded = False

    if fr_available and en_available:
        nlp_engine = SpacyNlpEngine(
            models=[
                {"lang_code": "fr", "model_name": "fr_core_news_md"},
                {"lang_code": "en", "model_name": "en_core_web_md"},
            ]
        )
        nlp_engine.load()
        ner_loaded = True
    elif fr_available:
        nlp_engine = SpacyNlpEngine(models=[{"lang_code": "fr", "model_name": "fr_core_news_md"}])
        nlp_engine.load()
        cast(dict[str, Any], nlp_engine.nlp)["en"] = spacy.blank("en")
        ner_loaded = True
    elif en_available:
        nlp_engine = SpacyNlpEngine(models=[{"lang_code": "en", "model_name": "en_core_web_md"}])
        nlp_engine.load()
        cast(dict[str, Any], nlp_engine.nlp)["fr"] = spacy.blank("fr")
        ner_loaded = True
    else:
        logger.warning(
            "spaCy NER models (fr_core_news_md / en_core_web_md) not found; "
            "using blank spaCy fallback with custom rule recognizers."
        )
        nlp_engine = _BlankSpacyNlpEngine(
            models=[
                {"lang_code": "fr", "model_name": "fr"},
                {"lang_code": "en", "model_name": "en"},
            ]
        )
        nlp_engine.load()

    registry = RecognizerRegistry(supported_languages=["fr", "en"])
    for lang in ("fr", "en"):
        for recognizer in build_custom_recognizers(lang):
            registry.add_recognizer(recognizer)

    engine = AnalyzerEngine(
        nlp_engine=nlp_engine,
        registry=registry,
        supported_languages=["fr", "en"],
    )
    return engine, ner_loaded


def _detect_header_name_span(text: str) -> RecognizerResult | None:
    """Detect a candidate name on the first non-empty line when NER models are absent."""
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped:
            offset += len(line)
            continue
        if _HEADER_NAME_RE.match(stripped):
            words = {w.lower() for w in stripped.split()}
            if not words.intersection(_NON_NAME_HEADER_WORDS):
                start = offset + line.index(stripped)
                return RecognizerResult(
                    entity_type="PERSON",
                    start=start,
                    end=start + len(stripped),
                    score=0.80,
                )
        break
    return None


def _resolve_overlaps(results: list[RecognizerResult]) -> list[RecognizerResult]:
    """Resolve overlapping entity spans, preferring higher score then longer span."""
    ordered = sorted(
        results,
        key=lambda r: (-r.score, -(r.end - r.start), r.start),
    )
    kept: list[RecognizerResult] = []
    for candidate in ordered:
        if any(
            not (candidate.end <= existing.start or candidate.start >= existing.end)
            for existing in kept
        ):
            continue
        kept.append(candidate)
    return sorted(kept, key=lambda r: r.start)


def anonymize_text(
    text: str,
    *,
    language: str = "fr",
    extra_names: list[str] | None = None,
) -> AnonymizationResult:
    """Anonymize PII locally before any external LLM call.

    Replaces detected PII with reversible indexed placeholders (e.g. [EMAIL_1])
    and returns the anonymized text alongside the local mapping dictionary.
    """
    if not text:
        return AnonymizationResult(
            anonymized_text="",
            mapping={},
            entities_found=[],
            ner_model_loaded=False,
        )

    lang = language if language in ("fr", "en") else "fr"
    engine, ner_loaded = _build_analyzer_engine()

    results = list(
        engine.analyze(
            text=text,
            language=lang,
            entities=_SUPPORTED_ENTITIES,
        )
    )

    header_span = _detect_header_name_span(text)
    if header_span is not None:
        results.append(header_span)

    if extra_names:
        for name in extra_names:
            cleaned = name.strip()
            if not cleaned:
                continue
            for match in re.finditer(re.escape(cleaned), text, re.IGNORECASE):
                results.append(
                    RecognizerResult(
                        entity_type="PERSON",
                        start=match.start(),
                        end=match.end(),
                        score=0.99,
                    )
                )

    resolved = _resolve_overlaps(results)

    counters: dict[str, int] = {}
    value_to_placeholder: dict[tuple[str, str], str] = {}
    mapping: dict[str, str] = {}
    entities_found: list[str] = []

    out_parts: list[str] = []
    cursor = 0
    for span in resolved:
        out_parts.append(text[cursor : span.start])
        raw_value = text[span.start : span.end]
        prefix = _ENTITY_PLACEHOLDER_PREFIX.get(span.entity_type, span.entity_type)

        key = (prefix, raw_value)
        if key in value_to_placeholder:
            placeholder = value_to_placeholder[key]
        else:
            counters[prefix] = counters.get(prefix, 0) + 1
            placeholder = f"[{prefix}_{counters[prefix]}]"
            value_to_placeholder[key] = placeholder
            mapping[placeholder] = raw_value
            if prefix not in entities_found:
                entities_found.append(prefix)

        out_parts.append(placeholder)
        cursor = span.end

    out_parts.append(text[cursor:])

    return AnonymizationResult(
        anonymized_text="".join(out_parts),
        mapping=mapping,
        entities_found=entities_found,
        ner_model_loaded=ner_loaded,
    )


def deanonymize_text(text: str, mapping: dict[str, str]) -> str:
    """Restore original PII values from placeholders using the local mapping."""
    result = text
    for placeholder, original in mapping.items():
        result = result.replace(placeholder, original)
    return result


__all__ = [
    "AnonymizationResult",
    "anonymize_text",
    "deanonymize_text",
    "decrypt_pii_map",
    "encrypt_pii_map",
]
