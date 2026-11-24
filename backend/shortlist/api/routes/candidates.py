# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Candidate CV upload, anonymization preview, file serving, erasure, and human decisions."""

from __future__ import annotations

import uuid
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from shortlist.api.auth import record_audit
from shortlist.api.deps import get_app_settings, get_db_session, require_roles
from shortlist.api.schemas import AnonymizedPreviewResponse, CandidateUploadResponse
from shortlist.config import Settings
from shortlist.core.anonymize.anonymizer import anonymize_text
from shortlist.core.extract.pipeline import extract_cv
from shortlist.core.ingest.ingestor import IngestError, ingest_file
from shortlist.core.scoring.scorer import score_candidate
from shortlist.db.models import (
    Candidate,
    CriteriaSet,
    Decision,
    Evaluation,
    Job,
    ModelProfile,
    User,
)
from shortlist.llm.providers import is_external_provider
from shortlist.schemas.candidates import (
    CandidateDetail,
    CandidateSummary,
    DecisionCreate,
    DecisionResponse,
    EvaluationResult,
    VerifiedCriterionResult,
)
from shortlist.schemas.common import (
    ExtractionStatus,
    ProviderType,
    Recommendation,
    UserRole,
)
from shortlist.schemas.jobs import CriterionItem
from shortlist.schemas.providers import ModelProfileEntry
from shortlist.worker.fake_llm import is_fake_llm_enabled

router = APIRouter(tags=["candidates"])


def _build_evaluation_result(evaluation: Evaluation) -> EvaluationResult:
    verdicts = [VerifiedCriterionResult.model_validate(v) for v in evaluation.verified_verdicts]
    return EvaluationResult(
        id=evaluation.id,
        candidate_id=evaluation.candidate_id,
        criteria_set_version=evaluation.criteria_set_version,
        model_used=evaluation.model_used,
        fallback_used=evaluation.fallback_used,
        verdicts=verdicts,
        score=evaluation.score,
        recommendation=Recommendation(evaluation.recommendation),
        formula_version=evaluation.formula_version,
        input_tokens=evaluation.input_tokens,
        output_tokens=evaluation.output_tokens,
        cost_usd=evaluation.cost_usd,
        created_at=evaluation.created_at,
    )


def _ensure_extracted_and_anonymized(
    candidate: Candidate,
    secret_key: str,
    *,
    force_extract: bool = False,
) -> None:
    if force_extract or candidate.extraction_status == ExtractionStatus.PENDING.value:
        file_bytes = Path(candidate.stored_path).read_bytes()
        ext_res = extract_cv(file_bytes, candidate.filename)
        candidate.extracted_text = ext_res.text
        candidate.extraction_status = ext_res.status.value

    if candidate.anonymized_text is None and candidate.extracted_text:
        anon_res = anonymize_text(candidate.extracted_text)
        candidate.anonymized_text = anon_res.anonymized_text
        candidate.encrypted_pii_map = anon_res.encrypt_mapping(secret_key)


@router.post(
    "/api/jobs/{job_id}/candidates",
    response_model=CandidateUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_candidates(
    job_id: str,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> CandidateUploadResponse:
    """Upload one or more CVs (PDF, DOCX, TXT, or ZIP) with SHA-256 deduplication."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    existing_hashes = set(
        db.scalars(select(Candidate.sha256).where(Candidate.job_id == job_id)).all()
    )

    dest_dir = settings.data_dir / "files" / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    uploaded_summaries: list[CandidateSummary] = []
    duplicates_skipped: list[str] = []
    errors: list[str] = []

    for upload in files:
        raw_name = upload.filename or "cv.pdf"
        data = await upload.read()
        try:
            ingested_items = ingest_file(data, raw_name)
        except IngestError as exc:
            errors.append(f"{raw_name}: {exc}")
            continue

        for item in ingested_items:
            if item.sha256 in existing_hashes:
                duplicates_skipped.append(item.filename)
                continue

            existing_hashes.add(item.sha256)
            ext = PurePosixPath(item.filename).suffix.lower() or ".bin"
            stored_path = dest_dir / f"{uuid.uuid4()}{ext}"
            stored_path.write_bytes(item.content)

            candidate = Candidate(
                job_id=job.id,
                filename=item.filename,
                stored_path=str(stored_path),
                sha256=item.sha256,
                extraction_status=ExtractionStatus.PENDING.value,
            )
            _ensure_extracted_and_anonymized(candidate, settings.secret_key, force_extract=True)
            db.add(candidate)
            db.flush()

            uploaded_summaries.append(
                CandidateSummary(
                    id=candidate.id,
                    job_id=candidate.job_id,
                    filename=candidate.filename,
                    extraction_status=ExtractionStatus(candidate.extraction_status),
                )
            )

    record_audit(
        db,
        user.id,
        "candidates.upload",
        "job",
        job.id,
        {
            "uploaded": len(uploaded_summaries),
            "duplicates": len(duplicates_skipped),
            "errors": len(errors),
        },
    )
    db.commit()

    return CandidateUploadResponse(
        uploaded=uploaded_summaries,
        duplicates_skipped=duplicates_skipped,
        errors=errors,
    )


@router.get("/api/candidates/{candidate_id}", response_model=CandidateDetail)
def get_candidate_detail(
    candidate_id: str,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> CandidateDetail:
    """Return full candidate details including anonymized text, evaluation, and decision."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")

    latest_eval = db.scalar(
        select(Evaluation)
        .where(Evaluation.candidate_id == candidate_id)
        .order_by(Evaluation.created_at.desc())
        .limit(1)
    )
    latest_decision = db.scalar(
        select(Decision)
        .where(Decision.candidate_id == candidate_id)
        .order_by(Decision.decided_at.desc())
        .limit(1)
    )

    record_audit(db, user.id, "candidate.view", "candidate", candidate.id)
    db.commit()

    return CandidateDetail(
        id=candidate.id,
        job_id=candidate.job_id,
        filename=candidate.filename,
        sha256=candidate.sha256,
        extraction_status=ExtractionStatus(candidate.extraction_status),
        anonymized_text=candidate.anonymized_text,
        evaluation=_build_evaluation_result(latest_eval) if latest_eval else None,
        decision=DecisionResponse.model_validate(latest_decision) if latest_decision else None,
        created_at=candidate.created_at,
    )


@router.get(
    "/api/candidates/{candidate_id}/anonymized-preview",
    response_model=AnonymizedPreviewResponse,
)
def get_anonymized_preview(
    candidate_id: str,
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> AnonymizedPreviewResponse:
    """Return the exact anonymized text that will be sent to external LLM providers."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")

    if candidate.anonymized_text is None:
        _ensure_extracted_and_anonymized(candidate, settings.secret_key)
        db.commit()

    job = db.get(Job, candidate.job_id)
    sends_external = False
    if job is not None and not is_fake_llm_enabled():
        profile = db.get(ModelProfile, job.profile_id) if job.profile_id else None
        if profile is not None and profile.models:
            first_entry = ModelProfileEntry.model_validate(profile.models[0])
            sends_external = is_external_provider(ProviderType(first_entry.provider))

    return AnonymizedPreviewResponse(
        candidate_id=candidate.id,
        filename=candidate.filename,
        anonymized_text=candidate.anonymized_text or "",
        extraction_status=ExtractionStatus(candidate.extraction_status),
        sends_external_data=sends_external,
    )


@router.get("/api/candidates/{candidate_id}/file")
def download_candidate_file(
    candidate_id: str,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.READER)),
    db: Session = Depends(get_db_session),
) -> FileResponse:
    """Serve the original CV file for the authenticated viewer."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")

    file_path = Path(candidate.stored_path)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV file not found.")

    record_audit(db, user.id, "candidate.file", "candidate", candidate.id)
    db.commit()

    return FileResponse(path=file_path, filename=candidate.filename)


@router.delete("/api/candidates/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: str,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> None:
    """Delete a candidate and their stored CV file (right of erasure)."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")

    file_path = Path(candidate.stored_path)
    if file_path.is_file():
        file_path.unlink(missing_ok=True)

    record_audit(
        db,
        user.id,
        "candidate.delete",
        "candidate",
        candidate.id,
        {"filename": candidate.filename, "job_id": candidate.job_id},
    )
    db.delete(candidate)
    db.commit()


@router.post("/api/candidates/{candidate_id}/decision", response_model=DecisionResponse)
def save_candidate_decision(
    candidate_id: str,
    payload: DecisionCreate,
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
    db: Session = Depends(get_db_session),
) -> DecisionResponse:
    """Record a human decision and optional verdict overrides, recomputing score."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")
    job = db.get(Job, candidate.job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    if payload.verdict_overrides:
        latest_eval = db.scalar(
            select(Evaluation)
            .where(Evaluation.candidate_id == candidate_id)
            .order_by(Evaluation.created_at.desc())
            .limit(1)
        )
        if latest_eval is not None:
            cset = db.scalar(
                select(CriteriaSet).where(
                    CriteriaSet.job_id == job.id,
                    CriteriaSet.version == latest_eval.criteria_set_version,
                )
            )
            criteria_items = [
                CriterionItem.model_validate(c) for c in (cset.criteria if cset else [])
            ]
            verdicts = [
                VerifiedCriterionResult.model_validate(v) for v in latest_eval.verified_verdicts
            ]
            updated_verdicts: list[VerifiedCriterionResult] = []
            for v in verdicts:
                if v.id in payload.verdict_overrides:
                    new_verdict = payload.verdict_overrides[v.id]
                    updated_verdicts.append(
                        VerifiedCriterionResult(
                            id=v.id,
                            verdict=new_verdict,
                            original_verdict=v.original_verdict,
                            quote=v.quote,
                            explanation=v.explanation,
                            verified=v.verified,
                            span=v.span,
                        )
                    )
                else:
                    updated_verdicts.append(v)

            if criteria_items:
                scoring = score_candidate(
                    criteria_items,
                    updated_verdicts,
                    interview_threshold=job.interview_threshold,
                    review_threshold=job.review_threshold,
                )
                latest_eval.verified_verdicts = [
                    v.model_dump(mode="json") for v in updated_verdicts
                ]
                latest_eval.score = scoring.score
                latest_eval.recommendation = scoring.recommendation.value

    decision = Decision(
        candidate_id=candidate.id,
        user_id=user.id,
        decision=payload.decision.value,
        note=payload.note,
        verdict_overrides={k: v.value for k, v in payload.verdict_overrides.items()},
    )
    db.add(decision)
    db.flush()
    record_audit(
        db,
        user.id,
        "candidate.decision",
        "candidate",
        candidate.id,
        {
            "decision": payload.decision.value,
            "overrides": {k: v.value for k, v in payload.verdict_overrides.items()},
        },
    )
    db.commit()
    db.refresh(decision)
    return DecisionResponse.model_validate(decision)
