// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Briefcase, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, jobsApi } from "@/lib/api/client";
import type { JobResponse, JobStatus } from "@/lib/api/types";

function statusVariant(status: JobStatus): "default" | "secondary" | "warning" | "success" {
  switch (status) {
    case "completed":
      return "success";
    case "running":
      return "warning";
    case "ready":
      return "default";
    default:
      return "secondary";
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
      toast.success(created.title);
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
      toast.success(t("common.delete"));
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
            <h1 className="text-2xl font-semibold tracking-tight">{t("dashboard.title")}</h1>
            <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
              {t("dashboard.subtitle")}
            </p>
          </div>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" />
            <span>{t("dashboard.newJob")}</span>
          </Button>
        </div>

        {/* Summary KPIs — numbers only, tabular figures */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <CardHeader className="pb-1">
              <CardDescription>{t("dashboard.totalJobs")}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-medium tracking-tight tabular-nums">{jobs.length}</div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-1">
              <CardDescription>{t("dashboard.runningJobs")}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-medium tracking-tight tabular-nums">{runningCount}</div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-1">
              <CardDescription>{t("dashboard.completedJobs")}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-medium tracking-tight tabular-nums">
                {completedCount}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Create Job Dialog */}
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent className="max-w-xl">
            <DialogHeader>
              <DialogTitle>{t("dashboard.createJobTitle")}</DialogTitle>
              <DialogDescription>{t("dashboard.subtitle")}</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4 pt-2">
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
              <div className="flex items-center justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowCreate(false)}>
                  {t("common.cancel")}
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? t("common.saving") : t("dashboard.createJobButton")}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>

        {/* Jobs List */}
        {jobsQuery.isLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Skeleton className="h-44 w-full rounded-xl" />
            <Skeleton className="h-44 w-full rounded-xl" />
          </div>
        ) : jobsQuery.isError ? (
          <Alert variant="danger">{t("common.errorGeneric")}</Alert>
        ) : jobs.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-14 text-center">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--muted)]">
                <Briefcase className="h-6 w-6 text-[var(--muted-foreground)]" />
              </div>
              <h2 className="text-base font-semibold">{t("dashboard.emptyTitle")}</h2>
              <p className="mt-1 max-w-md text-sm text-[var(--muted-foreground)]">
                {t("dashboard.emptyDescription")}
              </p>
              <Button className="mt-5" onClick={() => setShowCreate(true)}>
                <Plus className="h-4 w-4" />
                <span>{t("dashboard.newJob")}</span>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {jobs.map((job) => (
              <Card
                key={job.id}
                className="group flex flex-col justify-between transition-[border-color] duration-150 hover:border-[var(--foreground)]/25"
              >
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <div className="space-y-1">
                      <CardTitle className="text-base group-hover:text-[var(--primary)] transition-colors">
                        {job.title}
                      </CardTitle>
                      <CardDescription className="line-clamp-2">{job.description}</CardDescription>
                    </div>
                    <Badge variant={statusVariant(job.status)}>
                      {t(`jobStatus.${job.status}`)}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="flex items-center justify-between gap-2 border-t border-[var(--border)] pt-3">
                  <div className="flex items-center gap-3 text-xs text-[var(--muted-foreground)]">
                    <span className="text-[11px]">
                      {t("job.thresholds", {
                        interview: job.interview_threshold,
                        review: job.review_threshold,
                      })}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("common.delete")}
                      onClick={() => deleteMutation.mutate(job.id)}
                    >
                      <Trash2 className="h-4 w-4 text-[var(--muted-foreground)] hover:text-[var(--destructive)]" />
                    </Button>
                    <Link
                      href={`/jobs/${job.id}`}
                      className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 text-xs font-medium text-[var(--primary-foreground)] transition-colors hover:bg-[var(--primary)]/90"
                    >
                      <span>{t("dashboard.openJob")}</span>
                      <ArrowRight className="h-3.5 w-3.5" />
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
