# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""DOCX text extraction (paragraphs, tables, and hidden-text detection)."""

from __future__ import annotations

import io
from dataclasses import dataclass

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.shared import RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

from shortlist.core.extract.pdf_extractor import HiddenTextFinding


@dataclass(frozen=True, slots=True)
class DocxExtractionOutput:
    """Raw DOCX extraction output before normalization."""

    text: str
    hidden_text_findings: list[HiddenTextFinding]


def _extract_paragraph_and_findings(
    paragraph: Paragraph,
    findings: list[HiddenTextFinding],
) -> str:
    visible_parts: list[str] = []
    for run in paragraph.runs:
        raw = run.text or ""
        if not raw.strip():
            visible_parts.append(raw)
            continue

        font = run.font
        is_hidden = bool(font.hidden)
        is_tiny = font.size is not None and font.size.pt < 2.0
        is_white = font.color is not None and font.color.rgb == RGBColor(0xFF, 0xFF, 0xFF)

        if is_hidden or is_tiny or is_white:
            reason = (
                "hidden_run" if is_hidden else ("font_below_2pt" if is_tiny else "white_on_white")
            )
            findings.append(
                HiddenTextFinding(
                    reason=reason,
                    page_number=1,
                    snippet=raw.strip()[:120],
                )
            )
        else:
            visible_parts.append(raw)

    if not paragraph.runs and paragraph.text:
        return paragraph.text.strip()
    return "".join(visible_parts).strip()


def extract_docx(data: bytes) -> DocxExtractionOutput:
    """Extract paragraphs and tables in reading order from DOCX bytes."""
    doc = Document(io.BytesIO(data))
    chunks: list[str] = []
    findings: list[HiddenTextFinding] = []

    for child in doc.element.body:
        if isinstance(child, CT_P):
            para = Paragraph(child, doc)
            text = _extract_paragraph_and_findings(para, findings)
            if text:
                chunks.append(text)
        elif isinstance(child, CT_Tbl):
            table = Table(child, doc)
            for row in table.rows:
                cells = [
                    " ".join(
                        _extract_paragraph_and_findings(p, findings) for p in cell.paragraphs
                    ).strip()
                    for cell in row.cells
                ]
                non_empty = [c for c in cells if c]
                if non_empty:
                    chunks.append(" | ".join(non_empty))

    return DocxExtractionOutput(
        text="\n".join(chunks),
        hidden_text_findings=findings,
    )
