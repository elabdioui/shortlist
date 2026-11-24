# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unified CV extraction and normalization pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from shortlist.core.extract.docx_extractor import extract_docx
from shortlist.core.extract.normalizer import (
    MAX_APPROX_TOKENS,
    detect_language,
    normalize_text,
)
from shortlist.core.extract.pdf_extractor import HiddenTextFinding, extract_pdf
from shortlist.core.ingest.ingestor import MIME_DOCX, MIME_PDF, MIME_TXT, detect_mime_type
from shortlist.schemas.common import ExtractionStatus


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Normalized CV text and extraction metadata."""

    text: str
    status: ExtractionStatus
    page_count: int
    language: str
    ocr_used: bool
    hidden_text_detected: bool
    hidden_text_findings: list[HiddenTextFinding]
    truncated: bool
    truncation_warning: str | None
    engine: str
    error: str | None = None


def _decode_txt(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def extract_cv(
    data: bytes,
    filename: str,
    *,
    mime_type: str | None = None,
    enable_ocr: bool = True,
    max_tokens: int = MAX_APPROX_TOKENS,
) -> ExtractionResult:
    """Extract and normalize text from a PDF, DOCX, or TXT CV."""
    try:
        resolved_mime = mime_type or detect_mime_type(data, filename)
    except Exception as exc:
        return ExtractionResult(
            text="",
            status=ExtractionStatus.FAILED,
            page_count=0,
            language="unknown",
            ocr_used=False,
            hidden_text_detected=False,
            hidden_text_findings=[],
            truncated=False,
            truncation_warning=None,
            engine="none",
            error=str(exc),
        )

    raw_text = ""
    page_count = 1
    ocr_used = False
    findings: list[HiddenTextFinding] = []
    engine = "txt"

    try:
        if resolved_mime == MIME_PDF:
            pdf_out = extract_pdf(data, enable_ocr=enable_ocr)
            raw_text = pdf_out.text
            page_count = pdf_out.page_count
            ocr_used = pdf_out.ocr_used
            findings = pdf_out.hidden_text_findings
            engine = pdf_out.engine
        elif resolved_mime == MIME_DOCX:
            docx_out = extract_docx(data)
            raw_text = docx_out.text
            findings = docx_out.hidden_text_findings
            engine = "python-docx"
        elif resolved_mime == MIME_TXT:
            raw_text = _decode_txt(data)
            engine = "txt"
        else:
            return ExtractionResult(
                text="",
                status=ExtractionStatus.FAILED,
                page_count=0,
                language="unknown",
                ocr_used=False,
                hidden_text_detected=False,
                hidden_text_findings=[],
                truncated=False,
                truncation_warning=None,
                engine="none",
                error=f"Unsupported MIME type: {resolved_mime}",
            )
    except Exception as exc:
        return ExtractionResult(
            text="",
            status=ExtractionStatus.FAILED,
            page_count=0,
            language="unknown",
            ocr_used=False,
            hidden_text_detected=False,
            hidden_text_findings=[],
            truncated=False,
            truncation_warning=None,
            engine=engine,
            error=str(exc),
        )

    norm = normalize_text(raw_text, max_tokens=max_tokens)
    hidden_detected = len(findings) > 0

    if not norm.text.strip():
        status = (
            ExtractionStatus.HIDDEN_TEXT_FLAGGED if hidden_detected else ExtractionStatus.FAILED
        )
    elif hidden_detected:
        status = ExtractionStatus.HIDDEN_TEXT_FLAGGED
    elif ocr_used:
        status = ExtractionStatus.OCR_EXTRACTED
    else:
        status = ExtractionStatus.EXTRACTED

    return ExtractionResult(
        text=norm.text,
        status=status,
        page_count=page_count,
        language=detect_language(norm.text),
        ocr_used=ocr_used,
        hidden_text_detected=hidden_detected,
        hidden_text_findings=findings,
        truncated=norm.truncated,
        truncation_warning=norm.truncation_warning,
        engine=engine,
        error=None if norm.text.strip() else "No extractable text found in document.",
    )
