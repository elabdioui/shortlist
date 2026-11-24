# Shortlist — Fix pass after code review #1

You are the same 5-agent swarm that built Shortlist v0.1.0. An external code review found the defects below. Fix **all** of them on a branch `fix/review-01`, in the order given (P0 first).

Rules for this pass:
- **Test first.** For every defect, first write a failing test that reproduces it, commit it, then fix the code until it passes. A fix without a reproducing test is not accepted.
- Do not weaken or delete existing tests to make things pass.
- Keep `docs/SPEC.md` as the source of truth. If a fix changes behaviour described there, update the spec section and add an ADR in `docs/adr/`.
- Each defect = one conventional commit (`fix(anonymize): …`, `test(anonymize): …`).
- At the end: `ruff`, `mypy --strict`, full `pytest` with coverage ≥ 85 % on `core/` and `llm/`, frontend lint + tests, and `docker compose -f deploy/docker-compose.yml build` must all pass. Update `CHANGELOG.md` (v0.1.1) and `LIMITATIONS.md` if needed.

---

## P0-1 — Anonymisation leaks identity data and destroys language information (owner: A2, reviewer: A5)

**Observed** (`backend/shortlist/core/anonymize/anonymizer.py`):
- spaCy NER models `fr_core_news_md` / `en_core_web_md` are not installed (not in `pyproject.toml`, not in `deploy/Dockerfile.api` / `Dockerfile.worker`). The code silently falls back to `spacy.blank(...)`, so PERSON detection does not work.
- With this input:
  ```
  Curriculum Vitae
  Youssef Amrani
  Né le 12/03/1995 à Fès, marié, 2 enfants
  Tél : 0661234567 - youssef.amrani@gmail.com
  CIN : BE123456
  Acheteur chez Renault Tanger depuis 2019
  ```
  the output still contains `Youssef Amrani` and `marié, 2 enfants`. Names are only caught when they are on the first line.
- `Langues : Français courant` becomes `Langues : [NATIONALITY_1] courant` → the language criterion can no longer be evaluated.

**Required fixes**
1. Install the models: add them as dependencies (spaCy model wheels via direct URL in `pyproject.toml`, or a `RUN python -m spacy download …` step in both Dockerfiles **and** a documented `uv run python -m spacy download …` for local dev). The CI must install them too.
2. **Fail loudly**: if the NER models are missing, the worker and API must refuse to start (clear error message), unless `SHORTLIST_ALLOW_BLANK_NLP=1` is set explicitly for tests. No silent fallback.
3. Add a robust name heuristic independent of NER: in the first ~8 non-empty lines, a line of 2–4 capitalised tokens (letters, hyphens, apostrophes, accents, optional uppercase surname) that is not a known section header (`Curriculum Vitae`, `CV`, `Profil`, `Expérience`, `Formation`, `Compétences`, `Contact`, `Resume`, `Experience`, `Education`, `Skills`…) is a PERSON. Also derive the name from the email local part (`youssef.amrani@…` → `Youssef Amrani`) and redact every other occurrence of those tokens in the document.
4. Add a marital/family status recogniser (FR + EN): `marié(e)`, `célibataire`, `divorcé(e)`, `veuf/veuve`, `pacsé(e)`, `N enfant(s)`, `married`, `single`, `divorced`, `widowed`, `N child(ren)` → `[FAMILY_STATUS_n]`.
5. Nationality vs language: never redact a nationality/demonym word when it appears in a languages context (line or section containing `Langue`, `Langues`, `Language`, `Languages`, `Idiomas`, or followed by a proficiency word: `courant`, `natif`, `maternelle`, `bilingue`, `professionnel`, `notions`, `fluent`, `native`, `intermediate`, `B1`–`C2`). Only redact nationality when introduced by `Nationalité`, `Nationality`, `de nationalité`, or similar.
6. Birthplace: `Né(e) le … à <Ville>` / `born in <City>` → redact the city too.

**Tests to add** (`backend/tests/test_anonymize.py` + a new parametrised fixture file `backend/tests/fixtures/pii_cases.yaml` with ≥ 25 cases):
- Name not on the first line (after a `Curriculum Vitae` header), name in uppercase surname form (`Youssef AMRANI`), compound names (`Fatima-Zahra El Idrissi`), name only derivable from email.
- Family status FR and EN.
- `Langues : Français courant, Anglais professionnel, Arabe natif` → all three languages **preserved**.
- `Nationalité : Marocaine` → redacted.
- Moroccan phone formats (`+212 6 61 23 45 67`, `06-61-23-45-67`, `0661234567`, `+212661234567`), CIN, emails, LinkedIn/GitHub URLs.
- Strengthen the existing "no identity data in outgoing requests" test: run it over **all** `pii_cases.yaml` inputs and all 30 `eval/` CVs, intercept the LLM call, and assert that none of the original name tokens, emails, phones, CINs, family-status phrases or birth dates appear in the payload.

---

## P0-2 — API key usage is never recorded; per-key budgets never enforced (owner: A3, reviewer: A2)

**Observed** (`backend/shortlist/worker/queue.py`, ~line 392): `api_key_id: str | None = None` is never assigned, although `LLMRouter` returns the used key (`key_id`, router.py ~line 232). Consequences: `_record_usage` returns early, `UsageLog` stays empty, monthly budget per key is never enforced, the "costs per key" log screen is empty, and `Evaluation.api_key_id` is always null.

**Required fixes**
1. Make `evaluate_cv` (or the `LLMClient` result type) return the `key_id`, `model_used`, tokens and cost of the **successful** call, and propagate them into `Evaluation` and `UsageLog`.
2. Also record usage (tokens/cost, status) for **failed attempts that consumed tokens** (e.g. invalid JSON responses), so budgets reflect real spend.
3. `fallback_used` must be true whenever the final model **or** provider differs from the profile's first entry.

**Tests**: with a fake router that uses key B after key A returns 429, assert `Evaluation.api_key_id == B`, one `UsageLog` row for B with tokens and cost > 0, and that a key whose monthly budget is exhausted by recorded usage is skipped on the next task.

---

## P0-3 — A mandatory `non` without evidence auto-rejects the candidate (owner: A2, reviewer: A1)

**Observed** (`backend/shortlist/core/scoring/scorer.py`, `compute_recommendation`): any mandatory criterion with verdict `NO` returns `NOT_RETAINED`, even when the LLM gave no quote or the quote was not found in the CV. Spec §5 requires "un obligatoire `non` **avec citation contraire**".

**Required fixes**
1. In `verify_criterion`, a `NO` verdict whose quote is empty or not verified must be downgraded to `UNPROVEN` (keep `original_verdict = NO`, `verified = False`).
2. In `compute_recommendation`, only a mandatory `NO` with `verified = True` may produce `NOT_RETAINED`. A mandatory `UNPROVEN` goes to `REVIEW`.
3. Update the evaluation prompt (`prompts/evaluate_v2.md`, keep v1 for history, bump the prompt version stored on evaluations): for `non`, the model must quote the CV passage that contradicts the criterion (e.g. "2 ans d'expérience" against "3 ans minimum"); if the information is simply absent it must answer `non_trouve`, not `non`.
4. Bump `FORMULA_VERSION` to `v2` and document the change.

**Tests**: mandatory `NO` with empty quote → `REVIEW`; mandatory `NO` with fabricated quote → `REVIEW`; mandatory `NO` with a real contradicting quote → `NOT_RETAINED`; existing scoring tests still pass.

---

## P1-1 — Rate limits (RPM / TPM / per day) are not enforced across tasks (owner: A2 + A3)

**Observed**: `build_llm_client_for_job` rebuilds a fresh `KeyPool` for every task, so in-memory counters reset at every CV, and the 4 worker threads each have their own pool. Only provider 429s protect quotas.

**Required fix**: create **one** `KeyPool` per worker process, shared and thread-safe (locks around counters and concurrency slots), refreshed from the DB periodically (e.g. every 30 s) for new/changed keys while keeping live counters. Daily counters (`rpd_limit`) must be computed from `UsageLog` at startup so a worker restart does not reset them. Persist cooldowns as today.

**Tests**: with `rpm_limit=2` and 6 tasks processed concurrently by 4 threads, no more than 2 calls per rolling minute reach the fake provider for that key (use an injectable clock); `rpd_limit` survives a simulated worker restart.

---

## P1-2 — Criteria grid not frozen per run (owner: A3)

**Observed**: `process_task` uses the latest `CriteriaSet` version, not the one active when the run started. Editing the grid during a run mixes versions.

**Required fix**: store `criteria_set_version` on `AnalysisRun` at creation (Alembic migration `0003`), use it in `process_task`, and make `PUT /api/jobs/{id}/criteria` create a new version without affecting running runs. The UI must show which grid version each evaluation used and offer "re-analyse with the new grid".

**Tests**: start a run, change the grid mid-run, assert every evaluation of that run uses the original version.

---

## P1-3 — Too-short quotes pass verification (owner: A2)

**Observed**: `verify_quote` accepts a 1-word quote such as `SAP` (partial_ratio matches trivially).

**Required fix**: require a quote of at least **4 words or 20 characters** (configurable). Shorter quotes → `UNPROVEN`. Update the prompt to ask for a full phrase. For exact-match quality, compute the score on normalised text (lowercase, collapsed whitespace, unified quotes/dashes) and keep spans mapped back to original offsets.

**Tests**: `"SAP"` → unproven; `"Maîtrise de SAP MM au quotidien"` present in CV → verified with correct span.

---

## P1-4 — Insecure default secret key (owner: A3 + A5)

**Observed**: `config.py` and `docker-compose.yml` default `SHORTLIST_SECRET_KEY` to `dev-insecure-change-me-in-production`; API keys get encrypted with a public key if the user forgets to set it.

**Required fix**: remove the default from compose. On startup, API and worker refuse to run if the key is missing, equals a known placeholder, or is not a valid Fernet key — unless `SHORTLIST_ENV=dev`. Provide `shortlist gen-secret` (prints a valid Fernet key) and a `deploy/init.sh` / `init.ps1` that creates `deploy/.env` with a generated key on first run. Update README install steps (Windows and Linux/macOS).

**Tests**: startup fails with placeholder or missing key outside dev; succeeds with a generated key.

---

## P2 — Smaller items

1. **PostgreSQL profile broken** (A3/A5): add `psycopg[binary]` as an optional extra `postgres`, install it in the images, and add a CI job that runs the integration tests against a Postgres 16 service container.
2. **Evidence highlighting is fragile** (A4): highlighting in `CvViewer.tsx` does an exact per-text-item substring match. Use the backend-provided `span` (start/end on the anonymised text) for the anonymised view, and for the original PDF view use a fuzzy, whitespace-insensitive search across concatenated text items (spanning line breaks). Quotes containing redaction tokens (`[ENTREPRISE_1]`) must match by ignoring the token. Add a Playwright test with a quote spanning two lines.
3. **Repo hygiene** (A5): remove `frontend/test-results/` from git and add it (and `playwright-report/`) to `.gitignore`; add a pre-commit check that blocks `*.db`, `.coverage`, `data/` and `test-results/`.
4. **Alembic warning**: set `path_separator = os` in `alembic.ini`.
5. **mypy config**: remove the unused override sections reported by mypy.

---

## Definition of done

- [ ] Every item above has a reproducing test that failed before the fix and passes after.
- [ ] The P0-1 leak test passes on all `pii_cases.yaml` cases and all 30 `eval/` CVs, with the real spaCy models installed in CI.
- [ ] `docker compose -f deploy/docker-compose.yml up --build` works on a clean machine after running the init script, with no default secret.
- [ ] `shortlist eval --profile <fake>` still runs; scores/recommendations changes caused by formula v2 are listed in `docs/RELEASE_NOTES_v0.1.1.md`.
- [ ] A1 posts a final report: one line per defect (fixed / test name / commit), plus anything that could not be fixed and why.
