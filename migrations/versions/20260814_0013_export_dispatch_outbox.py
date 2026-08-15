"""export dispatch outbox

Revision ID: 20260814_0013
Revises: 20260814_0012
Created: 2026-08-15 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0013"
down_revision: str | None = "20260814_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow exactly one batch, aggregation, snapshot, evaluation, or export target."""
    op.add_column(
        "batch_dispatches",
        sa.Column("export_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_batch_dispatches_export_id_export_executions"),
        "batch_dispatches",
        "export_executions",
        ["export_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "export_single_dispatch",
        "batch_dispatches",
        ["export_id"],
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
        "evaluation_execution_id, export_id) = 1",
    )


def downgrade() -> None:
    """Remove export dispatches and restore the four-target outbox."""
    op.drop_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        type_="check",
    )
    op.execute(sa.text("DELETE FROM batch_dispatches WHERE export_id IS NOT NULL"))
    op.drop_constraint(
        "export_single_dispatch",
        "batch_dispatches",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_batch_dispatches_export_id_export_executions"),
        "batch_dispatches",
        type_="foreignkey",
    )
    op.drop_column("batch_dispatches", "export_id")
    op.create_check_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        "num_nonnulls(task_batch_id, aggregation_execution_id, dataset_snapshot_id, "
        "evaluation_execution_id) = 1",
    )
