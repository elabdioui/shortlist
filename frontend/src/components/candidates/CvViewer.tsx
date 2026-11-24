// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { ChevronLeft, ChevronRight, Eye, FileText, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { candidatesApi } from "@/lib/api/client";
import { cn } from "@/lib/utils";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

export interface TextSpan {
  start: number;
  end: number;
}

const REDACTION_TOKEN_RE = /\[[A-Z0-9_]+\]/g;

/**
 * Normalize text by collapsing whitespace runs to a single space (lowercased),
 * while keeping a map from each normalized character index back to the original string index.
 */
function normalizeWithIndexMap(text: string): {
  norm: string;
  origIndex: number[];
} {
  let norm = "";
  const origIndex: number[] = [];
  let inWhitespace = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text.charAt(i);
    if (/\s/.test(ch)) {
      if (!inWhitespace && norm.length > 0) {
        norm += " ";
        origIndex.push(i);
      }
      inWhitespace = true;
    } else {
      inWhitespace = false;
      norm += ch.toLowerCase();
      origIndex.push(i);
    }
  }
  return { norm, origIndex };
}

/**
 * Find a quote inside `text` using whitespace-insensitive matching and ignoring
 * redaction tokens like `[ENTREPRISE_1]` or `[COMPANY_1]`.
 */
export function findQuoteRange(text: string, quote: string | null): TextSpan | null {
  if (!quote || !quote.trim() || !text) return null;

  const { norm, origIndex } = normalizeWithIndexMap(text);
  if (!norm) return null;

  // Split quote around redaction tokens so we match the non-redacted parts in order
  const rawSegments = quote
    .split(REDACTION_TOKEN_RE)
    .map((seg) => seg.replace(/\s+/g, " ").trim().toLowerCase())
    .filter((seg) => seg.length >= 3);

  if (rawSegments.length === 0) return null;

  const firstSeg = rawSegments[0]!;
  let searchFrom = 0;
  while (searchFrom < norm.length) {
    const startNorm = norm.indexOf(firstSeg, searchFrom);
    if (startNorm === -1) return null;

    let cursor = startNorm + firstSeg.length;
    let allMatched = true;

    for (let s = 1; s < rawSegments.length; s++) {
      const seg = rawSegments[s]!;
      const nextIdx = norm.indexOf(seg, cursor);
      if (nextIdx === -1 || nextIdx - cursor > 160) {
        allMatched = false;
        break;
      }
      cursor = nextIdx + seg.length;
    }

    if (allMatched) {
      const origStart = origIndex[startNorm];
      const origLast = origIndex[Math.max(startNorm, cursor - 1)];
      if (origStart !== undefined && origLast !== undefined) {
        return { start: origStart, end: origLast + 1 };
      }
    }
    searchFrom = startNorm + 1;
  }

  // Fallback: match the longest non-redacted segment
  const longest = [...rawSegments].sort((a, b) => b.length - a.length)[0];
  if (longest && longest.length >= 6) {
    const idx = norm.indexOf(longest);
    if (idx !== -1) {
      const origStart = origIndex[idx];
      const origLast = origIndex[idx + longest.length - 1];
      if (origStart !== undefined && origLast !== undefined) {
        return { start: origStart, end: origLast + 1 };
      }
    }
  }

  return null;
}

function HighlightedText({
  text,
  quote,
  span,
}: {
  text: string;
  quote: string | null;
  span?: TextSpan | null;
}) {
  const range = useMemo(() => {
    if (span && span.start >= 0 && span.end > span.start && span.end <= text.length) {
      return span;
    }
    return findQuoteRange(text, quote);
  }, [text, quote, span]);

  if (!range) {
    return <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{text}</pre>;
  }

  const before = text.slice(0, range.start);
  const match = text.slice(range.start, range.end);
  const after = text.slice(range.end);

  return (
    <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
      {before}
      <mark className="evidence-highlight">{match}</mark>
      {after}
    </pre>
  );
}

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function CvViewer({
  candidateId,
  filename,
  anonymizedText,
  previewText,
  sendsExternalData,
  highlightedQuote,
  highlightedSpan,
}: {
  candidateId: string;
  filename: string;
  anonymizedText: string;
  previewText: string | null;
  sendsExternalData: boolean | null;
  highlightedQuote: string | null;
  highlightedSpan?: TextSpan | null;
}) {
  const t = useTranslations();
  const isPdf = filename.toLowerCase().endsWith(".pdf");
  const [viewMode, setViewMode] = useState<"original" | "anonymized">("original");
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [pdfFailed, setPdfFailed] = useState(false);
  const [pageItems, setPageItems] = useState<string[]>([]);

  const fileUrl = useMemo(() => candidatesApi.fileUrl(candidateId), [candidateId]);

  const pageItemRanges = useMemo(() => {
    if (pageItems.length === 0) return { fullText: "", ranges: [] as TextSpan[] };
    const ranges: TextSpan[] = [];
    let fullText = "";
    for (const str of pageItems) {
      const start = fullText.length;
      fullText += str;
      ranges.push({ start, end: fullText.length });
      fullText += " ";
    }
    return { fullText, ranges };
  }, [pageItems]);

  const pdfMatchRange = useMemo(
    () => findQuoteRange(pageItemRanges.fullText, highlightedQuote),
    [pageItemRanges.fullText, highlightedQuote]
  );

  const textRenderer = useCallback(
    (textItem: { str: string; itemIndex: number }) => {
      if (!pdfMatchRange) return escapeHtml(textItem.str);
      const itemRange = pageItemRanges.ranges[textItem.itemIndex];
      if (!itemRange) return escapeHtml(textItem.str);

      const overlapStart = Math.max(itemRange.start, pdfMatchRange.start);
      const overlapEnd = Math.min(itemRange.end, pdfMatchRange.end);
      if (overlapStart >= overlapEnd) {
        return escapeHtml(textItem.str);
      }

      const localStart = overlapStart - itemRange.start;
      const localEnd = overlapEnd - itemRange.start;
      const before = escapeHtml(textItem.str.slice(0, localStart));
      const match = escapeHtml(textItem.str.slice(localStart, localEnd));
      const after = escapeHtml(textItem.str.slice(localEnd));
      return `${before}<mark class="evidence-highlight">${match}</mark>${after}`;
    },
    [pageItemRanges.ranges, pdfMatchRange]
  );

  const displayedText = previewText ?? anonymizedText;

  return (
    <div className="flex flex-col rounded-xl border border-[var(--border)] bg-[var(--card)]">
      {/* Header / Mode Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] p-3">
        <div className="flex items-center gap-1 rounded-lg border border-[var(--border)] p-0.5">
          <button
            type="button"
            onClick={() => setViewMode("original")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium cursor-pointer",
              viewMode === "original"
                ? "bg-[var(--primary)] text-white"
                : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            )}
          >
            <FileText className="h-3.5 w-3.5" />
            <span>{t("candidate.originalCv")}</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode("anonymized")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium cursor-pointer",
              viewMode === "anonymized"
                ? "bg-[var(--primary)] text-white"
                : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            )}
          >
            <Eye className="h-3.5 w-3.5" />
            <span>{t("candidate.anonymizedPreview")}</span>
          </button>
        </div>

        {sendsExternalData !== null && (
          <Badge variant={sendsExternalData ? "warning" : "success"}>
            <ShieldCheck className="h-3 w-3" />
            <span>
              {sendsExternalData ? t("candidate.anonymizedNotice") : t("common.localPrivacy")}
            </span>
          </Badge>
        )}
      </div>

      {highlightedQuote && (
        <div className="border-b border-[var(--border)] bg-amber-50/80 px-4 py-2 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <span className="font-semibold">{t("candidate.highlightedQuote")} </span>
          <span className="italic">&laquo;{highlightedQuote}&raquo;</span>
        </div>
      )}

      {/* Body */}
      <div className="max-h-[72vh] overflow-auto p-4">
        {viewMode === "anonymized" ? (
          <div className="space-y-3">
            <Alert variant="info">{t("candidate.anonymizedNotice")}</Alert>
            <HighlightedText text={displayedText} quote={highlightedQuote} span={highlightedSpan} />
          </div>
        ) : isPdf && !pdfFailed ? (
          <div className="flex flex-col items-center gap-3">
            <Document
              file={fileUrl}
              onLoadSuccess={({ numPages: total }) => setNumPages(total)}
              onLoadError={() => setPdfFailed(true)}
              loading={
                <div className="py-12 text-sm text-[var(--muted-foreground)]">
                  {t("candidate.loadingPdf")}
                </div>
              }
            >
              <Page
                pageNumber={pageNumber}
                width={540}
                onGetTextSuccess={(textContent) => {
                  const strs = textContent.items.map((item) => ("str" in item ? item.str : ""));
                  setPageItems(strs);
                }}
                customTextRenderer={textRenderer}
                renderTextLayer
                renderAnnotationLayer={false}
              />
            </Document>
            {numPages > 1 && (
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={pageNumber <= 1}
                  onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
                >
                  <ChevronLeft className="h-4 w-4" />
                  <span>{t("candidate.prevPage")}</span>
                </Button>
                <span className="text-xs text-[var(--muted-foreground)]">
                  {t("candidate.pageOf", { page: pageNumber, total: numPages })}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={pageNumber >= numPages}
                  onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
                >
                  <span>{t("candidate.nextPage")}</span>
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {isPdf && pdfFailed && <Alert variant="warning">{t("candidate.pdfError")}</Alert>}
            <HighlightedText text={displayedText} quote={highlightedQuote} />
          </div>
        )}
      </div>
    </div>
  );
}
