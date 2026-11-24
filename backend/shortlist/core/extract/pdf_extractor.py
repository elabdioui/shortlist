# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""PDF text extraction using PyMuPDF (1- and 2-column), pdfplumber fallback, and Tesseract OCR."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

import fitz
import pdfplumber
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

MIN_USEFUL_CHARS_PER_PAGE = 200
MIN_VISIBLE_FONT_SIZE_PT = 2.0
WHITE_RGB_THRESHOLD = 250


@dataclass(frozen=True, slots=True)
class HiddenTextFinding:
    """Detected hidden or suspicious text span in a document."""

    reason: str
    page_number: int
    snippet: str


@dataclass(frozen=True, slots=True)
class PDFExtractionOutput:
    """Raw PDF extraction output before normalization."""

    text: str
    page_count: int
    ocr_used: bool
    hidden_text_findings: list[HiddenTextFinding]
    engine: str


@dataclass(frozen=True, slots=True)
class _TextBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def _is_white_color(color_int: int) -> bool:
    red = (color_int >> 16) & 0xFF
    green = (color_int >> 8) & 0xFF
    blue = color_int & 0xFF
    return (
        red >= WHITE_RGB_THRESHOLD and green >= WHITE_RGB_THRESHOLD and blue >= WHITE_RGB_THRESHOLD
    )


def _is_off_page(bbox: tuple[float, float, float, float], width: float, height: float) -> bool:
    x0, y0, x1, y1 = bbox
    return x1 < 0.0 or y1 < 0.0 or x0 > width or y0 > height


def _non_white_fill_rects(page: fitz.Page) -> list[fitz.Rect]:
    """Return bounding rects of filled drawings that are visibly non-white."""
    rects: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        rect = drawing.get("rect")
        if fill is None or rect is None or len(fill) < 3:
            continue
        if any(float(channel) < 0.85 for channel in fill[:3]):
            rects.append(fitz.Rect(rect))
    return rects


def _has_colored_background(
    bbox: tuple[float, float, float, float],
    colored_rects: list[fitz.Rect],
) -> bool:
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    point = fitz.Point(cx, cy)
    return any(rect.contains(point) for rect in colored_rects)


def _extract_visible_blocks_and_findings(
    page: fitz.Page,
    page_number: int,
) -> tuple[list[_TextBlock], list[HiddenTextFinding]]:
    """Inspect spans for hidden text and return only visible text blocks."""
    page_dict: dict[str, Any] = page.get_text("dict", clip=fitz.INFINITE_RECT())
    width = float(page.rect.width)
    height = float(page.rect.height)
    colored_rects = _non_white_fill_rects(page)

    visible_blocks: list[_TextBlock] = []
    findings: list[HiddenTextFinding] = []

    for block in page_dict.get("blocks", []):
        if block.get("type", 0) != 0:
            continue

        line_texts: list[str] = []
        for line in block.get("lines", []):
            span_texts: list[str] = []
            for span in line.get("spans", []):
                raw_text = str(span.get("text", ""))
                if not raw_text.strip():
                    if raw_text:
                        span_texts.append(raw_text)
                    continue

                size = float(span.get("size", 10.0))
                color = int(span.get("color", 0))
                alpha = span.get("alpha", 255)
                raw_bbox = span.get("bbox", (0.0, 0.0, 0.0, 0.0))
                bbox = (
                    float(raw_bbox[0]),
                    float(raw_bbox[1]),
                    float(raw_bbox[2]),
                    float(raw_bbox[3]),
                )

                reason: str | None = None
                if size < MIN_VISIBLE_FONT_SIZE_PT:
                    reason = "font_below_2pt"
                elif _is_white_color(color) and not _has_colored_background(bbox, colored_rects):
                    reason = "white_on_white"
                elif alpha == 0:
                    reason = "zero_opacity"
                elif _is_off_page(bbox, width, height):
                    reason = "off_page"

                if reason is not None:
                    findings.append(
                        HiddenTextFinding(
                            reason=reason,
                            page_number=page_number,
                            snippet=raw_text.strip()[:120],
                        )
                    )
                else:
                    span_texts.append(raw_text)

            joined_line = "".join(span_texts).strip()
            if joined_line:
                line_texts.append(joined_line)

        block_text = "\n".join(line_texts).strip()
        if block_text:
            b_bbox = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
            visible_blocks.append(
                _TextBlock(
                    x0=float(b_bbox[0]),
                    y0=float(b_bbox[1]),
                    x1=float(b_bbox[2]),
                    y1=float(b_bbox[3]),
                    text=block_text,
                )
            )

    return visible_blocks, findings


def _find_column_gutter(blocks: list[_TextBlock], page_width: float) -> float | None:
    """Find a vertical gutter separating two text columns, or None for 1-column pages.

    A gutter is an x position that no body block crosses, with a meaningful
    amount of text on each side. Blocks crossing it are allowed only above the
    columns (page header such as the candidate name) or below them (footer).
    Pages laid out as rows (dates on the left, details on the right, with
    full-width titles between rows) have no such gutter and are read top-down.
    """
    text_blocks = [b for b in blocks if len(b.text.strip()) > 2 and (b.x1 - b.x0) > 12.0]
    if len(text_blocks) < 4:
        return None
    total_chars = sum(len(b.text) for b in text_blocks)
    best: tuple[float, float] | None = None  # (balance, x)

    step = 4.0
    x = page_width * 0.18
    while x <= page_width * 0.82:
        left = [b for b in text_blocks if b.x1 <= x]
        right = [b for b in text_blocks if b.x0 >= x]
        crossing = [b for b in text_blocks if b.x0 < x < b.x1]
        left_chars = sum(len(b.text) for b in left)
        right_chars = sum(len(b.text) for b in right)
        if (
            left
            and right
            and left_chars >= 0.12 * total_chars
            and right_chars >= 0.12 * total_chars
        ):
            body_top = min(min(b.y0 for b in left), min(b.y0 for b in right))
            body_bottom = max(max(b.y1 for b in left), max(b.y1 for b in right))
            columns_overlap = min(max(b.y1 for b in left), max(b.y1 for b in right)) > max(
                min(b.y0 for b in left), min(b.y0 for b in right)
            )
            if columns_overlap and all(
                b.y1 <= body_top + 5.0 or b.y0 >= body_bottom - 5.0 for b in crossing
            ):
                balance = min(left_chars, right_chars) / max(left_chars, right_chars)
                if best is None or balance > best[0]:
                    best = (balance, x)
        x += step
    return best[1] if best else None


def _order_blocks_reading_order(blocks: list[_TextBlock], page_width: float) -> list[_TextBlock]:
    """Order blocks for 1-column, 2-column (incl. sidebar), and row-based layouts."""
    if len(blocks) <= 1 or page_width <= 0:
        return sorted(blocks, key=lambda b: (b.y0, b.x0))

    gutter = _find_column_gutter(blocks, page_width)
    if gutter is None:
        return sorted(blocks, key=lambda b: (b.y0, b.x0))

    left_col = [b for b in blocks if b.x1 <= gutter]
    right_col = [b for b in blocks if b.x0 >= gutter]
    crossing = [b for b in blocks if b.x0 < gutter < b.x1]
    body_top = min(b.y0 for b in [*left_col, *right_col])
    top_full = sorted([b for b in crossing if b.y0 < body_top + 5.0], key=lambda b: (b.y0, b.x0))
    bottom_full = sorted(
        [b for b in crossing if b.y0 >= body_top + 5.0], key=lambda b: (b.y0, b.x0)
    )
    left_sorted = sorted(left_col, key=lambda b: (b.y0, b.x0))
    right_sorted = sorted(right_col, key=lambda b: (b.y0, b.x0))

    # Read left to right, except when the right column clearly starts higher
    # on the page (a sidebar layout whose main column holds the name/headline).
    right_first = right_sorted[0].y0 < left_sorted[0].y0 - 20.0
    columns = [*right_sorted, *left_sorted] if right_first else [*left_sorted, *right_sorted]
    return [*top_full, *columns, *bottom_full]


def _ocr_page(page: fitz.Page) -> str:
    """Render a PDF page to an image and run Tesseract OCR (fra+eng)."""
    pixmap = page.get_pixmap(dpi=200)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    try:
        return str(pytesseract.image_to_string(image, lang="fra+eng"))
    except (pytesseract.TesseractNotFoundError, OSError) as exc:
        logger.warning("Tesseract OCR unavailable: %s", exc)
        return ""


def _useful_char_count(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _extract_with_pdfplumber(data: bytes) -> PDFExtractionOutput:
    """Fallback PDF extraction using pdfplumber."""
    page_texts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if txt.strip():
                page_texts.append(txt.strip())

    return PDFExtractionOutput(
        text="\n\n".join(page_texts),
        page_count=page_count,
        ocr_used=False,
        hidden_text_findings=[],
        engine="pdfplumber",
    )


def extract_pdf(data: bytes, *, enable_ocr: bool = True) -> PDFExtractionOutput:
    """Extract text from PDF bytes using PyMuPDF, OCR fallback, and pdfplumber fallback."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.warning("PyMuPDF failed to open PDF, falling back to pdfplumber: %s", exc)
        return _extract_with_pdfplumber(data)

    page_texts: list[str] = []
    all_findings: list[HiddenTextFinding] = []
    ocr_used = False

    with doc:
        page_count = len(doc)
        for idx, page in enumerate(doc):
            page_num = idx + 1
            blocks, findings = _extract_visible_blocks_and_findings(page, page_num)
            all_findings.extend(findings)

            ordered = _order_blocks_reading_order(blocks, float(page.rect.width))
            page_text = "\n\n".join(b.text for b in ordered)

            if enable_ocr and _useful_char_count(page_text) < MIN_USEFUL_CHARS_PER_PAGE:
                ocr_text = _ocr_page(page).strip()
                if _useful_char_count(ocr_text) > _useful_char_count(page_text):
                    page_text = ocr_text
                    ocr_used = True

            if page_text.strip():
                page_texts.append(page_text.strip())

    return PDFExtractionOutput(
        text="\n\n".join(page_texts),
        page_count=page_count,
        ocr_used=ocr_used,
        hidden_text_findings=all_findings,
        engine="pymupdf",
    )
