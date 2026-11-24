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

function HighlightedText({ text, quote }: { text: string; quote: string | null }) {
  if (!quote || !quote.trim()) {
    return <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{text}</pre>;
  }

  const trimmed = quote.trim();
  const idx = text.toLowerCase().indexOf(trimmed.toLowerCase());
  if (idx === -1) {
    return <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{text}</pre>;
  }

  const before = text.slice(0, idx);
  const match = text.slice(idx, idx + trimmed.length);
  const after = text.slice(idx + trimmed.length);

  return (
    <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
      {before}
      <mark className="evidence-highlight">{match}</mark>
      {after}
    </pre>
  );
}

export function CvViewer({
  candidateId,
  filename,
  anonymizedText,
  previewText,
  sendsExternalData,
  highlightedQuote,
}: {
  candidateId: string;
  filename: string;
  anonymizedText: string;
  previewText: string | null;
  sendsExternalData: boolean | null;
  highlightedQuote: string | null;
}) {
  const t = useTranslations();
  const isPdf = filename.toLowerCase().endsWith(".pdf");
  const [viewMode, setViewMode] = useState<"original" | "anonymized">("original");
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [pdfFailed, setPdfFailed] = useState(false);

  const fileUrl = useMemo(() => candidatesApi.fileUrl(candidateId), [candidateId]);

  const textRenderer = useCallback(
    (textItem: { str: string }) => {
      if (!highlightedQuote) return textItem.str;
      const needle = highlightedQuote.trim().toLowerCase();
      if (!needle) return textItem.str;
      const hay = textItem.str.toLowerCase();
      if (needle.includes(hay) && hay.length >= 8) {
        return `<mark class="evidence-highlight">${textItem.str}</mark>`;
      }
      const idx = hay.indexOf(needle);
      if (idx !== -1) {
        const before = textItem.str.slice(0, idx);
        const match = textItem.str.slice(idx, idx + needle.length);
        const after = textItem.str.slice(idx + needle.length);
        return `${before}<mark class="evidence-highlight">${match}</mark>${after}`;
      }
      return textItem.str;
    },
    [highlightedQuote]
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
            <HighlightedText text={displayedText} quote={highlightedQuote} />
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
