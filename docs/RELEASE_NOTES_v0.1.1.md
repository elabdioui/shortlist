# Shortlist v0.1.1 — Release Notes (Fix Pass #1)

**Release Date:** 2026-11-24  
**Branch:** `fix/review-01`  
**License:** AGPL-3.0-or-later

This release addresses all P0, P1, and P2 findings from Code Review #1 using a strict test-first workflow, alongside a shadcn/ui frontend redesign and circular-import fix.

## Security & Privacy Fixes

- **P0-1 — Fail-closed spaCy NER & stronger PII anonymization:**
  - Bundled `fr_core_news_md` and `en_core_web_md` spaCy models in `pyproject.toml`, Dockerfiles, and CI; API and worker refuse to start if NER models are missing unless `SHORTLIST_ALLOW_BLANK_NLP=1`.
  - Added header name heuristic (first 8 lines) + email-derived name redaction, FR/EN marital & family status recognizer (`[FAMILY_STATUS_n]`), language demonym preservation vs. labeled nationality redaction, and FR/EN birthplace city redaction.
  - Verified against 26 cases in `backend/tests/fixtures/pii_cases.yaml` and all 30 synthetic CVs in `eval/`.
- **P1-4 — Strict `SHORTLIST_SECRET_KEY`:**
  - API and worker refuse to start if `SHORTLIST_SECRET_KEY` is missing, equals the insecure placeholder, or is not a valid Fernet key, unless `SHORTLIST_ENV=dev`.
  - Added `shortlist gen-secret` CLI command, `deploy/init.sh`, and `deploy/init.ps1` to generate `deploy/.env` on first run, and removed the default secret from `deploy/docker-compose.yml`.

## Correctness & Reliability Fixes

- **P0-2 — Usage, key attribution & fallback tracking:**
  - Propagates `key_id`, `model_used`, `fallback_used`, tokens, and cost into `Evaluation` and `UsageLog` (including failed JSON attempts), and skips exhausted-budget keys on subsequent tasks.
- **P0-3 & P1-3 — Verification & Scoring Formula v2:**
  - Quotes must be at least 4 words or 20 characters; verification runs on whitespace-normalized text and maps spans back to original offsets.
  - `no` verdicts without a verified contradicting quote are downgraded to `unproven`; only verified mandatory `no` verdicts trigger `not_retained`.
  - Added `prompts/evaluate_v2.md` (preserving `evaluate_v1.md`) and bumped `FORMULA_VERSION = "v2"`.
- **P1-1 — Shared thread-safe `KeyPool`:**
  - One shared `KeyPool` per worker process with locks around RPM/TPM/RPD counters and concurrency slots, 30s DB refresh preserving live counters, and startup RPD initialization from `UsageLog`.
- **P1-2 — Frozen `criteria_set_version` on `AnalysisRun`:**
  - Added `criteria_set_version` to `AnalysisRun` (Alembic migration `0003_analysis_run_criteria_version`) and `AnalysisRunResponse` (`docs/openapi.json`). Mid-run grid edits create a new version without affecting running runs; the UI displays the grid version and offers a re-analysis button when a newer grid exists.

## Frontend, DevOps & Hygiene

- **P2-1:** Added `[postgres]` optional extra (`psycopg[binary]`) in `pyproject.toml`, Dockerfiles, and a Postgres 16 CI integration job.
- **P2-2:** `CvViewer` uses backend `span` offsets for anonymized text and whitespace/redaction-aware multi-line matching for original PDFs.
- **P2-3, P2-4, P2-5:** Untracked `frontend/test-results/` with `.gitignore` + `.pre-commit-config.yaml` guard, added `path_separator = os` in `backend/alembic.ini`, and removed unused mypy overrides.
- **UI Redesign:** Updated frontend components to shadcn/ui primitives + CommandPalette.

## Verification Summary

- `uv run ruff check .`: 0 errors
- `uv run ruff format --check .`: 105 files formatted
- `uv run mypy backend/shortlist`: 0 issues in 65 source files
- `uv run pytest --cov=shortlist.core --cov-report=term-missing backend/tests`: **72 passed**, **93% coverage** on `core/` + `llm/`
- `uv run shortlist eval --fake-llm --eval-dir eval`: `status: "ok"`, `jobs_evaluated: 3`
- `pnpm --dir frontend format:check`, `lint`, `typecheck`, `build` (11 routes), `test:e2e`: **3 passed** (`criteria-version.spec.ts`, `quote-highlight.spec.ts`, `full-flow.spec.ts`)
- `docker compose -f deploy/docker-compose.yml config -q` (with `SHORTLIST_SECRET_KEY` set): exit 0 (runtime `docker compose build/up` blocked locally because Docker Desktop daemon is not running)
