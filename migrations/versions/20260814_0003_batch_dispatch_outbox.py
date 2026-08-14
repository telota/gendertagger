"""batch dispatch outbox

Revision ID: 20260814_0003
Revises: 20260813_0002
Created: 2026-08-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0003"
down_revision: str | None = "20260813_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add durable, lease-based broker dispatch state for task batches."""
    op.create_table(
        "batch_dispatches",
        sa.Column("task_batch_id", sa.UUID(), nullable=False),
        sa.Column("queue_name", sa.String(length=100), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "published",
                name="batch_dispatch_status",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_batch_dispatches_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_until IS NULL) OR "
            "(status = 'pending' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL)",
            name=op.f("ck_batch_dispatches_lease_consistent"),
        ),
        sa.CheckConstraint(
            "lease_owner IS NULL OR btrim(lease_owner) <> ''",
            name=op.f("ck_batch_dispatches_lease_owner_nonblank"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND published_at IS NULL) OR "
            "(status = 'published' AND published_at IS NOT NULL)",
            name=op.f("ck_batch_dispatches_publication_consistent"),
        ),
        sa.CheckConstraint(
            "queue_name ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name=op.f("ck_batch_dispatches_queue_name_format"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'published')",
            name=op.f("ck_batch_dispatches_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["task_batch_id"],
            ["task_batches.id"],
            name=op.f("fk_batch_dispatches_task_batch_id_task_batches"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_dispatches")),
        sa.UniqueConstraint("task_batch_id", name="task_batch_single_dispatch"),
    )
    op.create_index(
        "ix_batch_dispatches_status_available_at",
        "batch_dispatches",
        ["status", "available_at"],
        unique=False,
    )
    op.create_index(
        "ix_batch_dispatches_status_published_at",
        "batch_dispatches",
        ["status", "published_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove durable task-batch dispatch state."""
    op.drop_index("ix_batch_dispatches_status_published_at", table_name="batch_dispatches")
    op.drop_index("ix_batch_dispatches_status_available_at", table_name="batch_dispatches")
    op.drop_table("batch_dispatches")
