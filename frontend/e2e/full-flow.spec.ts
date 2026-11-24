// SPDX-License-Identifier: AGPL-3.0-or-later

import { expect, test } from "@playwright/test";

const SAMPLE_CV = `Jean Dupont
Email: jean.dupont@example.com
Téléphone: +33 6 12 34 56 78

Expérience professionnelle:
- Acheteur Supply Chain Senior chez LogiCorp (2020 - 2026) : 5 ans d'expérience en achats industriels, négociation fournisseurs et gestion des stocks.
- Formation : Master en Logistique et Supply Chain.
- Langues : Français (natif), Anglais (courant).
`;

test("full recruitment screening flow with SHORTLIST_FAKE_LLM=1", async ({ page }) => {
  // 1. First-run redirect to /setup
  await page.goto("/");
  await page.waitForURL("**/setup");
  await expect(page.getByText("Configuration initiale de Shortlist")).toBeVisible();

  await page.getByLabel("Adresse e-mail").fill("admin@shortlist.test");
  await page.getByLabel("Mot de passe").fill("AdminPass123!");
  await page.getByRole("button", { name: "Créer le compte administrateur" }).click();

  // 2. Dashboard
  await page.waitForURL("**/");
  await expect(page.getByRole("heading", { name: "Tableau de bord" })).toBeVisible();

  // Test language toggle FR <-> EN
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.getByRole("button", { name: "FR", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Tableau de bord" })).toBeVisible();

  // 3. Create a job
  await page.getByRole("button", { name: "Nouvelle offre" }).first().click();
  await page.getByLabel("Intitulé du poste").fill("Acheteur Supply Chain Senior");
  await page
    .getByLabel("Fiche de poste")
    .fill(
      "Nous recherchons un Acheteur Supply Chain avec 5 ans d'expérience et maîtrise de l'anglais."
    );
  await page.getByRole("button", { name: "Créer l'offre" }).click();

  await page.waitForURL("**/jobs/**");
  await expect(page.getByRole("heading", { name: "Acheteur Supply Chain Senior" })).toBeVisible();

  // 4. Generate & save criteria
  await page.getByRole("button", { name: "Générer les critères avec l'IA" }).click();
  await expect(
    page.getByRole("button", { name: "Valider et enregistrer la grille" })
  ).toBeVisible();
  await page.getByRole("button", { name: "Valider et enregistrer la grille" }).click();
  await expect(page.getByText("Grille enregistrée avec succès.")).toBeVisible();

  // 5. Upload CV & run screening
  await page.getByRole("tab", { name: /^2\s*CV/ }).click();
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles({
    name: "jean_dupont_cv.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(SAMPLE_CV, "utf-8"),
  });

  await expect(page.getByText(/1 CV importé/).first()).toBeVisible();
  await page.getByRole("button", { name: "Lancer l'analyse" }).click();

  // Wait for SSE completion and auto-switch to Ranking tab
  await expect(page.getByRole("tab", { name: /Classement/ })).toHaveAttribute(
    "aria-selected",
    "true",
    { timeout: 30_000 }
  );

  // 6. Verify Ranking Table & open Candidate Detail
  await expect(page.getByText("jean_dupont_cv.txt")).toBeVisible();
  // Rows are clickable: open the candidate detail from its row.
  await page.getByText("jean_dupont_cv.txt").first().click();

  await page.waitForURL("**/candidates/**");
  await expect(page.getByRole("heading", { name: "jean_dupont_cv.txt" })).toBeVisible();

  // Toggle anonymized preview
  await page.getByRole("button", { name: /Aperçu anonymisé/ }).click();
  await expect(page.getByText(/masquées localement/)).toBeVisible();

  // Save recruiter decision
  await page.getByLabel("Décision du recruteur").selectOption("shortlisted");
  await page.getByLabel("Note libre").fill("Profil solide pour entretien.");
  await page.getByRole("button", { name: "Enregistrer la décision" }).click();
  await expect(page.getByText("Décision enregistrée.")).toBeVisible();

  // 7. Settings -> Providers & AI Keys
  await page.getByRole("link", { name: "Fournisseurs IA" }).click();
  await page.waitForURL("**/settings/providers");
  await page.getByRole("button", { name: "Ajouter un fournisseur" }).click();
  await page.getByLabel("Libellé (ex. Gemini perso)").fill("Gemini E2E");
  await page.getByLabel("Clé IA secrète").fill("fake-secret-key-for-e2e-123456");
  await page.getByRole("button", { name: "Ajouter une clé IA" }).click();
  await expect(page.getByText("Gemini E2E")).toBeVisible();
  await page.getByRole("button", { name: "Tester la clé" }).first().click();
  await expect(page.getByText(/Clé valide|Échec du test/)).toBeVisible();

  // 8. Settings -> Privacy
  await page.getByRole("link", { name: "Confidentialité" }).click();
  await page.waitForURL("**/settings/privacy");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Paramètres de confidentialité enregistrés.")).toBeVisible();

  // 9. Logs & Users
  await page.getByRole("link", { name: "Journaux & coûts" }).click();
  await page.waitForURL("**/logs");
  await expect(page.getByRole("heading", { name: "Journaux et coûts" })).toBeVisible();

  await page.getByRole("link", { name: "Utilisateurs" }).click();
  await page.waitForURL("**/users");
  await expect(page.getByText("admin@shortlist.test")).toBeVisible();
});
