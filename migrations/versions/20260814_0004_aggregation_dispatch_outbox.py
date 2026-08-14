"""aggregation dispatch outbox

Revision ID: 20260814_0004
Revises: 20260814_0003
Created: 2026-08-14 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0004"
down_revision: str | None = "20260814_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow exactly one batch or aggregation target per dispatch entry."""
    op.add_column(
        "batch_dispatches",
        sa.Column("aggregation_execution_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_batch_dispatches_aggregation_execution_id_aggregation_executions"),
        "batch_dispatches",
        "aggregation_executions",
        ["aggregation_execution_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "aggregation_execution_single_dispatch",
        "batch_dispatches",
        ["aggregation_execution_id"],
    )
    op.alter_column(
        "batch_dispatches",
        "task_batch_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.create_check_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        "(task_batch_id IS NOT NULL) <> (aggregation_execution_id IS NOT NULL)",
    )


def downgrade() -> None:
    """Remove aggregation dispatches and restore task-batch-only targets."""
    op.drop_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        type_="check",
    )
    op.execute(sa.text("DELETE FROM batch_dispatches WHERE aggregation_execution_id IS NOT NULL"))
    op.alter_column(
        "batch_dispatches",
        "task_batch_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.drop_constraint(
        "aggregation_execution_single_dispatch",
        "batch_dispatches",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_batch_dispatches_aggregation_execution_id_aggregation_executions"),
        "batch_dispatches",
        type_="foreignkey",
    )
    op.drop_column("batch_dispatches", "aggregation_execution_id")
