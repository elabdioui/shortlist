"""Add analysis_tasks, privacy_settings, and unique evaluation constraint.

Revision ID: 0002_phase3_tasks_privacy
Revises: 0001_initial
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase3_tasks_privacy"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "candidate_id", name="uq_task_run_candidate"),
    )
    op.create_index("ix_analysis_tasks_run_id", "analysis_tasks", ["run_id"], unique=False)
    op.create_index("ix_analysis_tasks_job_id", "analysis_tasks", ["job_id"], unique=False)
    op.create_index(
        "ix_analysis_tasks_candidate_id", "analysis_tasks", ["candidate_id"], unique=False
    )
    op.create_index("ix_analysis_tasks_status", "analysis_tasks", ["status"], unique=False)
    op.create_index(
        "ix_analysis_tasks_leased_until", "analysis_tasks", ["leased_until"], unique=False
    )

    op.create_table(
        "privacy_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("anonymization_level", sa.String(length=16), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("auto_purge_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_purge_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.create_unique_constraint(
            "uq_evaluation_candidate_version", ["candidate_id", "criteria_set_version"]
        )


def downgrade() -> None:
    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.drop_constraint("uq_evaluation_candidate_version", type_="unique")

    op.drop_table("privacy_settings")
    op.drop_table("analysis_tasks")
