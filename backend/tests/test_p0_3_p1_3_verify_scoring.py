# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Test-first regression suite for P0-3 (NO verification & scoring v2) and P1-3 (quote length & offset mapping)."""

from __future__ import annotations

from shortlist.core.evaluate import load_prompt
from shortlist.core.scoring import FORMULA_VERSION, compute_recommendation, score_candidate
from shortlist.core.verify import verify_criterion, verify_quote
from shortlist.schemas.candidates import LLMOutputCriterion, VerifiedCriterionResult
from shortlist.schemas.common import CriterionType, CriterionVerdict, Recommendation
from shortlist.schemas.jobs import CriterionItem


def _mandatory_criterion() -> CriterionItem:
    return CriterionItem(
        id="c1",
        label="Supply chain experience",
        description="At least 3 years in supply chain",
        type=CriterionType.MANDATORY,
        weight=5,
    )


def test_p0_3_no_without_verified_quote_downgrades_to_unproven() -> None:
    cv_text = "5 ans en tant qu'acheteur industriel chez Atlas Pack."

    no_empty = verify_criterion(
        LLMOutputCriterion(
            id="c1",
            verdict=CriterionVerdict.NO,
            quote="",
            explanation="No experience.",
        ),
        cv_text,
    )
    assert no_empty.verdict == CriterionVerdict.UNPROVEN
    assert no_empty.original_verdict == CriterionVerdict.NO
    assert no_empty.verified is False
    assert no_empty.span is None

    no_hallucinated = verify_criterion(
        LLMOutputCriterion(
            id="c1",
            verdict=CriterionVerdict.NO,
            quote="Candidate explicitly states zero years of supply chain experience.",
            explanation="Contradiction claimed.",
        ),
        cv_text,
    )
    assert no_hallucinated.verdict == CriterionVerdict.UNPROVEN
    assert no_hallucinated.original_verdict == CriterionVerdict.NO
    assert no_hallucinated.verified is False


def test_p0_3_only_verified_mandatory_no_triggers_not_retained_and_formula_v2() -> None:
    assert FORMULA_VERSION == "v2"
    criteria = [
        _mandatory_criterion(),
        CriterionItem(
            id="c2",
            label="SAP MM",
            description="SAP MM knowledge",
            type=CriterionType.BONUS,
            weight=1,
        ),
    ]

    # Unverified NO on mandatory criterion must NOT trigger NOT_RETAINED when score >= 45
    unverified_no = [
        VerifiedCriterionResult(
            id="c1",
            verdict=CriterionVerdict.NO,
            original_verdict=CriterionVerdict.NO,
            quote="",
            explanation="Unverified.",
            verified=False,
        ),
        VerifiedCriterionResult(
            id="c2",
            verdict=CriterionVerdict.YES,
            original_verdict=CriterionVerdict.YES,
            quote="Maîtrise quotidienne de SAP MM en production",
            explanation="Present.",
            verified=True,
        ),
    ]
    rec = compute_recommendation(50.0, criteria, unverified_no)
    assert rec == Recommendation.REVIEW

    # Verified NO on mandatory criterion DOES trigger NOT_RETAINED even if score >= 45
    verified_no = [
        VerifiedCriterionResult(
            id="c1",
            verdict=CriterionVerdict.NO,
            original_verdict=CriterionVerdict.NO,
            quote="Débutant sans aucune expérience en supply chain",
            explanation="Explicitly lacks experience.",
            verified=True,
        ),
        unverified_no[1],
    ]
    res = score_candidate(criteria, verified_no, review_threshold=10.0)
    assert res.recommendation == Recommendation.NOT_RETAINED
    assert res.formula_version == "v2"


def test_p0_3_evaluate_v2_prompt_exists_and_requires_contradiction_quote() -> None:
    v2 = load_prompt("evaluate", "v2")
    assert "<<<UNTRUSTED_CV_START>>>" in v2
    assert "no" in v2.lower()
    assert "not_found" in v2.lower()


def test_p1_3_short_quote_rejected_and_multiline_normalized_offsets_mapped() -> None:
    cv_text = (
        "Expérience professionnelle :\n"
        "5 ans   en tant qu'acheteur\n"
        "industriel senior chez Atlas Pack.\n"
        "Outils : SAP MM."
    )

    # Short quote (< 4 words and < 20 chars) must be rejected -> UNPROVEN
    short_res = verify_criterion(
        LLMOutputCriterion(
            id="c1",
            verdict=CriterionVerdict.YES,
            quote="SAP MM",
            explanation="Uses SAP MM.",
        ),
        cv_text,
    )
    assert short_res.verdict == CriterionVerdict.UNPROVEN
    assert short_res.verified is False
    assert short_res.span is None

    # Quote spanning newline + extra spaces must match and map back to original cv_text offsets
    quote = "5 ans en tant qu'acheteur industriel senior chez Atlas Pack."
    span = verify_quote(quote, cv_text)
    assert span is not None
    assert span.match_score >= 90.0
    sliced = cv_text[span.start : span.end]
    assert "5 ans" in sliced
    assert "Atlas Pack" in sliced
