// SPDX-License-Identifier: AGPL-3.0-or-later

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label, Select, Textarea } from "@/components/ui/input";
import { ApiError, candidatesApi, jobsApi } from "@/lib/api/client";
import type { CriterionVerdict, HumanDecision, Recommendation } from "@/lib/api/types";
import { cn, computeScorePreview, explainRecommendation } from "@/lib/utils";

const CvViewer = dynamic(
  () => import("@/components/candidates/CvViewer").then((mod) => mod.CvViewer),
  { ssr: false }
);

function verdictBadgeVariant(
  verdict: CriterionVerdict
): "success" | "warning" | "danger" | "default" {
  switch (verdict) {
    case "yes":
      return "success";
    case "partial":
      return "warning";
    case "no":
      return "danger";
    default:
      return "default";
  }
}

function recBadgeVariant(rec: Recommendation): "success" | "warning" | "danger" | "default" {
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

export default function CandidateDetailPage() {
  const t = useTranslations();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const candidateQuery = useQuery({
    queryKey: ["candidate", params.id],
    queryFn: () => candidatesApi.get(params.id),
  });

  const jobId = candidateQuery.data?.job_id;

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => jobsApi.get(jobId!),
    enabled: Boolean(jobId),
  });

  const criteriaQuery = useQuery({
    queryKey: ["job", jobId, "criteria"],
    queryFn: () => jobsApi.getCriteria(jobId!),
    enabled: Boolean(jobId),
  });

  const rankingQuery = useQuery({
    queryKey: ["job", jobId, "ranking", "", "", ""],
    queryFn: () => jobsApi.getRanking(jobId!, { limit: 500, offset: 0 }),
    enabled: Boolean(jobId),
  });

  const previewQuery = useQuery({
    queryKey: ["candidate", params.id, "preview"],
    queryFn: () => candidatesApi.getAnonymizedPreview(params.id),
  });

  const [decision, setDecision] = useState<HumanDecision>("pending");
  const [note, setNote] = useState("");
  const [overrides, setOverrides] = useState<Record<string, CriterionVerdict>>({});
  const [highlightedQuote, setHighlightedQuote] = useState<string | null>(null);
  const [highlightedSpan, setHighlightedSpan] = useState<{ start: number; end: number } | null>(
    null
  );
  const [savedBanner, setSavedBanner] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (candidateQuery.data) {
      const dec = candidateQuery.data.decision;
      if (dec) {
        setDecision(dec.decision);
        setNote(dec.note ?? "");
        setOverrides(dec.verdict_overrides ?? {});
      }
      const firstWithQuote = candidateQuery.data.evaluation?.verdicts.find((v) => v.quote);
      if (firstWithQuote?.quote) {
        setHighlightedQuote(firstWithQuote.quote);
        setHighlightedSpan(
          firstWithQuote.span
            ? { start: firstWithQuote.span.start, end: firstWithQuote.span.end }
            : null
        );
      }
    }
  }, [candidateQuery.data]);

  const effectiveVerdicts = useMemo(() => {
    const map: Record<string, CriterionVerdict> = {};
    for (const v of candidateQuery.data?.evaluation?.verdicts ?? []) {
      map[v.id] = overrides[v.id] ?? v.verdict;
    }
    return map;
  }, [candidateQuery.data?.evaluation?.verdicts, overrides]);

  const liveScore = useMemo(() => {
    const criteria = criteriaQuery.data?.criteria ?? [];
    if (criteria.length === 0) return null;
    return computeScorePreview(
      criteria,
      effectiveVerdicts,
      jobQuery.data?.interview_threshold ?? 70,
      jobQuery.data?.review_threshold ?? 45
    );
  }, [criteriaQuery.data?.criteria, effectiveVerdicts, jobQuery.data]);

  const saveDecisionMutation = useMutation({
    mutationFn: (nextDecision?: HumanDecision) =>
      candidatesApi.saveDecision(params.id, {
        decision: nextDecision ?? decision,
        note: note.trim() || null,
        verdict_overrides: overrides,
      }),
    onSuccess: () => {
      setSavedBanner(true);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["candidate", params.id] });
      if (jobId) {
        queryClient.invalidateQueries({ queryKey: ["job", jobId, "ranking"] });
      }
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : t("common.errorGeneric"));
    },
  });

  const deleteCandidateMutation = useMutation({
    mutationFn: () => candidatesApi.delete(params.id),
    onSuccess: () => {
      if (jobId) {
        queryClient.invalidateQueries({ queryKey: ["job", jobId, "ranking"] });
        router.replace(`/jobs/${jobId}?tab=ranking`);
      } else {
        router.replace("/");
      }
    },
  });

  const reanalyzeMutation = useMutation({
    mutationFn: () => jobsApi.startRun(jobId!, { resume_failed: false }),
    onSuccess: () => {
      if (jobId) {
        queryClient.invalidateQueries({ queryKey: ["job", jobId] });
        router.push(`/jobs/${jobId}?tab=upload`);
      }
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : t("common.errorGeneric"));
    },
  });

  function handleSubmitDecision(e: FormEvent) {
    e.preventDefault();
    setSavedBanner(false);
    saveDecisionMutation.mutate(undefined);
  }

  const candidate = candidateQuery.data;
  const evaluation = candidate?.evaluation;

  const savedOverrides = candidate?.decision?.verdict_overrides ?? {};
  const overridesDirty = JSON.stringify(overrides) !== JSON.stringify(savedOverrides);

  const reasons = useMemo(() => {
    if (!liveScore || !evaluation) return [];
    if ((liveScore.recommendation as string) === "manual_review") return [];
    return explainRecommendation(
      criteriaQuery.data?.criteria ?? [],
      effectiveVerdicts,
      liveScore.score,
      jobQuery.data?.interview_threshold ?? 70,
      jobQuery.data?.review_threshold ?? 45
    );
  }, [liveScore, evaluation, criteriaQuery.data?.criteria, effectiveVerdicts, jobQuery.data]);

  const rankedIds = (rankingQuery.data?.items ?? []).map((item) => item.id);
  const position = rankedIds.indexOf(params.id);
  const prevId = position > 0 ? rankedIds[position - 1] : null;
  const nextId = position >= 0 && position < rankedIds.length - 1 ? rankedIds[position + 1] : null;

  function decide(next: HumanDecision) {
    setDecision(next);
    setSavedBanner(false);
    saveDecisionMutation.mutate(next);
  }
  const criteriaById = useMemo(() => {
    const map: Record<string, { label: string; type: string; weight: number }> = {};
    for (const c of criteriaQuery.data?.criteria ?? []) {
      map[c.id] = c;
    }
    return map;
  }, [criteriaQuery.data?.criteria]);

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <Link
              href={jobId ? `/jobs/${jobId}?tab=ranking` : "/"}
              className="inline-flex items-center gap-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              <ArrowLeft className="h-4 w-4" />
              <span>{t("candidate.backToRanking")}</span>
            </Link>
            {candidate && (
              <h1 className="mt-1 text-xl font-bold tracking-tight">{candidate.filename}</h1>
            )}
          </div>

          {candidate && (
            <div className="flex flex-wrap items-center gap-2">
              {position >= 0 && rankedIds.length > 1 && (
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!prevId}
                    onClick={() => prevId && router.push(`/candidates/${prevId}`)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    <span>{t("candidate.prevCandidate")}</span>
                  </Button>
                  <span className="px-1 text-xs tabular-nums text-[var(--muted-foreground)]">
                    {t("candidate.positionOf", { index: position + 1, total: rankedIds.length })}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!nextId}
                    onClick={() => nextId && router.push(`/candidates/${nextId}`)}
                  >
                    <span>{t("candidate.nextCandidate")}</span>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (window.confirm(t("candidate.deleteCandidateConfirm"))) {
                    deleteCandidateMutation.mutate();
                  }
                }}
              >
                <Trash2 className="h-4 w-4 text-rose-500" />
                <span>{t("candidate.deleteCandidate")}</span>
              </Button>
            </div>
          )}
        </div>

        {candidateQuery.isLoading ? (
          <div className="py-12 text-center text-sm text-[var(--muted-foreground)]">
            {t("common.loading")}
          </div>
        ) : candidateQuery.isError || !candidate ? (
          <Alert variant="danger">{t("common.errorGeneric")}</Alert>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* Left: PDF / Anonymized CV Viewer */}
            <div className="lg:col-span-6">
              <CvViewer
                candidateId={candidate.id}
                filename={candidate.filename}
                anonymizedText={candidate.anonymized_text ?? ""}
                previewText={previewQuery.data?.anonymized_text ?? null}
                sendsExternalData={previewQuery.data?.sends_external_data ?? null}
                highlightedQuote={highlightedQuote}
                highlightedSpan={highlightedSpan}
              />
            </div>

            {/* Right: Score, Verdicts, Human Decision */}
            <div className="space-y-4 lg:col-span-6">
              {error && <Alert variant="danger">{error}</Alert>}
              {savedBanner && (
                <Alert variant="success" className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>{t("candidate.decisionSaved")}</span>
                </Alert>
              )}

              {/* Newer Grid Warning */}
              {evaluation &&
                criteriaQuery.data &&
                criteriaQuery.data.version > evaluation.criteria_set_version && (
                  <Alert
                    variant="warning"
                    className="flex flex-wrap items-center justify-between gap-3"
                  >
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 shrink-0" />
                      <span>
                        {t("candidate.newerGridWarning", {
                          latest: criteriaQuery.data.version,
                          used: evaluation.criteria_set_version,
                        })}
                      </span>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => reanalyzeMutation.mutate()}
                      disabled={reanalyzeMutation.isPending || !jobId}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      <span>{t("candidate.reanalyzeNewGrid")}</span>
                    </Button>
                  </Alert>
                )}

              {/* Score Card */}
              <Card>
                <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
                  <div>
                    <div className="text-xs text-[var(--muted-foreground)]">
                      {t("candidate.scoreLive")}
                    </div>
                    <div className="text-3xl font-bold tabular-nums">
                      {liveScore
                        ? `${liveScore.score}/100`
                        : evaluation
                          ? `${Math.round(evaluation.score)}/100`
                          : "—"}
                    </div>
                    {evaluation && (
                      <div className="mt-1 text-xs text-[var(--muted-foreground)]">
                        {t("candidate.scoreOriginal", { score: Math.round(evaluation.score) })} ·{" "}
                        {t("candidate.formulaVersion", { version: evaluation.formula_version })} ·{" "}
                        {t("candidate.gridVersion", { version: evaluation.criteria_set_version })}
                      </div>
                    )}
                  </div>
                  {(liveScore?.recommendation ?? evaluation?.recommendation) && (
                    <Badge
                      variant={recBadgeVariant(
                        liveScore?.recommendation ?? evaluation!.recommendation
                      )}
                      className="px-3 py-1 text-sm"
                    >
                      {t(
                        `recommendations.${liveScore?.recommendation ?? evaluation!.recommendation}`
                      )}
                    </Badge>
                  )}
                </CardContent>

                {evaluation && (
                  <div className="border-t border-[var(--border)] px-5 py-3">
                    <div className="mb-1.5 text-xs font-medium">{t("candidate.whyTitle")}</div>
                    {evaluation.recommendation === "manual_review" ? (
                      <p className="text-xs text-[var(--muted-foreground)]">
                        {t("candidate.why.manual")}
                      </p>
                    ) : (
                      <ul className="space-y-0.5 text-xs text-[var(--muted-foreground)]">
                        {reasons.map((r, i) => (
                          <li key={i} className="flex gap-1.5">
                            <span aria-hidden>•</span>
                            <span>
                              {r.code === "mandatoryNo" || r.code === "mandatoryIncomplete"
                                ? t(`candidate.why.${r.code}`, { label: r.label })
                                : r.code === "allGood"
                                  ? t("candidate.why.allGood", { threshold: r.threshold })
                                  : t(`candidate.why.${r.code}`, {
                                      score: r.score,
                                      threshold: r.threshold,
                                    })}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 border-t border-[var(--border)] px-5 py-3">
                  <span className="mr-1 text-xs font-medium">
                    {t("candidate.humanDecisionTitle")}
                  </span>
                  {(
                    [
                      ["shortlisted", ThumbsUp, "border-emerald-600 bg-emerald-600 text-white"],
                      [
                        "pending",
                        Clock,
                        "border-[var(--foreground)] bg-[var(--foreground)] text-[var(--background)]",
                      ],
                      ["rejected", ThumbsDown, "border-rose-600 bg-rose-600 text-white"],
                    ] as const
                  ).map(([value, Icon, activeClass]) => (
                    <Button
                      key={value}
                      size="sm"
                      variant="outline"
                      aria-pressed={decision === value}
                      disabled={saveDecisionMutation.isPending}
                      onClick={() => decide(value)}
                      className={cn(decision === value && activeClass)}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      <span>{t(`decisions.${value}`)}</span>
                    </Button>
                  ))}
                  {overridesDirty && (
                    <span className="ml-auto flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300">
                      {t("candidate.unsavedOverrides")}
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={saveDecisionMutation.isPending}
                        onClick={() => saveDecisionMutation.mutate(undefined)}
                      >
                        {t("candidate.saveOverrides")}
                      </Button>
                    </span>
                  )}
                </div>
              </Card>

              {/* Criteria Verdicts */}
              <Card>
                <CardHeader>
                  <CardTitle>{t("candidate.criteriaVerdicts")}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {!evaluation ? (
                    <div className="space-y-2 text-sm text-[var(--muted-foreground)]">
                      <p>{t("candidate.noEvaluation")}</p>
                      {jobId && (
                        <Link
                          href={`/jobs/${jobId}?tab=ranking`}
                          className="text-xs underline underline-offset-2"
                        >
                          {t("candidate.noEvaluationHint")}
                        </Link>
                      )}
                    </div>
                  ) : (
                    evaluation.verdicts.map((v) => {
                      const meta = criteriaById[v.id];
                      const currentVerdict = overrides[v.id] ?? v.verdict;
                      return (
                        <div
                          key={v.id}
                          onClick={() => {
                            if (v.quote) {
                              setHighlightedQuote(v.quote);
                              setHighlightedSpan(
                                v.span ? { start: v.span.start, end: v.span.end } : null
                              );
                            }
                          }}
                          className="cursor-pointer rounded-lg border border-[var(--border)] bg-[var(--background)] p-3 transition-colors hover:border-blue-400"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <div className="font-medium text-sm">
                                {meta?.label ?? v.id}
                                {meta && (
                                  <span className="ml-2 text-xs text-[var(--muted-foreground)]">
                                    ({t(`job.criteria.${meta.type}`)} · w={meta.weight})
                                  </span>
                                )}
                              </div>
                              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                                {v.explanation}
                              </p>
                            </div>
                            <Badge variant={verdictBadgeVariant(currentVerdict)}>
                              {t(`verdicts.${currentVerdict}`)}
                            </Badge>
                          </div>

                          {v.quote && (
                            <blockquote className="mt-2 rounded bg-[var(--muted)] px-2.5 py-1.5 text-xs italic">
                              <span className="font-semibold not-italic">
                                {t("candidate.quoteLabel")}{" "}
                              </span>
                              &laquo;{v.quote}&raquo;
                            </blockquote>
                          )}

                          {!v.verified && v.verdict === "unproven" && (
                            <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-300">
                              <AlertTriangle className="h-3.5 w-3.5" />
                              <span>{t("candidate.unprovenWarning")}</span>
                            </div>
                          )}

                          <div
                            className="mt-2 flex items-center gap-2"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Label className="text-xs text-[var(--muted-foreground)]">
                              {t("candidate.overrideVerdict")}
                            </Label>
                            <Select
                              className="h-7 w-40 text-xs"
                              value={currentVerdict}
                              onChange={(e) =>
                                setOverrides((prev) => ({
                                  ...prev,
                                  [v.id]: e.target.value as CriterionVerdict,
                                }))
                              }
                            >
                              <option value="yes">{t("verdicts.yes")}</option>
                              <option value="partial">{t("verdicts.partial")}</option>
                              <option value="no">{t("verdicts.no")}</option>
                              <option value="not_found">{t("verdicts.not_found")}</option>
                              <option value="unproven">{t("verdicts.unproven")}</option>
                            </Select>
                          </div>
                        </div>
                      );
                    })
                  )}
                </CardContent>
              </Card>

              {/* Human Decision Form */}
              <Card>
                <CardHeader>
                  <CardTitle>{t("candidate.humanDecisionTitle")}</CardTitle>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleSubmitDecision} className="space-y-4">
                    <div className="space-y-1.5">
                      <Label htmlFor="human-decision">{t("candidate.humanDecisionTitle")}</Label>
                      <Select
                        id="human-decision"
                        value={decision}
                        onChange={(e) => setDecision(e.target.value as HumanDecision)}
                      >
                        <option value="shortlisted">{t("decisions.shortlisted")}</option>
                        <option value="pending">{t("decisions.pending")}</option>
                        <option value="rejected">{t("decisions.rejected")}</option>
                      </Select>
                    </div>

                    <div className="space-y-1.5">
                      <Label htmlFor="decision-note">{t("candidate.decisionNote")}</Label>
                      <Textarea
                        id="decision-note"
                        rows={3}
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder={t("candidate.decisionNotePlaceholder")}
                      />
                    </div>

                    <Button type="submit" disabled={saveDecisionMutation.isPending}>
                      {saveDecisionMutation.isPending
                        ? t("common.saving")
                        : t("candidate.saveDecision")}
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
