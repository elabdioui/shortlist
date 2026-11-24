// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ListChecks, Trophy, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { CriteriaEditorTab } from "@/components/jobs/CriteriaEditorTab";
import { RankingTab } from "@/components/jobs/RankingTab";
import { UploadAndRunTab } from "@/components/jobs/UploadAndRunTab";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { jobsApi } from "@/lib/api/client";

type JobTab = "criteria" | "upload" | "ranking";

export default function JobDetailPage() {
  const t = useTranslations();
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const initialTab = (searchParams.get("tab") as JobTab | null) ?? "criteria";
  const [activeTab, setActiveTab] = useState<JobTab>(
    initialTab === "upload" || initialTab === "ranking" ? initialTab : "criteria"
  );

  const jobQuery = useQuery({
    queryKey: ["job", params.id],
    queryFn: () => jobsApi.get(params.id),
  });

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex flex-col gap-2">
          <Link
            href="/"
            className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>{t("job.backToDashboard")}</span>
          </Link>

          {jobQuery.data && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-semibold tracking-tight">{jobQuery.data.title}</h1>
                <Badge variant="default">{t(`jobStatus.${jobQuery.data.status}`)}</Badge>
              </div>
              <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                <Badge variant="outline" className="font-mono">
                  {jobQuery.data.interview_threshold}/{jobQuery.data.review_threshold}
                </Badge>
              </div>
            </div>
          )}
        </div>

        {jobQuery.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-10 w-80" />
            <Skeleton className="h-64 w-full rounded-xl" />
          </div>
        ) : jobQuery.isError || !jobQuery.data ? (
          <Alert variant="danger">{t("common.errorGeneric")}</Alert>
        ) : (
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as JobTab)}>
            <TabsList>
              <TabsTrigger value="criteria">
                <ListChecks className="h-4 w-4" />
                <span>{t("job.tabs.criteria")}</span>
              </TabsTrigger>
              <TabsTrigger value="upload">
                <UploadCloud className="h-4 w-4" />
                <span>{t("job.tabs.upload")}</span>
              </TabsTrigger>
              <TabsTrigger value="ranking">
                <Trophy className="h-4 w-4" />
                <span>{t("job.tabs.ranking")}</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="criteria">
              <CriteriaEditorTab job={jobQuery.data} />
            </TabsContent>
            <TabsContent value="upload">
              <UploadAndRunTab job={jobQuery.data} onRunFinished={() => setActiveTab("ranking")} />
            </TabsContent>
            <TabsContent value="ranking">
              <RankingTab jobId={jobQuery.data.id} />
            </TabsContent>
          </Tabs>
        )}
      </div>
    </AppShell>
  );
}
