// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { CriteriaEditorTab } from "@/components/jobs/CriteriaEditorTab";
import { JobRunBar } from "@/components/jobs/JobRunBar";
import { RankingTab } from "@/components/jobs/RankingTab";
import { UploadAndRunTab } from "@/components/jobs/UploadAndRunTab";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { jobsApi } from "@/lib/api/client";
import type { EstimateResponse } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type JobTab = "criteria" | "upload" | "ranking";

function isJobTab(value: string | null): value is JobTab {
  return value === "criteria" || value === "upload" || value === "ranking";
}

/** Open the step the recruiter most likely needs next. */
function defaultTab(estimate: EstimateResponse): JobTab {
  if (estimate.criteria_count === 0) return "criteria";
  if (estimate.candidate_count === 0) return "upload";
  return "ranking";
}

export default function JobDetailPage() {
  const t = useTranslations();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const [chosenTab, setChosenTab] = useState<JobTab | null>(
    isJobTab(requestedTab) ? requestedTab : null
  );

  const jobQuery = useQuery({
    queryKey: ["job", params.id],
    queryFn: () => jobsApi.get(params.id),
  });

  const estimateQuery = useQuery({
    queryKey: ["job", params.id, "estimate"],
    queryFn: () => jobsApi.getEstimate(params.id),
    // Poll while a run is active so step counters stay current.
    refetchInterval: (query) => (query.state.data?.active_run_id ? 3000 : false),
  });

  const estimate = estimateQuery.data;
  // Pick the default step once, on first load: recomputing it on every
  // estimate refresh would yank the user away (e.g. right after saving criteria).
  useEffect(() => {
    if (chosenTab === null && estimate) setChosenTab(defaultTab(estimate));
  }, [chosenTab, estimate]);
  const activeTab: JobTab | null = chosenTab ?? (estimate ? defaultTab(estimate) : null);

  const navigate = useCallback(
    (tab: JobTab) => {
      setChosenTab(tab);
      router.replace(`/jobs/${params.id}?tab=${tab}`, { scroll: false });
    },
    [params.id, router]
  );

  const job = jobQuery.data;

  return (
    <AppShell>
      <div className="space-y-5">
        <div className="flex flex-col gap-2">
          <Link
            href="/"
            className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>{t("job.backToDashboard")}</span>
          </Link>

          {job && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-semibold tracking-tight">{job.title}</h1>
                <Badge variant="default">{t(`jobStatus.${job.status}`)}</Badge>
              </div>
              <span className="text-xs text-[var(--muted-foreground)]">
                {t("job.thresholds", {
                  interview: job.interview_threshold,
                  review: job.review_threshold,
                })}
              </span>
            </div>
          )}
        </div>

        {jobQuery.isLoading || estimateQuery.isLoading || !activeTab ? (
          <div className="space-y-4">
            <Skeleton className="h-16 w-full rounded-xl" />
            <Skeleton className="h-64 w-full rounded-xl" />
          </div>
        ) : jobQuery.isError || !job || !estimate ? (
          <Alert variant="danger">{t("common.errorGeneric")}</Alert>
        ) : (
          <>
            <JobRunBar jobId={job.id} estimate={estimate} onNavigate={navigate} />

            <Tabs value={activeTab} onValueChange={(v) => navigate(v as JobTab)}>
              <TabsList className="h-auto flex-wrap">
                <StepTrigger
                  value="criteria"
                  index={1}
                  label={t("job.tabs.criteria")}
                  done={estimate.criteria_count > 0}
                  detail={
                    estimate.criteria_count > 0
                      ? t("job.steps.criteriaDone", {
                          count: estimate.criteria_count,
                          version: estimate.criteria_version ?? 1,
                        })
                      : t("job.steps.criteriaTodo")
                  }
                />
                <StepTrigger
                  value="upload"
                  index={2}
                  label={t("job.tabs.upload")}
                  done={estimate.candidate_count > 0}
                  detail={
                    estimate.candidate_count > 0
                      ? t("job.steps.uploadDone", { count: estimate.candidate_count })
                      : t("job.steps.uploadTodo")
                  }
                />
                <StepTrigger
                  value="ranking"
                  index={3}
                  label={t("job.tabs.ranking")}
                  done={
                    estimate.candidate_count > 0 &&
                    estimate.evaluated_count === estimate.candidate_count
                  }
                  warn={estimate.failed_count > 0}
                  detail={
                    estimate.active_run_id
                      ? t("job.steps.rankingRunning")
                      : estimate.evaluated_count > 0
                        ? [
                            t("job.steps.rankingDone", {
                              evaluated: estimate.evaluated_count,
                              total: estimate.candidate_count,
                            }),
                            estimate.failed_count > 0
                              ? t("job.steps.rankingFailed", { count: estimate.failed_count })
                              : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")
                        : t("job.steps.rankingTodo")
                  }
                />
              </TabsList>

              <TabsContent value="criteria">
                <CriteriaEditorTab
                  job={job}
                  evaluatedCount={estimate.evaluated_count}
                  onNext={estimate.candidate_count === 0 ? () => navigate("upload") : undefined}
                />
              </TabsContent>
              <TabsContent value="upload">
                <UploadAndRunTab job={job} />
              </TabsContent>
              <TabsContent value="ranking">
                <RankingTab jobId={job.id} runActive={Boolean(estimate.active_run_id)} />
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </AppShell>
  );
}

function StepTrigger({
  value,
  index,
  label,
  detail,
  done,
  warn = false,
}: {
  value: JobTab;
  index: number;
  label: string;
  detail: string;
  done: boolean;
  warn?: boolean;
}) {
  return (
    <TabsTrigger value={value} className="h-auto items-start gap-2.5 px-3 py-2 text-left">
      <span
        className={cn(
          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold",
          done
            ? "border-emerald-600 bg-emerald-600 text-white"
            : "border-[var(--border)] text-[var(--muted-foreground)]"
        )}
      >
        {done ? <Check className="h-3 w-3" /> : index}
      </span>
      <span className="flex flex-col">
        <span className="text-sm font-medium">{label}</span>
        <span
          className={cn(
            "text-[11px] font-normal",
            warn ? "text-amber-700 dark:text-amber-300" : "text-[var(--muted-foreground)]"
          )}
        >
          {detail}
        </span>
      </span>
    </TabsTrigger>
  );
}
