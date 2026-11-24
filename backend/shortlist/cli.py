# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shortlist CLI entrypoint (`shortlist`)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import typer

from shortlist import __version__
from shortlist.api.export import ExportRow, export_ranking_csv, export_ranking_xlsx
from shortlist.config import get_settings
from shortlist.core.anonymize.anonymizer import anonymize_text
from shortlist.core.evaluate.criteria_generator import generate_criteria
from shortlist.core.evaluate.evaluator import evaluate_cv
from shortlist.core.extract.pipeline import extract_cv
from shortlist.core.ingest.ingestor import IngestError, ingest_file
from shortlist.core.scoring.scorer import score_candidate
from shortlist.core.verify.verifier import verify_evaluation
from shortlist.db.models import ModelProfile
from shortlist.db.session import get_session_factory
from shortlist.llm.client import LLMClient
from shortlist.schemas.candidates import VerifiedCriterionResult
from shortlist.schemas.common import (
    CriterionType,
    CriterionVerdict,
    ExtractionStatus,
    HumanDecision,
)
from shortlist.schemas.jobs import CriterionItem
from shortlist.worker.fake_llm import build_deterministic_fake_llm, is_fake_llm_enabled
from shortlist.worker.llm_factory import build_llm_client_for_job

app = typer.Typer(
    name="shortlist",
    help="Open-source, self-hosted AI CV screening CLI.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the Shortlist version."""
    typer.echo(f"shortlist {__version__}")


@app.command()
def screen(
    cv_dir: Path = typer.Argument(..., exists=True, file_okay=False, help="Directory of CV files."),
    job: Path = typer.Option(
        ..., "--job", exists=True, dir_okay=False, help="Job description file."
    ),
    profile: str = typer.Option("default", "--profile", help="Model profile name."),
    out: Path = typer.Option(
        Path("shortlist_ranking.xlsx"),
        "--out",
        help="Output path (.xlsx or .csv).",
    ),
    fake_llm: bool = typer.Option(
        False,
        "--fake-llm",
        help="Use deterministic FakeLLMClient instead of calling external APIs.",
    ),
) -> None:
    """Screen a directory of CVs against a job description and export a ranking."""
    job_text = job.read_text(encoding="utf-8")
    settings = get_settings()

    client: LLMClient
    if fake_llm or is_fake_llm_enabled():
        client = build_deterministic_fake_llm()
        model_name = "fake-deterministic-v1"
    else:
        session_factory = get_session_factory()
        with session_factory() as db:
            from sqlalchemy import select

            profile_row = db.scalar(select(ModelProfile).where(ModelProfile.name == profile))
            if profile_row is None:
                typer.echo(
                    f"Model profile '{profile}' not found in DB; "
                    "configure one via API or pass --fake-llm.",
                    err=True,
                )
                raise typer.Exit(code=1)
            client, _pool, model_name = build_llm_client_for_job(db, None, settings.secret_key)

    crit_result = generate_criteria(job_text, client, model=model_name)
    criteria = crit_result.criteria
    mandatory_ids = [c.id for c in criteria if c.type == CriterionType.MANDATORY]

    raw_rows: list[ExportRow] = []
    seen_hashes: set[str] = set()

    for file_path in sorted(cv_dir.iterdir()):
        if not file_path.is_file():
            continue
        try:
            ingested = ingest_file(file_path.read_bytes(), file_path.name)
        except IngestError as exc:
            typer.echo(f"Skipping {file_path.name}: {exc}", err=True)
            continue

        for item in ingested:
            if item.sha256 in seen_hashes:
                continue
            seen_hashes.add(item.sha256)

            ext_res = extract_cv(item.content, item.filename, mime_type=item.mime_type)
            anon_res = anonymize_text(ext_res.text) if ext_res.text else None
            anon_text = anon_res.anonymized_text if anon_res else ""

            hidden = ext_res.status == ExtractionStatus.HIDDEN_TEXT_FLAGGED
            failed = ext_res.status == ExtractionStatus.FAILED or not anon_text.strip()

            if failed or hidden:
                scoring = score_candidate(
                    criteria,
                    [],
                    extraction_failed=failed,
                    hidden_text_detected=hidden,
                )
                verdicts: list[VerifiedCriterionResult] = []
                used_model = "none"
            else:
                eval_res = evaluate_cv(anon_text, job_text, criteria, client, model=model_name)
                if eval_res.invalid_json or eval_res.output is None:
                    scoring = score_candidate(criteria, [], invalid_json=True)
                    verdicts = []
                else:
                    verdicts = verify_evaluation(eval_res.output, anon_text)
                    scoring = score_candidate(criteria, verdicts)
                used_model = eval_res.model_used

            verdict_map = {v.id: v.verdict for v in verdicts}
            mandatory_met = sum(
                1 for cid in mandatory_ids if verdict_map.get(cid) == CriterionVerdict.YES
            )
            raw_rows.append(
                ExportRow(
                    rank=0,
                    filename=item.filename,
                    score=scoring.score,
                    recommendation=scoring.recommendation,
                    decision=HumanDecision.PENDING,
                    note=None,
                    mandatory_met=mandatory_met,
                    mandatory_total=len(mandatory_ids),
                    model_used=used_model,
                    fallback_used=False,
                    verdicts=verdicts,
                )
            )

    raw_rows.sort(key=lambda r: (r.score is None, -(r.score or 0.0), r.filename.lower()))
    ranked_rows = [
        ExportRow(
            rank=idx,
            filename=r.filename,
            score=r.score,
            recommendation=r.recommendation,
            decision=r.decision,
            note=r.note,
            mandatory_met=r.mandatory_met,
            mandatory_total=r.mandatory_total,
            model_used=r.model_used,
            fallback_used=r.fallback_used,
            verdicts=r.verdicts,
        )
        for idx, r in enumerate(raw_rows, start=1)
    ]

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".csv":
        out.write_bytes(export_ranking_csv(ranked_rows, criteria))
    else:
        out.write_bytes(export_ranking_xlsx(job.stem, ranked_rows, criteria))

    typer.echo(f"Screened {len(ranked_rows)} CV(s) -> {out}")


def _rank_with_ties(values: list[float], *, descending: bool = False) -> list[float]:
    """Assign 1-based average ranks to numeric values."""
    indexed = sorted(enumerate(values), key=lambda pair: pair[1], reverse=descending)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def _spearman_correlation(expected_ranks: list[float], predicted_scores: list[float]) -> float:
    """Compute Spearman rank correlation between expected_ranks (1=best) and predicted_scores."""
    n = len(expected_ranks)
    if n < 2:
        return 1.0 if n == 1 else 0.0
    pred_ranks = _rank_with_ties(predicted_scores, descending=True)
    mean_exp = sum(expected_ranks) / n
    mean_pred = sum(pred_ranks) / n
    num = sum(
        (e - mean_exp) * (p - mean_pred) for e, p in zip(expected_ranks, pred_ranks, strict=True)
    )
    den_exp = math.sqrt(sum((e - mean_exp) ** 2 for e in expected_ranks))
    den_pred = math.sqrt(sum((p - mean_pred) ** 2 for p in pred_ranks))
    if den_exp == 0.0 or den_pred == 0.0:
        return 0.0
    return round(num / (den_exp * den_pred), 4)


@app.command(name="eval")
def eval_dataset(
    profile: str = typer.Option("default", "--profile", help="Model profile name to evaluate."),
    eval_dir: Path = typer.Option(
        Path("eval"),
        "--eval-dir",
        help="Path to the annotated evaluation dataset directory.",
    ),
    fake_llm: bool = typer.Option(
        False,
        "--fake-llm",
        help="Run evaluation against deterministic FakeLLMClient.",
    ),
) -> None:
    """Run the annotated evaluation benchmark against eval/<job_slug>/."""
    if not eval_dir.exists():
        typer.echo(
            json.dumps(
                {
                    "status": "no_dataset",
                    "profile": profile,
                    "eval_dir": str(eval_dir),
                    "message": "Evaluation dataset directory not found.",
                }
            )
        )
        raise typer.Exit(code=0)

    job_dirs = sorted(p for p in eval_dir.iterdir() if p.is_dir())
    if not job_dirs:
        typer.echo(
            json.dumps(
                {
                    "status": "no_jobs",
                    "profile": profile,
                    "eval_dir": str(eval_dir),
                }
            )
        )
        raise typer.Exit(code=0)

    settings = get_settings()
    client: LLMClient
    if fake_llm or is_fake_llm_enabled():
        client = build_deterministic_fake_llm()
        model_name = "fake-deterministic-v1"
    else:
        session_factory = get_session_factory()
        with session_factory() as db:
            from sqlalchemy import select

            profile_row = db.scalar(select(ModelProfile).where(ModelProfile.name == profile))
            if profile_row is None:
                typer.echo(
                    f"Model profile '{profile}' not found in DB; "
                    "configure one via API or pass --fake-llm.",
                    err=True,
                )
                raise typer.Exit(code=1)
            client, _pool, model_name = build_llm_client_for_job(db, None, settings.secret_key)

    total_criteria_checks = 0
    total_criteria_matches = 0
    total_claim_verdicts = 0
    total_verified_quotes = 0
    job_reports: list[dict[str, object]] = []

    for job_dir in job_dirs:
        job_file = job_dir / "job.txt"
        criteria_file = job_dir / "criteria.json"
        annotations_file = job_dir / "annotations.json"
        cvs_dir = job_dir / "cvs"
        if not (
            job_file.is_file()
            and criteria_file.is_file()
            and annotations_file.is_file()
            and cvs_dir.is_dir()
        ):
            continue

        job_text = job_file.read_text(encoding="utf-8")
        criteria = [
            CriterionItem.model_validate(item)
            for item in json.loads(criteria_file.read_text(encoding="utf-8"))
        ]
        annotations: dict[str, dict[str, object]] = json.loads(
            annotations_file.read_text(encoding="utf-8")
        )

        job_checks = 0
        job_matches = 0
        job_claims = 0
        job_verified = 0
        expected_ranks: list[float] = []
        predicted_scores: list[float] = []

        for cv_path in sorted(cvs_dir.iterdir()):
            if not cv_path.is_file():
                continue
            ann = annotations.get(cv_path.name)
            if ann is None:
                continue

            ext_res = extract_cv(cv_path.read_bytes(), cv_path.name)
            anon_res = anonymize_text(ext_res.text) if ext_res.text else None
            anon_text = anon_res.anonymized_text if anon_res else ""

            eval_res = evaluate_cv(anon_text, job_text, criteria, client, model=model_name)
            verdicts: list[VerifiedCriterionResult] = []
            if not eval_res.invalid_json and eval_res.output is not None:
                verdicts = verify_evaluation(eval_res.output, anon_text)
            scoring = score_candidate(criteria, verdicts)

            verdict_map = {v.id: v for v in verdicts}
            expected_verdicts = ann.get("expected_verdicts", {})
            if isinstance(expected_verdicts, dict):
                for cid, exp_verdict in expected_verdicts.items():
                    job_checks += 1
                    actual = verdict_map.get(str(cid))
                    if actual is not None and actual.verdict.value == str(exp_verdict):
                        job_matches += 1

            for v in verdicts:
                if v.original_verdict in (CriterionVerdict.YES, CriterionVerdict.PARTIAL):
                    job_claims += 1
                    if v.verified:
                        job_verified += 1

            exp_rank = ann.get("expected_rank")
            if isinstance(exp_rank, (int, float)):
                expected_ranks.append(float(exp_rank))
                predicted_scores.append(scoring.score)

        total_criteria_checks += job_checks
        total_criteria_matches += job_matches
        total_claim_verdicts += job_claims
        total_verified_quotes += job_verified

        job_reports.append(
            {
                "job_slug": job_dir.name,
                "cv_count": len(expected_ranks),
                "per_criterion_agreement": round(job_matches / job_checks, 4)
                if job_checks
                else 0.0,
                "spearman_correlation": _spearman_correlation(expected_ranks, predicted_scores),
                "verified_quote_rate": round(job_verified / job_claims, 4) if job_claims else 1.0,
            }
        )

    avg_spearman = (
        round(
            sum(float(str(r["spearman_correlation"])) for r in job_reports) / len(job_reports),
            4,
        )
        if job_reports
        else 0.0
    )

    typer.echo(
        json.dumps(
            {
                "status": "ok",
                "profile": profile,
                "fake_llm": fake_llm or is_fake_llm_enabled(),
                "jobs_evaluated": len(job_reports),
                "per_criterion_agreement": round(total_criteria_matches / total_criteria_checks, 4)
                if total_criteria_checks
                else 0.0,
                "spearman_correlation": avg_spearman,
                "verified_quote_rate": round(total_verified_quotes / total_claim_verdicts, 4)
                if total_claim_verdicts
                else 1.0,
                "jobs": job_reports,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
