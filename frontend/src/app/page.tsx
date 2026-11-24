// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Briefcase, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { ApiError, jobsApi } from "@/lib/api/client";
import type { JobResponse, JobStatus } from "@/lib/api/types";

function statusVariant(status: JobStatus): "default" | "info" | "warning" | "success" | "danger" {
  switch (status) {
    case "completed":
      return "success";
    case "running":
      return "warning";
    case "ready":
      return "info";
    default:
      return "default";
  }
}

export default function DashboardPage() {
  const t = useTranslations();
  const router = useRouter();
  const queryClient = useQueryClient();

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: jobsApi.list,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: jobsApi.create,
    onSuccess: (created: JobResponse) => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setShowCreate(false);
      setTitle("");
      setDescription("");
      router.push(`/jobs/${created.id}`);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : t("common.errorGeneric"));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: jobsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createMutation.mutate({
      title,
      description,
      interview_threshold: 70,
      review_threshold: 45,
    });
  }

  const jobs = jobsQuery.data ?? [];
  const runningCount = jobs.filter((j) => j.status === "running").length;
  const completedCount = jobs.filter((j) => j.status === "completed").length;

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{t("dashboard.title")}</h1>
            <p className="text-sm text-[var(--muted-foreground)]">{t("dashboard.subtitle")}</p>
          </div>
          <Button onClick={() => setShowCreate((prev) => !prev)}>
            <Plus className="h-4 w-4" />
            <span>{t("dashboard.newJob")}</span>
          </Button>
        </div>

        {/* Summary KPIs */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>{t("dashboard.totalJobs")}</CardDescription>
              <CardTitle className="text-2xl">{jobs.length}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>{t("dashboard.runningJobs")}</CardDescription>
              <CardTitle className="text-2xl">{runningCount}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>{t("dashboard.completedJobs")}</CardDescription>
              <CardTitle className="text-2xl">{completedCount}</CardTitle>
            </CardHeader>
          </Card>
        </div>

        {/* Quick Create Form */}
        {showCreate && (
          <Card className="border-blue-300 dark:border-blue-800">
            <CardHeader>
              <CardTitle>{t("dashboard.createJobTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreate} className="space-y-4">
                {error && <Alert variant="danger">{error}</Alert>}
                <div className="space-y-1.5">
                  <Label htmlFor="job-title">{t("dashboard.jobTitleLabel")}</Label>
                  <Input
                    id="job-title"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder={t("dashboard.jobTitlePlaceholder")}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="job-description">{t("dashboard.jobDescriptionLabel")}</Label>
                  <Textarea
                    id="job-description"
                    required
                    rows={6}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder={t("dashboard.jobDescriptionPlaceholder")}
                  />
                </div>
                <div className="flex items-center justify-end gap-2">
                  <Button variant="outline" onClick={() => setShowCreate(false)}>
                    {t("common.cancel")}
                  </Button>
                  <Button type="submit" disabled={createMutation.isPending}>
                    {createMutation.isPending ? t("common.saving") : t("dashboard.createJobButton")}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Jobs List */}
        {jobsQuery.isLoading ? (
          <div className="py-12 text-center text-sm text-[var(--muted-foreground)]">
            {t("common.loading")}
          </div>
        ) : jobsQuery.isError ? (
          <Alert variant="danger">{t("common.errorGeneric")}</Alert>
        ) : jobs.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12 text-center">
              <Briefcase className="mb-3 h-10 w-10 text-[var(--muted-foreground)]" />
              <h2 className="text-base font-semibold">{t("dashboard.emptyTitle")}</h2>
              <p className="mt-1 max-w-md text-sm text-[var(--muted-foreground)]">
                {t("dashboard.emptyDescription")}
              </p>
              <Button className="mt-4" onClick={() => setShowCreate(true)}>
                <Plus className="h-4 w-4" />
                <span>{t("dashboard.newJob")}</span>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {jobs.map((job) => (
              <Card key={job.id} className="flex flex-col justify-between">
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="line-clamp-1">{job.title}</CardTitle>
                    <Badge variant={statusVariant(job.status)}>
                      {t(`jobStatus.${job.status}`)}
                    </Badge>
                  </div>
                  <CardDescription className="line-clamp-2">{job.description}</CardDescription>
                </CardHeader>
                <CardContent className="flex items-center justify-between gap-2 pt-2">
                  <div className="text-xs text-[var(--muted-foreground)]">
                    {t("dashboard.thresholds", {
                      interview: job.interview_threshold,
                      review: job.review_threshold,
                    })}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("common.delete")}
                      onClick={() => {
                        if (window.confirm(t("dashboard.deleteJobConfirm"))) {
                          deleteMutation.mutate(job.id);
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-rose-500" />
                    </Button>
                    <Link href={`/jobs/${job.id}`}>
                      <Button size="sm">
                        <span>{t("dashboard.openJob")}</span>
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    </Link>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
