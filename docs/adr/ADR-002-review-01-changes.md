# ADR-002: Review #1 Behavioural & Security Hardening

- **Status:** Accepted
- **Date:** 2026-11-24
- **Authors:** Shortlist Team (A1 Lead)

## Context

Following code review #1 on the v0.1.0 MVP, three behavioural/contract gaps were identified that require explicit architectural decisions and spec updates:
1. Unverified `NO` verdicts could unfairly auto-demote candidates to `not_retained` without a verified contradicting quote, and short 1–2 word quotes could pass fuzzy verification.
2. Editing a job's criteria grid while an `AnalysisRun` was in flight could cause mixed criteria versions within a single run.
3. Defaulting `SHORTLIST_SECRET_KEY` to a static placeholder risked silent insecure deployments in production.

## Decisions

### 1. Verification & Scoring Formula v2 (P0-3, P1-3)
- **Quote length threshold:** Quotes must be at least 4 words or 20 characters (configurable); shorter quotes are downgraded to `unproven` (`non_prouve`). Verification runs on normalized text and maps spans back to original text offsets.
- **Unverified `NO` downgrade:** A `no` verdict without a verified contradicting quote is downgraded to `unproven` (`original_verdict = no`, `verified = False`).
- **Recommendation rule:** Only a mandatory criterion with `no` AND `verified = True` triggers `not_retained`; mandatory `unproven` triggers `review`.
- **Prompt & formula versioning:** Introduce `prompts/evaluate_v2.md` (preserving `evaluate_v1.md` for historical audits) requiring full-phrase quotes (including contradicting quotes for `no`), and bump `FORMULA_VERSION = "v2"`.

### 2. Frozen `criteria_set_version` on `AnalysisRun` (P1-2)
- `analysis_runs` adds a `criteria_set_version` column (Alembic migration `0003_analysis_run_criteria_version`) captured when the run starts.
- Updating criteria (`PUT /api/jobs/{id}/criteria`) creates a new `CriteriaSet` version without mutating the version bound to active runs. The UI displays the version used per evaluation and offers re-analysis when a newer grid version exists.

### 3. Fail-Closed `SHORTLIST_SECRET_KEY` & NLP Startup Checks (P0-1, P1-4)
- API and worker refuse to start if `SHORTLIST_SECRET_KEY` is missing, equals the insecure placeholder, or is not a valid Fernet key, unless `SHORTLIST_ENV=dev`. `shortlist gen-secret` generates a valid key; `deploy/init.sh` and `deploy/init.ps1` generate `deploy/.env` on first run.
- API and worker refuse to start if spaCy NER models (`fr_core_news_md`, `en_core_web_md`) are missing, unless `SHORTLIST_ALLOW_BLANK_NLP=1`.

## Consequences
- Existing `v1` evaluations remain interpretable via `formula_version = "v1"`.
- Production deployments cannot accidentally boot with blank NER or a hardcoded Fernet key.
