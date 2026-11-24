// SPDX-License-Identifier: AGPL-3.0-or-later

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { CriterionItem, CriterionVerdict, Recommendation } from "@/lib/api/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const VERDICT_VALUES: Record<CriterionVerdict, number> = {
  yes: 1,
  partial: 0.5,
  no: 0,
  not_found: 0,
  unproven: 0,
};

/**
 * Deterministic score & recommendation calculation matching backend core/scoring.
 * Formula: 100 * sum(w_i * v_i) / sum(w_i)
 */
export function computeScorePreview(
  criteria: CriterionItem[],
  verdictById: Record<string, CriterionVerdict>,
  interviewThreshold = 70,
  reviewThreshold = 45
): { score: number; recommendation: Recommendation } {
  if (criteria.length === 0) {
    return { score: 0, recommendation: "review" };
  }

  let weightedSum = 0;
  let totalWeight = 0;

  let anyMandatoryNo = false;
  let anyMandatoryIncomplete = false;
  let allMandatoryYes = true;

  for (const criterion of criteria) {
    const verdict = verdictById[criterion.id] ?? "not_found";
    const value = VERDICT_VALUES[verdict] ?? 0;
    weightedSum += criterion.weight * value;
    totalWeight += criterion.weight;

    if (criterion.type === "mandatory") {
      if (verdict !== "yes") {
        allMandatoryYes = false;
      }
      if (verdict === "no") {
        anyMandatoryNo = true;
      } else if (verdict === "partial" || verdict === "not_found" || verdict === "unproven") {
        anyMandatoryIncomplete = true;
      }
    }
  }

  const score = totalWeight > 0 ? Math.round((100 * weightedSum) / totalWeight) : 0;

  if (anyMandatoryNo || score < reviewThreshold) {
    return { score, recommendation: "not_retained" };
  }
  if (score >= interviewThreshold && allMandatoryYes) {
    return { score, recommendation: "interview" };
  }
  if (anyMandatoryIncomplete || (score >= reviewThreshold && score < interviewThreshold)) {
    return { score, recommendation: "review" };
  }
  return { score, recommendation: "review" };
}

export type RecommendationReason =
  | { code: "mandatoryNo"; label: string }
  | { code: "mandatoryIncomplete"; label: string }
  | { code: "belowReview"; score: number; threshold: number }
  | { code: "belowInterview"; score: number; threshold: number }
  | { code: "allGood"; threshold: number };

/** List the rules of computeScorePreview that produced the recommendation, most decisive first. */
export function explainRecommendation(
  criteria: CriterionItem[],
  verdictById: Record<string, CriterionVerdict>,
  score: number,
  interviewThreshold = 70,
  reviewThreshold = 45
): RecommendationReason[] {
  const reasons: RecommendationReason[] = [];
  const mandatory = criteria.filter((c) => c.type === "mandatory");
  for (const c of mandatory) {
    if ((verdictById[c.id] ?? "not_found") === "no") {
      reasons.push({ code: "mandatoryNo", label: c.label });
    }
  }
  if (score < reviewThreshold) {
    reasons.push({ code: "belowReview", score, threshold: reviewThreshold });
  }
  for (const c of mandatory) {
    const v = verdictById[c.id] ?? "not_found";
    if (v === "partial" || v === "not_found" || v === "unproven") {
      reasons.push({ code: "mandatoryIncomplete", label: c.label });
    }
  }
  if (score >= reviewThreshold && score < interviewThreshold) {
    reasons.push({ code: "belowInterview", score, threshold: interviewThreshold });
  }
  if (reasons.length === 0) {
    reasons.push({ code: "allGood", threshold: interviewThreshold });
  }
  return reasons;
}

export function formatCostUsd(cost: number | null | undefined): string {
  if (cost == null) return "—";
  if (cost === 0) return "$0.00";
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

export function formatDurationSeconds(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}
