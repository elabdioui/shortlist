// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Play, RotateCcw, Shield, ShieldAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ApiError, jobsApi, runsApi } from "@/lib/api/client";
import type { EstimateResponse, RunProgressEvent } from "@/lib/api/types";
import { formatCostUsd, formatDurationSeconds } from "@/lib/utils";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "paused_budget"]);

type JobTab = "criteria" | "upload" | "ranking";

/**
 * Single place where an analysis is started and followed, shown above every tab.
 * It survives tab switches and page reloads because the active run comes from
 * the server (estimate.active_run_id), not from component state.
 */
export function JobRunBar({
  jobId,
  estimate,
  onNavigate,
}: {
  jobId: string;
  estimate: EstimateResponse;
  onNavigate: (tab: JobTab) => void;
}) {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<RunProgressEvent | null>(null);
  const [finished, setFinished] = useState<RunProgressEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const finishedFailures = useRef<number | null>(null);

  const activeRunId = estimate.active_run_id ?? null;

  const refreshJob = () => {
    queryClient.invalidateQueries({ queryKey: ["job", jobId] });
  };

  const startRun = useMutation({
    mutationFn: () => jobsApi.startRun(jobId, { resume_failed: true }),
    onSuccess: (run) => {
      setError(null);
      setFinished(null);
      setProgress({
        run_id: run.id,
        status: run.status,
        processed_count: run.processed_count,
        total_count: run.total_count,
        cumulative_cost_usd: run.cumulative_cost_usd,
      });
      refreshJob();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.errorGeneric")),
  });

  const runId =
    activeRunId ?? (progress && !TERMINAL_STATUSES.has(progress.status) ? progress.run_id : null);

  useEffect(() => {
    if (!runId) return;
    const es = new EventSource(runsApi.eventsUrl(runId), { withCredentials: true });
    es.addEventListener("progress", ((event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as RunProgressEvent;
        setProgress(data);
        // Keep the ranking and step counters moving while the run progresses.
        queryClient.invalidateQueries({ queryKey: ["job", jobId, "ranking"] });
        if (TERMINAL_STATUSES.has(data.status)) {
          es.close();
          finishedFailures.current = null;
          setFinished(data);
          queryClient.invalidateQueries({ queryKey: ["job", jobId] });
          if (data.status === "completed") onNavigate("ranking");
        }
      } catch {
        // Ignore malformed SSE payloads.
      }
    }) as EventListener);
    es.onerror = () => es.close();
    return () => es.close();
  }, [runId, jobId, queryClient, onNavigate]);

  const running = Boolean(runId) && !(progress && TERMINAL_STATUSES.has(progress.status));

  if (estimate.criteria_count === 0) {
    return (
      <NextStep text={t("job.run.needCriteria")}>
        <Button size="sm" onClick={() => onNavigate("criteria")}>
          {t("job.run.goCriteria")}
        </Button>
      </NextStep>
    );
  }

  if (estimate.candidate_count === 0) {
    return (
      <NextStep text={t("job.run.needCvs")}>
        <Button size="sm" onClick={() => onNavigate("upload")}>
          {t("job.run.goUpload")}
        </Button>
      </NextStep>
    );
  }

  if (running) {
    const processed = progress?.processed_count ?? 0;
    const total = progress?.total_count ?? estimate.pending_count;
    const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
    return (
      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Loader2 className="h-4 w-4 animate-spin text-[var(--primary)]" />
              <span>{t("job.run.runningTitle", { processed, total })}</span>
            </div>
            <span className="text-xs text-[var(--muted-foreground)]">
              {t("job.upload.cumulativeCost", {
                cost: formatCostUsd(progress?.cumulative_cost_usd ?? 0),
              })}
            </span>
          </div>
          <Progress value={percent} />
          <p className="text-xs text-[var(--muted-foreground)]">{t("job.run.runningHint")}</p>
        </CardContent>
      </Card>
    );
  }

  const failed = estimate.failed_count ?? 0;
  const pending = estimate.pending_count ?? 0;

  return (
    <div className="space-y-2">
      {error && <Alert variant="danger">{error}</Alert>}
      {finished?.status === "paused_budget" && (
        <Alert variant="warning">{t("job.run.pausedBudget")}</Alert>
      )}
      {finished?.status === "completed" && pending === 0 && (
        <Alert variant="success" className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            {t("job.run.finishedOk", { count: estimate.evaluated_count })}
          </span>
          <Button size="sm" variant="outline" onClick={() => onNavigate("ranking")}>
            {t("job.run.viewRanking")}
          </Button>
        </Alert>
      )}
      {finished?.status === "completed" && failed > 0 && (
        <Alert variant="warning">{t("job.run.finishedWithFailures", { failed })}</Alert>
      )}

      {pending > 0 ? (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div className="space-y-1">
              <div className="text-sm font-medium">
                {failed > 0
                  ? t("job.run.retryTitle", { count: pending, failed })
                  : t("job.run.readyTitle", { count: pending })}
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--muted-foreground)]">
                <span>
                  {t("job.run.readyDetail", {
                    duration: formatDurationSeconds(estimate.estimated_duration_seconds),
                    cost: formatCostUsd(estimate.estimated_cost_usd),
                  })}
                </span>
                <span className="inline-flex items-center gap-1">
                  {estimate.sends_external_data ? (
                    <ShieldAlert className="h-3.5 w-3.5 text-amber-600" />
                  ) : (
                    <Shield className="h-3.5 w-3.5 text-emerald-600" />
                  )}
                  {estimate.sends_external_data
                    ? t("common.externalPrivacy", { provider: estimate.provider_label ?? "IA" })
                    : t("common.localPrivacy")}
                </span>
              </div>
            </div>
            <Button onClick={() => startRun.mutate()} disabled={startRun.isPending}>
              {failed > 0 ? <RotateCcw className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              <span>
                {startRun.isPending
                  ? t("job.run.starting")
                  : failed > 0
                    ? t("job.run.retry")
                    : t("job.run.start")}
              </span>
            </Button>
          </CardContent>
        </Card>
      ) : (
        !finished && (
          <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
            <span>{t("job.run.allDone", { version: estimate.criteria_version ?? 1 })}</span>
          </div>
        )
      )}
    </div>
  );
}

function NextStep({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
        <span className="text-sm">{text}</span>
        {children}
      </CardContent>
    </Card>
  );
}
