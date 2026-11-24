// SPDX-License-Identifier: AGPL-3.0-or-later

import { expect, test } from "@playwright/test";

test("shows evaluation grid version and re-analyse button when a newer grid exists", async ({
  page,
}) => {
  let runStarted = false;

  await page.route("**/api/auth/status", (route) =>
    route.fulfill({ json: { needs_setup: false } }),
  );
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: {
        user: {
          id: "u1",
          email: "admin@shortlist.test",
          role: "admin",
          locale: "fr",
          created_at: "2026-01-01T00:00:00Z",
        },
        csrf_token: "csrf-test",
      },
    }),
  );
  await page.route("**/api/jobs/job-1", (route) =>
    route.fulfill({
      json: {
        id: "job-1",
        title: "Acheteur Senior",
        description: "Desc",
        profile_id: null,
        interview_threshold: 70,
        review_threshold: 45,
        max_budget_usd: null,
        status: "completed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    }),
  );
  await page.route("**/api/jobs/job-1/criteria", (route) =>
    route.fulfill({
      json: {
        id: "cs-2",
        job_id: "job-1",
        version: 2,
        frozen_at: null,
        criteria: [
          {
            id: "c1",
            label: "Expérience achats",
            description: "5 ans",
            type: "mandatory",
            weight: 5,
          },
        ],
      },
    }),
  );
  await page.route("**/api/candidates/cand-1", (route) =>
    route.fulfill({
      json: {
        id: "cand-1",
        job_id: "job-1",
        filename: "cv_v1.txt",
        sha256: "abc",
        extraction_status: "extracted",
        anonymized_text: "5 ans en achats.",
        created_at: "2026-01-01T00:00:00Z",
        decision: null,
        evaluation: {
          id: "ev-1",
          candidate_id: "cand-1",
          criteria_set_version: 1,
          model_used: "fake",
          fallback_used: false,
          score: 100,
          recommendation: "interview",
          formula_version: "v2",
          input_tokens: 10,
          output_tokens: 10,
          cost_usd: 0,
          created_at: "2026-01-01T00:00:00Z",
          verdicts: [
            {
              id: "c1",
              verdict: "yes",
              original_verdict: "yes",
              quote: "5 ans en achats.",
              explanation: "Confirmé.",
              verified: true,
              span: { start: 0, end: 16, match_score: 100 },
            },
          ],
        },
      },
    }),
  );
  await page.route("**/api/candidates/cand-1/anonymized-preview", (route) =>
    route.fulfill({
      json: {
        candidate_id: "cand-1",
        filename: "cv_v1.txt",
        extraction_status: "extracted",
        anonymized_text: "5 ans en achats.",
        sends_external_data: false,
      },
    }),
  );
  await page.route("**/api/jobs/job-1/runs", (route) => {
    runStarted = true;
    return route.fulfill({
      status: 201,
      json: {
        id: "run-2",
        job_id: "job-1",
        criteria_set_version: 2,
        status: "pending",
        processed_count: 0,
        total_count: 1,
        cumulative_cost_usd: 0,
        error_count: 0,
        started_at: null,
        finished_at: null,
      },
    });
  });

  await page.goto("/candidates/cand-1");
  await expect(page.getByText(/Grille v1/)).toBeVisible();

  const reanalyzeBtn = page.getByRole("button", { name: "Réanalyser avec la nouvelle grille" });
  await expect(reanalyzeBtn).toBeVisible();
  await reanalyzeBtn.click();

  await expect.poll(() => runStarted).toBe(true);
});
