"""snapshot import dispatch outbox

Revision ID: 20260814_0006
Revises: 20260814_0005
Created: 2026-08-14 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0006"
down_revision: str | None = "20260814_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow exactly one batch, aggregation, or snapshot target per dispatch."""
    op.add_column(
        "batch_dispatches",
        sa.Column("dataset_snapshot_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_batch_dispatches_dataset_snapshot_id_dataset_snapshots"),
        "batch_dispatches",
        "dataset_snapshots",
        ["dataset_snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "dataset_snapshot_single_dispatch",
        "batch_dispatches",
        ["dataset_snapshot_id"],
    )
    op.drop_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        "num_nonnulls(task_batch_id, aggregation_execution_id, dataset_snapshot_id) = 1",
    )


def downgrade() -> None:
    """Remove snapshot dispatches and restore the two-target outbox."""
    op.drop_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        type_="check",
    )
    op.execute(sa.text("DELETE FROM batch_dispatches WHERE dataset_snapshot_id IS NOT NULL"))
    op.drop_constraint(
        "dataset_snapshot_single_dispatch",
        "batch_dispatches",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_batch_dispatches_dataset_snapshot_id_dataset_snapshots"),
        "batch_dispatches",
        type_="foreignkey",
    )
    op.drop_column("batch_dispatches", "dataset_snapshot_id")
    op.create_check_constraint(
        op.f("ck_batch_dispatches_exactly_one_target"),
        "batch_dispatches",
        "(task_batch_id IS NOT NULL) <> (aggregation_execution_id IS NOT NULL)",
    )
