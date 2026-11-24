// SPDX-License-Identifier: AGPL-3.0-or-later

import { expect, test } from "@playwright/test";

test("highlights multi-line quote with redaction token and backend span", async ({ page }) => {
  // Mock auth & candidate endpoints so we can deterministically test a quote spanning two lines
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
        id: "cs-1",
        job_id: "job-1",
        version: 1,
        frozen_at: "2026-01-01T00:00:00Z",
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

  const cvText =
    "Profil candidat\n5 ans en tant qu'acheteur\nchez [ENTREPRISE_1] en logistique.\nFormation Master.";
  const quoteStart = cvText.indexOf("5 ans");
  const quoteEnd = quoteStart + "5 ans en tant qu'acheteur\nchez [ENTREPRISE_1]".length;

  await page.route("**/api/candidates/cand-1", (route) =>
    route.fulfill({
      json: {
        id: "cand-1",
        job_id: "job-1",
        filename: "cv_multiline.txt",
        sha256: "abc",
        extraction_status: "extracted",
        anonymized_text: cvText,
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
              quote: "5 ans en tant qu'acheteur chez [COMPANY_1]",
              explanation: "5 ans confirmés.",
              verified: true,
              span: { start: quoteStart, end: quoteEnd, match_score: 100 },
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
        filename: "cv_multiline.txt",
        extraction_status: "extracted",
        anonymized_text: cvText,
        sends_external_data: false,
      },
    }),
  );

  await page.goto("/candidates/cand-1");
  await expect(page.getByRole("heading", { name: "cv_multiline.txt" })).toBeVisible();

  // Anonymized view must highlight using backend-provided span (start..end)
  await page.getByRole("button", { name: /Aperçu anonymisé/ }).click();
  const anonMark = page.locator("mark.evidence-highlight");
  await expect(anonMark).toBeVisible();
  await expect(anonMark).toContainText("5 ans en tant qu'acheteur");
  await expect(anonMark).toContainText("chez [ENTREPRISE_1]");

  // Original view (with whitespace-insensitive + redaction-token-ignoring search) must also highlight
  await page.getByRole("button", { name: /CV original/ }).click();
  const origMark = page.locator("mark.evidence-highlight");
  await expect(origMark).toBeVisible();
  await expect(origMark).toContainText("5 ans en tant qu'acheteur");
});
