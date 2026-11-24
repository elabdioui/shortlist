# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Phase 0 smoke tests for API, schemas, database models, and Alembic migrations."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from shortlist.api.app import app
from shortlist.db.session import create_db_engine
from shortlist.schemas import (
    CriterionItem,
    CriterionType,
    CriterionVerdict,
    JobCreate,
    LLMOutputCriterion,
    LLMOutputSchema,
)

EXPECTED_TABLES = {
    "users",
    "providers",
    "api_keys",
    "model_profiles",
    "jobs",
    "criteria_sets",
    "candidates",
    "evaluations",
    "decisions",
    "analysis_runs",
    "usage_log",
    "audit_log",
}


def test_health_endpoint() -> None:
    """GET /api/health returns ok and current version."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_openapi_schema_contains_health() -> None:
    """FastAPI generates an OpenAPI schema with /api/health."""
    schema = app.openapi()
    assert schema["info"]["title"] == "Shortlist"
    assert "/api/health" in schema["paths"]


def test_alembic_initial_migration(tmp_path: Path) -> None:
    """Alembic 0001_initial creates all 12 core tables on SQLite."""
    db_file = tmp_path / "test_shortlist.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    backend_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", str(backend_dir / "shortlist" / "db" / "migrations")
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(tables)
    engine.dispose()


def test_schemas_v1_validation() -> None:
    """Shared Pydantic v2 contracts validate expected structures."""
    job = JobCreate(title="Supply Chain Buyer", description="3+ years experience in procurement.")
    assert job.interview_threshold == 70.0
    assert job.review_threshold == 45.0

    criterion = CriterionItem(
        id="c1",
        label="Procurement experience",
        description="At least 3 years in supply chain procurement",
        type=CriterionType.MANDATORY,
        weight=5,
    )
    assert criterion.weight == 5

    llm_out = LLMOutputSchema(
        criteria=[
            LLMOutputCriterion(
                id="c1",
                verdict=CriterionVerdict.YES,
                quote="5 years as Buyer at ACME",
                explanation="Exceeds 3 years requirement.",
            )
        ],
        relevant_experience_years=5.0,
        languages=["fr", "en"],
    )
    assert llm_out.criteria[0].verdict == CriterionVerdict.YES
