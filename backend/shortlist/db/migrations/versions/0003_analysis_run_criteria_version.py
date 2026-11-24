"""Add criteria_set_version to analysis_runs.

Revision ID: 0003_analysis_run_criteria_version
Revises: 0002_phase3_tasks_privacy
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_analysis_run_criteria_version"
down_revision: str | None = "0002_phase3_tasks_privacy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_runs") as batch_op:
        batch_op.add_column(sa.Column("criteria_set_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analysis_runs") as batch_op:
        batch_op.drop_column("criteria_set_version")
