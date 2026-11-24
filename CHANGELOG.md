# Changelog

All notable changes to **Shortlist** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-24

### Added
- **Core Pipeline (`shortlist.core`):**
  - Safe file ingestion (SHA-256 deduplication, MIME/magic validation, 10 MB limit, zip-bomb & path-traversal guards).
  - Multi-format extraction (PyMuPDF 1/2-column reading order, `pdfplumber` fallback, `python-docx` tables, Tesseract `fra+eng` OCR fallback, hidden-text detection).
  - Local PII anonymization (Microsoft Presidio + spaCy + Moroccan `+212`/`06`/`07`/CIN rules) with Fernet-encrypted reversible mapping.
  - Versioned evaluation & criteria prompts (`evaluate_v1.md`, `criteria_v1.md`) with prompt-injection delimiters and anti-discrimination guardrails.
  - `rapidfuzz` evidence quote verification (`>= 90` threshold, `non_prouve` downgrade) and deterministic code-computed scoring (`FORMULA_VERSION = "v1"`).
- **LLM Key-Pool Router (`shortlist.llm`):**
  - LiteLLM integration with priority, round-robin, and lowest-cost routing strategies, RPM/TPM/daily/budget limits, `429` cooldowns, `401/403` invalidation, and `vcrpy` contract tests.
- **API, Worker & CLI (`shortlist.api`, `shortlist.worker`, `shortlist.cli`):**
  - FastAPI REST API with Argon2 auth, `httpOnly` cookie sessions, CSRF protection, rate limiting, SSE run progress, and `.xlsx`/`.csv` export.
  - Persistent DB-backed worker with crash recovery and SQLite WAL / PostgreSQL support.
  - `shortlist screen` and `shortlist eval` CLI commands.
- **Frontend (`frontend/`):**
  - Next.js 15 App Router UI in French (default) and English (`next-intl`), light/dark theme, split CV viewer with quote highlighting, ranking table, and provider/privacy/user settings.
- **Evaluation, Docs & DevOps:**
  - `eval/` benchmark dataset (3 fictional jobs, 30 synthetic CVs).
  - Multi-arch (`amd64`/`arm64`) Docker Compose deployment (`api`, `worker`, `web`, optional `ollama` & `postgres` profiles).
  - GitHub Actions CI & GHCR release workflows, MkDocs site, and recruiter/provider/governance documentation.
