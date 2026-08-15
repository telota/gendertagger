"""evaluation dispatch outbox

Revision ID: 20260814_0011
Revises: 20260814_0010
Created: 2026-08-15 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0011"
down_revision: str | None = "20260814_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow exactly one batch, aggregation, snapshot, or evaluation target per dispatch."""
    op.add_column(
        "batch_dispatches",
        sa.Column("evaluation_execution_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_batch_dispatches_evaluation_execution_id_evaluation_executions"),
        "batch_dispatches",
        "evaluation_executions",
        ["evaluation_execution_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "evaluation_execution_single_dispatch",
        "batch_dispatches",
        ["evaluation_execution_id"],
    )
    op.drop_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        "num_nonnulls(task_batch_id, aggregation_execution_id, dataset_snapshot_id, "
        "evaluation_execution_id) = 1",
    )


def downgrade() -> None:
    """Remove evaluation dispatches and restore the three-target outbox."""
    op.drop_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        type_="check",
    )
    op.execute(sa.text("DELETE FROM batch_dispatches WHERE evaluation_execution_id IS NOT NULL"))
    op.drop_constraint(
        "evaluation_execution_single_dispatch",
        "batch_dispatches",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_batch_dispatches_evaluation_execution_id_evaluation_executions"),
        "batch_dispatches",
        type_="foreignkey",
    )
    op.drop_column("batch_dispatches", "evaluation_execution_id")
    op.create_check_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        "num_nonnulls(task_batch_id, aggregation_execution_id, dataset_snapshot_id) = 1",
    )
