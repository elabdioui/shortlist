# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Excel (.xlsx) and CSV export for job candidate rankings and justifications."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from shortlist.schemas.candidates import VerifiedCriterionResult
from shortlist.schemas.common import HumanDecision, Recommendation
from shortlist.schemas.jobs import CriterionItem

_HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)

_RECOMMENDATION_FILLS: dict[str, PatternFill] = {
    Recommendation.INTERVIEW.value: PatternFill(
        start_color="DCFCE7", end_color="DCFCE7", fill_type="solid"
    ),
    Recommendation.REVIEW.value: PatternFill(
        start_color="FEF3C7", end_color="FEF3C7", fill_type="solid"
    ),
    Recommendation.NOT_RETAINED.value: PatternFill(
        start_color="FEE2E2", end_color="FEE2E2", fill_type="solid"
    ),
    Recommendation.MANUAL_REVIEW.value: PatternFill(
        start_color="E2E8F0", end_color="E2E8F0", fill_type="solid"
    ),
}


@dataclass(frozen=True, slots=True)
class ExportRow:
    """Flattened candidate row for ranking export."""

    rank: int
    filename: str
    score: float | None
    recommendation: Recommendation | None
    decision: HumanDecision
    note: str | None
    mandatory_met: int
    mandatory_total: int
    model_used: str | None
    fallback_used: bool
    verdicts: list[VerifiedCriterionResult]


def _format_criterion_cell(verdict: VerifiedCriterionResult | None) -> str:
    if verdict is None:
        return ""
    parts = [verdict.verdict.value]
    if verdict.quote:
        parts.append(f'"{verdict.quote}"')
    if verdict.explanation:
        parts.append(verdict.explanation)
    return " | ".join(parts)


def _build_headers(criteria: list[CriterionItem]) -> list[str]:
    base = [
        "Rank",
        "Candidate",
        "Score (%)",
        "Recommendation",
        "Human Decision",
        "Mandatory Met",
        "Model Used",
        "Fallback Used",
        "Recruiter Note",
    ]
    crit_headers = [f"[{c.type.value.upper()}] {c.label} (w={c.weight})" for c in criteria]
    return base + crit_headers


def _build_row_values(row: ExportRow, criteria: list[CriterionItem]) -> list[Any]:
    verdict_map = {v.id: v for v in row.verdicts}
    values: list[Any] = [
        row.rank,
        row.filename,
        row.score if row.score is not None else "",
        row.recommendation.value if row.recommendation else "",
        row.decision.value,
        f"{row.mandatory_met}/{row.mandatory_total}",
        row.model_used or "",
        "yes" if row.fallback_used else "no",
        row.note or "",
    ]
    for crit in criteria:
        values.append(_format_criterion_cell(verdict_map.get(crit.id)))
    return values


def export_ranking_csv(rows: list[ExportRow], criteria: list[CriterionItem]) -> bytes:
    """Export candidate ranking to UTF-8 BOM CSV bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_build_headers(criteria))
    for row in rows:
        writer.writerow(_build_row_values(row, criteria))
    return buf.getvalue().encode("utf-8-sig")


def export_ranking_xlsx(
    job_title: str,
    rows: list[ExportRow],
    criteria: list[CriterionItem],
) -> bytes:
    """Export candidate ranking to a formatted, colour-coded Excel (.xlsx) workbook."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Shortlist Ranking"

    headers = _build_headers(criteria)
    ws.append(headers)

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    for row in rows:
        ws.append(_build_row_values(row, criteria))
        excel_row = ws.max_row
        rec_val = row.recommendation.value if row.recommendation else ""
        rec_fill = _RECOMMENDATION_FILLS.get(rec_val)
        if rec_fill is not None:
            ws.cell(row=excel_row, column=4).fill = rec_fill
        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=excel_row, column=col_idx).alignment = Alignment(
                vertical="top", wrap_text=True
            )

    ws.freeze_panes = "A2"
    last_col = get_column_letter(len(headers))
    ws.auto_filter.ref = f"A1:{last_col}{max(1, ws.max_row)}"

    # Set readable column widths.
    widths = [8, 28, 12, 18, 16, 15, 22, 14, 30] + [36] * len(criteria)
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.views.sheetView[0].showGridLines = True

    # Add a metadata sheet for traceability.
    meta = wb.create_sheet(title="Job Info")
    meta.append(["Job Title", job_title])
    meta.append(["Total Candidates", len(rows)])
    meta.append(["Criteria Count", len(criteria)])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
