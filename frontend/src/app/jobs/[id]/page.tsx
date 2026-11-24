// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
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
import { jobsApi } from "@/lib/api/client";
import { cn } from "@/lib/utils";

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
        <div>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>{t("job.backToDashboard")}</span>
          </Link>

          {jobQuery.data && (
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight">{jobQuery.data.title}</h1>
              <Badge variant="info">{t(`jobStatus.${jobQuery.data.status}`)}</Badge>
            </div>
          )}
        </div>

        {jobQuery.isLoading ? (
          <div className="py-12 text-center text-sm text-[var(--muted-foreground)]">
            {t("common.loading")}
          </div>
        ) : jobQuery.isError || !jobQuery.data ? (
          <Alert variant="danger">{t("common.errorGeneric")}</Alert>
        ) : (
          <>
            <div
              role="tablist"
              className="flex flex-wrap gap-2 border-b border-[var(--border)] pb-2"
            >
              {(["criteria", "upload", "ranking"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab}
                  onClick={() => setActiveTab(tab)}
                  className={cn(
                    "rounded-lg px-4 py-2 text-sm font-medium transition-colors cursor-pointer",
                    activeTab === tab
                      ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                      : "text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                  )}
                >
                  {t(`job.tabs.${tab}`)}
                </button>
              ))}
            </div>

            {activeTab === "criteria" && <CriteriaEditorTab job={jobQuery.data} />}
            {activeTab === "upload" && (
              <UploadAndRunTab job={jobQuery.data} onRunFinished={() => setActiveTab("ranking")} />
            )}
            {activeTab === "ranking" && <RankingTab jobId={jobQuery.data.id} />}
          </>
        )}
      </div>
    </AppShell>
  );
}
