# Shortlist Evaluation Dataset

This directory contains **3 fictional job descriptions** and **30 synthetic CVs** (10 per job, zero real candidate data) annotated criterion-by-criterion for benchmarking Shortlist's evaluation pipeline.

## Structure

- `01_supply_chain_buyer/` — Supply Chain Buyer (French)
- `02_backend_python_engineer/` — Backend Python Engineer (English)
- `03_hr_generalist/` — HR Generalist (French)

Each job folder contains:
- `job.txt` — Fictional job description.
- `criteria.json` — Annotated criteria grid (`id`, `label`, `description`, `type`, `weight`).
- `annotations.json` — Ground-truth `expected_verdicts`, `expected_rank`, and `expected_recommendation` per CV.
- `cvs/` — 10 synthetic `.txt` CVs.

## Running the Benchmark

```bash
# Deterministic offline check
uv run shortlist eval --fake-llm --eval-dir eval

# Against a configured model profile
uv run shortlist eval --profile economical --eval-dir eval
```

Metrics reported:
- **Per-criterion agreement**: Percentage of `(CV, criterion)` pairs matching the ground-truth verdict.
- **Spearman rank correlation**: Rank correlation between Shortlist's computed ranking and `expected_rank`.
- **Verified quote rate**: Percentage of `yes`/`partial` verdicts backed by a verified quote in the CV text.
