# Shortlist v0.1.0 — Release Notes

**Release Date:** 2026-11-24  
**License:** AGPL-3.0-or-later

Shortlist is an open-source, self-hosted AI CV screening MVP. It ranks candidate CVs against a job's criteria grid, verifies every evidence quote against the extracted CV text, and leaves hiring decisions strictly to humans.

## Highlights

- **Human-in-the-loop by design:** No automatic rejections; the lowest automated recommendation is `not_retained` ("Non retenu, à confirmer"), and recruiters can override any criterion verdict with live deterministic score recalculation.
- **Deterministic scoring & quote verification:** LLMs evaluate criteria (`yes`, `partial`, `no`, `not_found`) with verbatim quotes; `rapidfuzz` (`partial_ratio >= 90`) verifies quotes and downgrades unverified claims to `unproven`; code computes `100 * sum(w_i * v_i) / sum(w_i)` (`FORMULA_VERSION = "v1"`).
- **Privacy-first local anonymization:** Presidio + spaCy + custom rules (Moroccan `+212`/`06`/`07` phones, CIN, emails, LinkedIn/GitHub URLs, addresses, age/DOB, marital status, nationality, person names) anonymize CVs locally before any external LLM call, with Fernet-encrypted mapping tables (`SHORTLIST_SECRET_KEY`).
- **Multi-provider LLM router:** LiteLLM-backed router supporting Ollama (100% local), Gemini, OpenAI, Anthropic, Mistral, Groq, OpenRouter, and OpenAI-compatible endpoints with priority/round-robin/lowest-cost strategies, local RPM/TPM/RPD/budget counters, 429 cooldown failover, 401/403 invalidation, and 5xx/timeout fallback tracking.
- **Crash-resumable batch processing:** DB-backed `AnalysisTask` queue with atomic task leasing and stale-lease recovery (`SQLite` WAL by default, optional `PostgreSQL` profile), plus live SSE progress updates.
- **Recruiter-friendly Web UI & CLI:** Next.js 15 App Router UI (French default, English toggle via `next-intl`, light/dark theme, split CV viewer with quote highlighting, TanStack Table ranking, formatted `.xlsx` and `.csv` exports) and `shortlist` CLI (`version`, `screen`, `eval`).

## Verification Summary (v0.1.0)

- **Backend lint & typecheck:** `uv run ruff check .` (0 errors), `uv run ruff format --check .` (92 files formatted), `uv run mypy backend/shortlist` (0 issues in 63 source files).
- **Backend tests:** `uv run pytest --cov=shortlist.core --cov-report=term-missing backend/tests` — **52 passed**, **93% coverage** on `shortlist.core` (including 50-CV crash-and-resume integration test, fairness/security suite, and synthetic `vcrpy` cassettes for OpenAI, Gemini, and Ollama).
- **Evaluation benchmark (fake-LLM baseline):** `uv run shortlist eval --fake-llm --eval-dir eval` — 3 fictional jobs × 10 synthetic CVs (`verified_quote_rate: 1.0`).
- **Frontend & E2E:** `pnpm --dir frontend format:check`, `lint`, `typecheck`, `build` (11 routes), and `test:e2e` (Playwright full-flow against FastAPI + Worker with `SHORTLIST_FAKE_LLM=1`).
- **Compose config:** `docker compose -f deploy/docker-compose.yml config -q` passed.

## Known Limitations & Operational Notes

- Runtime `docker compose build` / `up` was not executed in the local build environment because the Docker Desktop daemon was not running; CI/release workflows validate multi-arch (`linux/amd64`, `linux/arm64`) builds.
- `eval/` metrics with `SHORTLIST_FAKE_LLM=1` validate pipeline determinism and quote verification (`1.0`); live-provider accuracy benchmarks are documented separately as providers are configured.
- See [LIMITATIONS.md](../LIMITATIONS.md), [PRIVACY.md](../PRIVACY.md), and [SECURITY.md](../SECURITY.md) before production deployment.
