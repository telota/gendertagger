"""Project working-aggregation pointer (ADR-0035).

Revision ID: 20260922_0005
Revises: 20260921_0004
Created: 2026-09-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260922_0005"
down_revision: str | None = "20260921_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable working-aggregation pointer and its forward foreign key."""
    op.add_column(
        "projects",
        sa.Column("working_aggregation_execution_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_projects_working_aggregation_execution_id_aggregation_executions"),
        "projects",
        "aggregation_executions",
        ["working_aggregation_execution_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Drop the working-aggregation pointer and its foreign key."""
    op.drop_constraint(
        op.f("fk_projects_working_aggregation_execution_id_aggregation_executions"),
        "projects",
        type_="foreignkey",
    )
    op.drop_column("projects", "working_aggregation_execution_id")
