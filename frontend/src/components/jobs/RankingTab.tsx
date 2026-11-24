// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { AlertTriangle, ArrowUpDown, ChevronRight, Download, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { jobsApi } from "@/lib/api/client";
import type { CandidateSummary, HumanDecision, Recommendation } from "@/lib/api/types";

type AnalysisStatus = "done" | "queued" | "running" | "failed" | "not_analyzed";

const columnHelper = createColumnHelper<CandidateSummary>();

function recVariant(rec: Recommendation | null): "success" | "warning" | "danger" | "default" {
  switch (rec) {
    case "interview":
      return "success";
    case "review":
      return "warning";
    case "not_retained":
      return "danger";
    default:
      return "default";
  }
}

function decVariant(dec: HumanDecision): "success" | "danger" | "default" {
  switch (dec) {
    case "shortlisted":
      return "success";
    case "rejected":
      return "danger";
    default:
      return "default";
  }
}

export function RankingTab({ jobId, runActive = false }: { jobId: string; runActive?: boolean }) {
  const t = useTranslations();
  const router = useRouter();

  const [recommendation, setRecommendation] = useState<Recommendation | "">("");
  const [decision, setDecision] = useState<HumanDecision | "">("");
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);

  const rankingQuery = useQuery({
    queryKey: ["job", jobId, "ranking", recommendation, decision, search],
    queryFn: () =>
      jobsApi.getRanking(jobId, {
        recommendation,
        decision,
        search: search.trim() || undefined,
        limit: 500,
        offset: 0,
      }),
    refetchInterval: runActive ? 3000 : false,
  });

  const items = useMemo(() => rankingQuery.data?.items ?? [], [rankingQuery.data?.items]);

  const summary = useMemo(() => {
    const counts = {
      total: items.length,
      interview: 0,
      review: 0,
      not_retained: 0,
      manual_review: 0,
      unscored: 0,
    };
    const models = new Set<string>();
    let anyFallback = false;

    for (const item of items) {
      if (item.recommendation === "interview") counts.interview += 1;
      else if (item.recommendation === "review") counts.review += 1;
      else if (item.recommendation === "not_retained") counts.not_retained += 1;
      else if (item.recommendation === "manual_review") counts.manual_review += 1;
      else counts.unscored += 1;

      if (item.model_used) models.add(item.model_used);
      if (item.fallback_used) anyFallback = true;
    }

    return {
      counts,
      mixedModels: models.size > 1 || anyFallback,
    };
  }, [items]);

  const columns = useMemo(
    () => [
      columnHelper.accessor("filename", {
        header: t("job.ranking.colCandidate"),
        cell: (info) => <span className="font-medium">{info.getValue()}</span>,
      }),
      columnHelper.accessor((row) => row.score ?? -1, {
        id: "score",
        header: t("job.ranking.colScore"),
        cell: (info) => {
          const row = info.row.original;
          const raw = row.score;
          return (
            <span
              className={`font-semibold tabular-nums ${row.is_stale ? "text-[var(--muted-foreground)] line-through decoration-1" : ""}`}
              title={
                row.is_stale
                  ? t("job.ranking.staleHint", { version: row.criteria_set_version ?? 1 })
                  : undefined
              }
            >
              {raw != null ? `${Math.round(raw)}/100` : "—"}
            </span>
          );
        },
      }),
      columnHelper.accessor("recommendation", {
        header: t("job.ranking.colRecommendation"),
        cell: (info) => {
          const row = info.row.original;
          const rec = info.getValue();
          const status = (row.analysis_status ?? "not_analyzed") as AnalysisStatus;
          return (
            <div className="flex flex-col items-start gap-1">
              {rec && !row.is_stale ? (
                <Badge variant={recVariant(rec)}>{t(`recommendations.${rec}`)}</Badge>
              ) : null}
              {row.is_stale && (
                <Badge
                  variant="outline"
                  title={t("job.ranking.staleHint", { version: row.criteria_set_version ?? 1 })}
                >
                  {t("job.ranking.staleBadge")}
                </Badge>
              )}
              {status !== "done" && (
                <span
                  className={`inline-flex items-center gap-1 text-xs ${
                    status === "failed"
                      ? "text-rose-700 dark:text-rose-300"
                      : "text-[var(--muted-foreground)]"
                  }`}
                >
                  {(status === "running" || status === "queued") && (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  )}
                  {status === "failed" && <AlertTriangle className="h-3 w-3" />}
                  <span>{t(`job.ranking.status.${status}`)}</span>
                </span>
              )}
              {row.analysis_error_code && status !== "done" && (
                <span className="max-w-[18rem] text-[11px] leading-snug text-[var(--muted-foreground)]">
                  {t(`job.ranking.errors.${row.analysis_error_code}`)}
                </span>
              )}
            </div>
          );
        },
      }),
      columnHelper.accessor(
        (row) => (row.mandatory_total > 0 ? row.mandatory_met / row.mandatory_total : 1),
        {
          id: "mandatory",
          header: t("job.ranking.colMandatory"),
          cell: (info) => {
            const row = info.row.original;
            return (
              <span className="tabular-nums">
                {row.score == null ? "—" : `${row.mandatory_met}/${row.mandatory_total}`}
              </span>
            );
          },
        }
      ),
      columnHelper.accessor("decision", {
        header: t("job.ranking.colDecision"),
        cell: (info) => {
          const dec = info.getValue();
          return <Badge variant={decVariant(dec)}>{t(`decisions.${dec}`)}</Badge>;
        },
      }),
      columnHelper.display({
        id: "open",
        header: "",
        cell: () => <ChevronRight className="h-4 w-4 text-[var(--muted-foreground)]" />,
      }),
    ],
    [t]
  );

  const table = useReactTable({
    data: items,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="space-y-4">
      {/* Summary Counters */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Card>
          <CardContent className="p-3">
            <div className="text-xs text-[var(--muted-foreground)]">
              {t("job.ranking.summaryTotal")}
            </div>
            <div className="text-xl font-bold">{summary.counts.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <div className="text-xs text-emerald-700 dark:text-emerald-300">
              {t("job.ranking.summaryInterview")}
            </div>
            <div className="text-xl font-bold">{summary.counts.interview}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <div className="text-xs text-amber-700 dark:text-amber-300">
              {t("job.ranking.summaryReview")}
            </div>
            <div className="text-xl font-bold">{summary.counts.review}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <div className="text-xs text-rose-700 dark:text-rose-300">
              {t("job.ranking.summaryNotRetained")}
            </div>
            <div className="text-xl font-bold">{summary.counts.not_retained}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <div className="text-xs text-[var(--muted-foreground)]">
              {t("job.ranking.summaryManual")}
            </div>
            <div className="text-xl font-bold">{summary.counts.manual_review}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <div className="text-xs text-[var(--muted-foreground)]">
              {t("job.ranking.summaryUnscored")}
            </div>
            <div className="text-xl font-bold">{summary.counts.unscored}</div>
          </CardContent>
        </Card>
      </div>

      {summary.mixedModels && (
        <Alert variant="warning" className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{t("job.ranking.mixedModelWarning")}</span>
        </Alert>
      )}

      {/* Filters & Export */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="w-56"
            placeholder={t("job.ranking.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            className="w-48"
            aria-label={t("job.ranking.filterRecommendation")}
            value={recommendation}
            onChange={(e) => setRecommendation(e.target.value as Recommendation | "")}
          >
            <option value="">
              {t("job.ranking.filterRecommendation")}: {t("job.ranking.all")}
            </option>
            <option value="interview">{t("recommendations.interview")}</option>
            <option value="review">{t("recommendations.review")}</option>
            <option value="not_retained">{t("recommendations.not_retained")}</option>
            <option value="manual_review">{t("recommendations.manual_review")}</option>
          </Select>
          <Select
            className="w-44"
            aria-label={t("job.ranking.filterDecision")}
            value={decision}
            onChange={(e) => setDecision(e.target.value as HumanDecision | "")}
          >
            <option value="">
              {t("job.ranking.filterDecision")}: {t("job.ranking.all")}
            </option>
            <option value="shortlisted">{t("decisions.shortlisted")}</option>
            <option value="pending">{t("decisions.pending")}</option>
            <option value="rejected">{t("decisions.rejected")}</option>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <a href={jobsApi.exportUrl(jobId, "xlsx")} download>
            <Button variant="outline" size="sm">
              <Download className="h-3.5 w-3.5" />
              <span>{t("job.ranking.exportXlsx")}</span>
            </Button>
          </a>
          <a href={jobsApi.exportUrl(jobId, "csv")} download>
            <Button variant="outline" size="sm">
              <Download className="h-3.5 w-3.5" />
              <span>{t("job.ranking.exportCsv")}</span>
            </Button>
          </a>
        </div>
      </div>

      {/* Table */}
      <Card>
        <div className="overflow-x-auto">
          {rankingQuery.isLoading ? (
            <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">
              {t("common.loading")}
            </div>
          ) : items.length === 0 ? (
            <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">
              {t("job.ranking.emptyRanking")}
            </div>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="border-b border-[var(--border)] bg-[var(--muted)]/50 text-xs uppercase text-[var(--muted-foreground)]">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((header) => (
                      <th key={header.id} className="px-4 py-3 font-medium">
                        {header.isPlaceholder ? null : (
                          <button
                            type="button"
                            className="inline-flex items-center gap-1 hover:text-[var(--foreground)] cursor-pointer"
                            onClick={header.column.getToggleSortingHandler()}
                          >
                            {flexRender(header.column.columnDef.header, header.getContext())}
                            {header.column.getCanSort() && <ArrowUpDown className="h-3 w-3" />}
                          </button>
                        )}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    tabIndex={0}
                    onClick={() => router.push(`/candidates/${row.original.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") router.push(`/candidates/${row.original.id}`);
                    }}
                    className="cursor-pointer hover:bg-[var(--muted)]/30 focus-visible:bg-[var(--muted)]/40 focus-visible:outline-none"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-4 py-3">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>
    </div>
  );
}
