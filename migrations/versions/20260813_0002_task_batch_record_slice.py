"""task batch record slice

Revision ID: 20260813_0002
Revises: 20260813_0001
Created: 2026-08-13 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0002"
down_revision: str | None = "20260813_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the deterministic person-slice columns to task batches."""
    op.add_column("task_batches", sa.Column("record_offset", sa.Integer(), nullable=False))
    op.add_column("task_batches", sa.Column("record_count", sa.Integer(), nullable=False))
    op.create_check_constraint("record_offset_nonnegative", "task_batches", "record_offset >= 0")
    op.create_check_constraint("record_count_positive", "task_batches", "record_count > 0")


def downgrade() -> None:
    """Drop the deterministic person-slice columns from task batches."""
    op.drop_constraint(op.f("ck_task_batches_record_count_positive"), "task_batches", type_="check")
    op.drop_constraint(
        op.f("ck_task_batches_record_offset_nonnegative"), "task_batches", type_="check"
    )
    op.drop_column("task_batches", "record_count")
    op.drop_column("task_batches", "record_offset")
