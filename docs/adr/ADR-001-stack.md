# ADR-001: Technology Stack & Architectural Decisions

- **Status:** Accepted
- **Date:** 2026-11-24
- **Authors:** Shortlist Team (A1 Lead)

## Context

Shortlist is an open-source (AGPL-3.0), self-hosted AI CV screening MVP designed for non-technical recruiters. It must:
1. Run locally via a single `docker compose up` command in under 5 minutes, with zero external cloud dependencies when using Ollama.
2. Process batches of 50–500 CVs reliably with crash recovery, deterministic scoring, verifiable evidence citations, and local PII anonymization before any external LLM call.
3. Provide a modern web UI (French default, English via i18n, RTL-ready) alongside a Python CLI sharing the same core pipeline.

## Decisions

### 1. Monorepo Layout
We adopt a single repository with:
- `backend/shortlist/`: Python 3.12 package managed via `uv` and `hatchling` from root `pyproject.toml`.
  - `core/`: pure, framework-free pipeline (`extract/`, `anonymize/`, `evaluate/`, `verify/`, `scoring/`).
  - `llm/`: LiteLLM wrapper, multi-key pool, quota-aware router, cost tracking.
  - `schemas/`: shared Pydantic v2 contracts (source of truth for API & OpenAPI).
  - `db/`: SQLAlchemy 2.0 models and Alembic migrations.
  - `api/`: FastAPI REST + SSE server.
  - `worker/`: persistent DB-backed task queue worker.
  - `cli.py`: Typer CLI reusing `core/`.
- `frontend/`: Next.js 15 (App Router), TypeScript strict, Tailwind CSS, pnpm.
- `deploy/`: Dockerfiles and `docker-compose.yml` (`api`, `worker`, `web`, `/data` volume, optional `ollama` and `postgres` profiles).

### 2. Backend & Persistence
- **Python 3.12 + FastAPI + Pydantic v2:** Strong typing, automatic OpenAPI 3.1 schema generation, and rich AI/document ecosystem.
- **SQLAlchemy 2.0 + Alembic:** Single codebase supporting **SQLite (WAL mode)** by default (zero-config single-node) and **PostgreSQL** via optional profile for teams.
- **DB-backed task queue:** Avoids requiring Redis for default deployments while guaranteeing crash-resumable batch processing (`analysis_runs` + candidate status).

### 3. LLM Abstraction & Privacy
- **LiteLLM + custom key router:** Supports 100+ providers (Ollama, Gemini, OpenAI, Anthropic, Mistral, Groq, OpenRouter, OpenAI-compatible) with per-key rate limits, cooldowns, and fallback.
- **Local-first anonymization:** Microsoft Presidio + spaCy + custom rules run locally before any external LLM call. Mapping tables are encrypted at rest with Fernet (`SHORTLIST_SECRET_KEY`).
- **Deterministic scoring & verification:** The LLM outputs structured JSON verdicts (`oui`, `partiel`, `non`, `non_trouve`) with exact quotes; `core/verify/` checks quotes via `rapidfuzz` (threshold 90, downgrading unverified claims to `non_prouve`); `core/scoring/` computes the weighted score deterministically in code.

### 4. Frontend
- **Next.js 15 (App Router) + TypeScript strict + Tailwind CSS:** Fast iteration, clean separation from the Python API, and TypeScript client generation from FastAPI's OpenAPI schema.
- **Server-Sent Events (SSE):** Real-time batch progress without WebSocket complexity.

### 5. Licensing & Language Policy
- **AGPL-3.0:** Ensures hosted modifications remain open source and is compatible with PyMuPDF and all chosen dependencies.
- **Language:** All code, identifiers, comments, commits, and developer docs are in English. End-user UI is French by default with English support via `next-intl`.

## Consequences
- No Redis or external message broker required for default self-hosted installs.
- Strict boundary between `core/` (pure Python, ≥85% test coverage target) and `api/`/`worker/` enables both the web app and the CLI to share identical screening logic.
- OpenAPI schema exported from FastAPI serves as the contract between backend and frontend teams.
