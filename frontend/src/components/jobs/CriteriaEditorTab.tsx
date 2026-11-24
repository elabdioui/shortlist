// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ChevronDown, Lock, Plus, Sparkles, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { ApiError, jobsApi, providersApi } from "@/lib/api/client";
import type { CriterionItem, JobResponse } from "@/lib/api/types";

export function CriteriaEditorTab({
  job,
  evaluatedCount = 0,
  onNext,
}: {
  job: JobResponse;
  evaluatedCount?: number;
  onNext?: () => void;
}) {
  const t = useTranslations();
  const queryClient = useQueryClient();

  const criteriaQuery = useQuery({
    queryKey: ["job", job.id, "criteria"],
    queryFn: () => jobsApi.getCriteria(job.id),
  });

  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: providersApi.listProfiles,
  });

  const [profileId, setProfileId] = useState(job.profile_id ?? "");
  const [maxBudget, setMaxBudget] = useState(
    job.max_budget_usd != null ? String(job.max_budget_usd) : ""
  );
  const [interviewThreshold, setInterviewThreshold] = useState(String(job.interview_threshold));
  const [reviewThreshold, setReviewThreshold] = useState(String(job.review_threshold));

  const [criteria, setCriteria] = useState<CriterionItem[]>([]);
  const [rejectedDiscriminatory, setRejectedDiscriminatory] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<{ type: "success" | "danger"; text: string } | null>(
    null
  );
  const [justSaved, setJustSaved] = useState(false);

  useEffect(() => {
    if (criteriaQuery.data?.criteria) {
      setCriteria(criteriaQuery.data.criteria);
    }
  }, [criteriaQuery.data]);

  const updateJobMutation = useMutation({
    mutationFn: () =>
      jobsApi.update(job.id, {
        profile_id: profileId || null,
        max_budget_usd: maxBudget ? Number(maxBudget) : null,
        interview_threshold: Number(interviewThreshold),
        review_threshold: Number(reviewThreshold),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["job", job.id] });
      queryClient.invalidateQueries({ queryKey: ["job", job.id, "estimate"] });
      setFeedback({ type: "success", text: t("job.criteria.settingsSaved") });
    },
    onError: (err) => {
      setFeedback({
        type: "danger",
        text: err instanceof ApiError ? err.detail : t("common.errorGeneric"),
      });
    },
  });

  const generateMutation = useMutation({
    mutationFn: () => jobsApi.generateCriteria(job.id),
    onSuccess: (res) => {
      setCriteria(res.criteria);
      setRejectedDiscriminatory(res.rejected_discriminatory ?? []);
      setFeedback(null);
      setJustSaved(false);
    },
    onError: (err) => {
      setFeedback({
        type: "danger",
        text: err instanceof ApiError ? err.detail : t("common.errorGeneric"),
      });
    },
  });

  const saveCriteriaMutation = useMutation({
    mutationFn: () => jobsApi.saveCriteria(job.id, { criteria }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["job", job.id, "criteria"] });
      queryClient.invalidateQueries({ queryKey: ["job", job.id] });
      setFeedback({ type: "success", text: t("job.criteria.savedSuccess") });
      setJustSaved(true);
    },
    onError: (err) => {
      setFeedback({
        type: "danger",
        text: err instanceof ApiError ? err.detail : t("common.errorGeneric"),
      });
    },
  });

  function addEmptyCriterion() {
    const nextIndex = criteria.length + 1;
    setCriteria((prev) => [
      ...prev,
      {
        id: `c${Date.now()}_${nextIndex}`,
        label: "",
        description: "",
        type: "mandatory",
        weight: 3,
      },
    ]);
  }

  function updateCriterion(index: number, patch: Partial<CriterionItem>) {
    setCriteria((prev) => prev.map((c, idx) => (idx === index ? { ...c, ...patch } : c)));
  }

  function removeCriterion(index: number) {
    setCriteria((prev) => prev.filter((_, idx) => idx !== index));
  }

  const version = criteriaQuery.data?.version ?? 1;
  const isFrozen = Boolean(criteriaQuery.data?.frozen_at);
  const savedCriteria = criteriaQuery.data?.criteria;
  const isDirty = useMemo(
    () => JSON.stringify(criteria) !== JSON.stringify(savedCriteria ?? []),
    [criteria, savedCriteria]
  );

  function handleGenerate() {
    if (criteria.length > 0 && !window.confirm(t("job.criteria.regenerateConfirm"))) return;
    generateMutation.mutate();
  }

  const settingsCard = (
    <details className="group rounded-xl border border-[var(--border)] bg-[var(--card)]">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
        <div>
          <div className="text-sm font-semibold">{t("job.criteria.settingsTitle")}</div>
          <div className="text-xs text-[var(--muted-foreground)]">
            {t("job.criteria.settingsHint")}
          </div>
        </div>
        <ChevronDown className="h-4 w-4 text-[var(--muted-foreground)] transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-[var(--border)] px-5 py-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="job-profile">{t("job.criteria.profile")}</Label>
            <Select
              id="job-profile"
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
            >
              <option value="">{t("job.criteria.noProfile")}</option>
              {(profilesQuery.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.strategy})
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="job-budget">{t("job.criteria.maxBudget")}</Label>
            <Input
              id="job-budget"
              type="number"
              min="0"
              step="0.01"
              value={maxBudget}
              onChange={(e) => setMaxBudget(e.target.value)}
              placeholder="5.00"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="job-interview-threshold">{t("job.criteria.interviewThreshold")}</Label>
            <Input
              id="job-interview-threshold"
              type="number"
              min="0"
              max="100"
              value={interviewThreshold}
              onChange={(e) => setInterviewThreshold(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="job-review-threshold">{t("job.criteria.reviewThreshold")}</Label>
            <Input
              id="job-review-threshold"
              type="number"
              min="0"
              max="100"
              value={reviewThreshold}
              onChange={(e) => setReviewThreshold(e.target.value)}
            />
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <Button
            variant="outline"
            onClick={() => updateJobMutation.mutate()}
            disabled={updateJobMutation.isPending}
          >
            {updateJobMutation.isPending ? t("common.saving") : t("job.criteria.saveSettings")}
          </Button>
        </div>
        <p className="mt-3 text-xs text-[var(--muted-foreground)]">
          {t("job.criteria.thresholdsHelp")}
        </p>
      </div>
    </details>
  );

  return (
    <div className="space-y-6">
      {feedback && <Alert variant={feedback.type}>{feedback.text}</Alert>}

      {/* Criteria Grid */}
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <CardTitle>{t("job.tabs.criteria")}</CardTitle>
            <Badge variant={isFrozen ? "warning" : "info"}>
              {isFrozen && <Lock className="h-3 w-3" />}
              {isFrozen
                ? t("job.criteria.frozenBadge", { version })
                : t("job.criteria.draftBadge", { version })}
            </Badge>
            {isDirty && <Badge variant="warning">{t("job.criteria.unsaved")}</Badge>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              onClick={handleGenerate}
              disabled={generateMutation.isPending}
            >
              <Sparkles className="h-4 w-4" />
              <span>
                {generateMutation.isPending
                  ? t("job.criteria.generating")
                  : t("job.criteria.generateButton")}
              </span>
            </Button>
            <Button variant="outline" onClick={addEmptyCriterion}>
              <Plus className="h-4 w-4" />
              <span>{t("job.criteria.addCriterion")}</span>
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {rejectedDiscriminatory.length > 0 && (
            <Alert variant="warning">
              <div className="font-medium">{t("job.criteria.discriminatoryWarning")}</div>
              <ul className="mt-1 list-disc pl-5 text-xs">
                {rejectedDiscriminatory.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </Alert>
          )}

          {criteriaQuery.isLoading ? (
            <div className="py-8 text-center text-sm text-[var(--muted-foreground)]">
              {t("common.loading")}
            </div>
          ) : criteria.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--muted-foreground)]">
              {t("job.criteria.emptyCriteria")}
            </div>
          ) : (
            <div className="space-y-3">
              {criteria.map((criterion, index) => (
                <div
                  key={criterion.id}
                  className="grid grid-cols-1 gap-3 rounded-lg border border-[var(--border)] bg-[var(--background)] p-3 md:grid-cols-12 md:items-start"
                >
                  <div className="space-y-1 md:col-span-3">
                    <Label>{t("job.criteria.label")}</Label>
                    <Input
                      value={criterion.label}
                      onChange={(e) => updateCriterion(index, { label: e.target.value })}
                      placeholder="ex. 3 ans en achats"
                    />
                  </div>

                  <div className="space-y-1 md:col-span-4">
                    <Label>{t("job.criteria.description")}</Label>
                    <Textarea
                      rows={2}
                      className="min-h-[38px]"
                      value={criterion.description}
                      onChange={(e) => updateCriterion(index, { description: e.target.value })}
                    />
                  </div>

                  <div className="space-y-1 md:col-span-2">
                    <Label>{t("job.criteria.type")}</Label>
                    <Select
                      value={criterion.type}
                      onChange={(e) =>
                        updateCriterion(index, {
                          type: e.target.value === "bonus" ? "bonus" : "mandatory",
                        })
                      }
                    >
                      <option value="mandatory">{t("job.criteria.mandatory")}</option>
                      <option value="bonus">{t("job.criteria.bonus")}</option>
                    </Select>
                  </div>

                  <div className="space-y-1 md:col-span-2">
                    <Label>{t("job.criteria.weight")}</Label>
                    <Select
                      value={String(criterion.weight)}
                      onChange={(e) => updateCriterion(index, { weight: Number(e.target.value) })}
                    >
                      {[1, 2, 3, 4, 5].map((w) => (
                        <option key={w} value={w}>
                          {w}
                        </option>
                      ))}
                    </Select>
                  </div>

                  <div className="flex items-end justify-end pt-6 md:col-span-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("common.delete")}
                      onClick={() => removeCriterion(index)}
                    >
                      <Trash2 className="h-4 w-4 text-rose-500" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {isDirty && isFrozen && evaluatedCount > 0 && (
            <Alert variant="warning" className="text-xs">
              {t("job.criteria.newVersionNotice", { next: version + 1 })}
            </Alert>
          )}

          {criteria.length > 0 && (
            <div className="sticky bottom-3 z-10 flex flex-wrap items-center justify-end gap-2 rounded-lg border border-[var(--border)] bg-[var(--card)]/95 p-2 shadow-sm backdrop-blur">
              {isDirty && savedCriteria && savedCriteria.length > 0 && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    setCriteria(savedCriteria);
                    setRejectedDiscriminatory([]);
                  }}
                >
                  {t("job.criteria.discard")}
                </Button>
              )}
              {!isDirty && justSaved && onNext ? (
                <Button onClick={onNext}>
                  <span>{t("job.criteria.nextStep")}</span>
                  <ArrowRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button
                  onClick={() => saveCriteriaMutation.mutate()}
                  disabled={saveCriteriaMutation.isPending || !isDirty}
                >
                  {saveCriteriaMutation.isPending
                    ? t("common.saving")
                    : t("job.criteria.saveCriteria")}
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {settingsCard}
    </div>
  );
}
