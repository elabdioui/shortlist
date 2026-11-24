// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RotateCcw, Shield, ShieldAlert, Upload } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ApiError, jobsApi, runsApi } from "@/lib/api/client";
import type {
  AnalysisRunResponse,
  CandidateUploadResponse,
  JobResponse,
  RunProgressEvent,
} from "@/lib/api/types";
import { formatCostUsd, formatDurationSeconds } from "@/lib/utils";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "paused_budget"]);

export function UploadAndRunTab({
  job,
  onRunFinished,
}: {
  job: JobResponse;
  onRunFinished?: () => void;
}) {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [dragActive, setDragActive] = useState(false);
  const [uploadResult, setUploadResult] = useState<CandidateUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [liveProgress, setLiveProgress] = useState<RunProgressEvent | null>(null);

  const estimateQuery = useQuery({
    queryKey: ["job", job.id, "estimate"],
    queryFn: () => jobsApi.getEstimate(job.id),
  });

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => jobsApi.uploadCandidates(job.id, files),
    onSuccess: (res) => {
      setUploadResult(res);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["job", job.id, "estimate"] });
      queryClient.invalidateQueries({ queryKey: ["job", job.id, "ranking"] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : t("common.errorGeneric"));
    },
  });

  const startRunMutation = useMutation({
    mutationFn: (resumeFailed: boolean) =>
      jobsApi.startRun(job.id, { resume_failed: resumeFailed }),
    onSuccess: (run: AnalysisRunResponse) => {
      setError(null);
      setActiveRunId(run.id);
      setLiveProgress({
        run_id: run.id,
        status: run.status,
        processed_count: run.processed_count,
        total_count: run.total_count,
        cumulative_cost_usd: run.cumulative_cost_usd,
      });
      queryClient.invalidateQueries({ queryKey: ["job", job.id] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : t("common.errorGeneric"));
    },
  });

  // Subscribe to SSE progress while a run is active
  useEffect(() => {
    if (!activeRunId) return;

    const es = new EventSource(runsApi.eventsUrl(activeRunId), { withCredentials: true });

    const handleProgress = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as RunProgressEvent;
        setLiveProgress(data);
        if (TERMINAL_STATUSES.has(data.status)) {
          es.close();
          queryClient.invalidateQueries({ queryKey: ["job", job.id] });
          queryClient.invalidateQueries({ queryKey: ["job", job.id, "ranking"] });
          queryClient.invalidateQueries({ queryKey: ["job", job.id, "estimate"] });
          if (data.status === "completed") {
            onRunFinished?.();
          }
        }
      } catch {
        // Ignore malformed SSE payload
      }
    };

    es.addEventListener("progress", handleProgress as EventListener);
    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
    };
  }, [activeRunId, job.id, onRunFinished, queryClient]);

  function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    uploadMutation.mutate(Array.from(fileList));
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    handleFiles(e.dataTransfer.files);
  }

  const estimate = estimateQuery.data;
  const progressPercent =
    liveProgress && liveProgress.total_count > 0
      ? Math.round((liveProgress.processed_count / liveProgress.total_count) * 100)
      : 0;

  return (
    <div className="space-y-6">
      {error && <Alert variant="danger">{error}</Alert>}

      {/* Dropzone */}
      <Card>
        <CardHeader>
          <CardTitle>{t("job.tabs.upload")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
              dragActive
                ? "border-[var(--primary)] bg-blue-50/50 dark:bg-blue-950/20"
                : "border-[var(--border)] bg-[var(--background)]"
            }`}
          >
            <Upload className="mb-3 h-8 w-8 text-[var(--muted-foreground)]" />
            <p className="text-sm font-medium">{t("job.upload.dropzoneTitle")}</p>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">
              {t("job.upload.dropzoneSubtitle")}
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.zip"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
            <Button
              variant="outline"
              className="mt-4"
              disabled={uploadMutation.isPending}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploadMutation.isPending ? t("job.upload.uploading") : t("job.upload.browseFiles")}
            </Button>
          </div>

          {uploadResult && (
            <Alert variant="success">
              <div>
                {t("job.upload.uploadSuccess", {
                  uploaded: uploadResult.uploaded.length,
                  duplicates: (uploadResult.duplicates_skipped ?? []).length,
                })}
              </div>
              {(uploadResult.errors ?? []).length > 0 && (
                <div className="mt-2 text-xs text-rose-700 dark:text-rose-300">
                  <div className="font-semibold">{t("job.upload.uploadErrors")}</div>
                  <ul className="list-disc pl-5">
                    {(uploadResult.errors ?? []).map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Pre-run Estimate & Launch */}
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>{t("job.upload.estimateTitle")}</CardTitle>
          {estimate && (
            <Badge variant={estimate.sends_external_data ? "warning" : "success"}>
              {estimate.sends_external_data ? (
                <ShieldAlert className="h-3.5 w-3.5" />
              ) : (
                <Shield className="h-3.5 w-3.5" />
              )}
              <span>
                {estimate.sends_external_data
                  ? t("common.externalPrivacy", { provider: estimate.provider_label ?? "IA" })
                  : t("common.localPrivacy")}
              </span>
            </Badge>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          {estimateQuery.isLoading ? (
            <div className="text-sm text-[var(--muted-foreground)]">{t("common.loading")}</div>
          ) : estimate ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-lg border border-[var(--border)] p-3">
                <div className="text-xs text-[var(--muted-foreground)]">
                  {t("job.upload.candidateCount")}
                </div>
                <div className="mt-1 text-xl font-bold">{estimate.candidate_count}</div>
              </div>
              <div className="rounded-lg border border-[var(--border)] p-3">
                <div className="text-xs text-[var(--muted-foreground)]">
                  {t("job.upload.duplicateCount")}
                </div>
                <div className="mt-1 text-xl font-bold">{estimate.duplicate_count}</div>
              </div>
              <div className="rounded-lg border border-[var(--border)] p-3">
                <div className="text-xs text-[var(--muted-foreground)]">
                  {t("job.upload.estimatedCost")}
                </div>
                <div className="mt-1 text-xl font-bold">
                  {formatCostUsd(estimate.estimated_cost_usd)}
                </div>
              </div>
              <div className="rounded-lg border border-[var(--border)] p-3">
                <div className="text-xs text-[var(--muted-foreground)]">
                  {t("job.upload.estimatedDuration")}
                </div>
                <div className="mt-1 text-xl font-bold">
                  {formatDurationSeconds(estimate.estimated_duration_seconds)}
                </div>
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => startRunMutation.mutate(true)}
              disabled={startRunMutation.isPending || !estimate || estimate.candidate_count === 0}
            >
              <RotateCcw className="h-4 w-4" />
              <span>{t("job.upload.resumeRun")}</span>
            </Button>
            <Button
              onClick={() => startRunMutation.mutate(false)}
              disabled={startRunMutation.isPending || !estimate || estimate.candidate_count === 0}
            >
              <Play className="h-4 w-4" />
              <span>
                {startRunMutation.isPending
                  ? t("job.upload.startingRun")
                  : t("job.upload.startRun")}
              </span>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Live SSE Progress */}
      {liveProgress && (
        <Card>
          <CardHeader>
            <CardTitle>{t("job.upload.progressTitle")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Progress value={progressPercent} />
            <div className="flex flex-wrap items-center justify-between text-sm">
              <span>
                {t("job.upload.processedOf", {
                  processed: liveProgress.processed_count,
                  total: liveProgress.total_count,
                })}{" "}
                ({progressPercent}%)
              </span>
              <span className="text-[var(--muted-foreground)]">
                {t("job.upload.cumulativeCost", {
                  cost: formatCostUsd(liveProgress.cumulative_cost_usd),
                })}
              </span>
            </div>
            {liveProgress.status === "completed" && (
              <Alert variant="success">{t("job.upload.runCompleted")}</Alert>
            )}
            {liveProgress.status === "paused_budget" && (
              <Alert variant="warning">{t("job.upload.runPausedBudget")}</Alert>
            )}
            {liveProgress.status === "failed" && (
              <Alert variant="danger">{t("job.upload.runFailed")}</Alert>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
