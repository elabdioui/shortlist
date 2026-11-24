# Contributing to Shortlist

Thank you for your interest in contributing to **Shortlist**, an open-source, self-hosted AI CV screening tool licensed under **AGPL-3.0**.

## Guiding Principles

Before making changes, please keep Shortlist's core principles in mind:

1. **Human in the loop:** Shortlist never auto-rejects a candidate.
2. **Evidence or nothing:** Every evaluated criterion must quote an exact verifiable snippet from the CV.
3. **Computed scores, not guessed:** The LLM evaluates individual criteria; deterministic code computes the score.
4. **Privacy by default:** PII is anonymized locally before any external LLM call, and 100% local execution via Ollama is supported.
5. **Language policy:** All code, identifiers, comments, commit messages, and developer documentation must be in **English**. User-facing UI and recruiter guides support French (default) and English.

## License & Header Policy (AGPL-3.0)

Shortlist is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0-or-later)**.

Every new source file must include an SPDX license header at the top of the file:

- **Python** (`.py`):
  ```python
  # SPDX-License-Identifier: AGPL-3.0-or-later
  ```
- **TypeScript / JavaScript** (`.ts`, `.tsx`, `.js`, `.jsx`):
  ```ts
  // SPDX-License-Identifier: AGPL-3.0-or-later
  ```

By submitting a pull request, you agree that your contributions are licensed under AGPL-3.0-or-later.

## Development Setup

### Prerequisites

- **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/)
- **Node.js 20+** and `pnpm`
- **Docker** and **Docker Compose** (for full-stack local runs and multi-service testing)

### Backend

```bash
uv sync --all-extras
uv run pytest
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

### Full Stack (Docker Compose)

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## Code Quality & Checks

All pull requests must pass CI checks:

### Python (`backend/`)
- **Linter & Formatter:** `uv run ruff check .` and `uv run ruff format --check .`
- **Type Checking:** `uv run mypy --strict backend/shortlist`
- **Tests:** `uv run pytest` (target coverage ≥ 85% on `shortlist/core/`)

### Frontend (`frontend/`)
- **Lint:** `pnpm lint`
- **Format:** `pnpm format:check`
- **Type Check:** `pnpm typecheck`
- **Build:** `pnpm build`

## Conventional Commits

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```text
<type>(<optional scope>): <short imperative description>
```

Common types:
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `refactor`: Code refactoring without changing behavior
- `ci`: CI/CD workflow or DevOps changes
- `chore`: Maintenance tasks, dependency updates

Examples:
- `feat(core): add Moroccan phone number anonymization rule`
- `fix(llm): handle Retry-After header on 429 responses`
- `docs: clarify Ollama profile setup in PRIVACY.md`

## Prompt Versioning

Prompts are treated as versioned code (e.g., `prompts/evaluate_v1.md`). Because changing a prompt changes evaluation scores, never silently edit an existing prompt version in place—create a new versioned file and document the change.

## Pull Request Process

1. Check existing issues (look for `good first issue` if you are new to the repo).
2. Create a feature branch from `main`.
3. Add tests for any new deterministic logic, edge cases, or bug fixes.
4. Ensure all lint, type, and test checks pass locally.
5. Open a pull request with a clear description of *what* changed and *why*.
