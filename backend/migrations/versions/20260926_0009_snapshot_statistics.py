"""Persist immutable source-inventory statistics on ready snapshots.

Revision ID: 20260926_0009
Revises: 20260925_0008
Created: 2026-09-26 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260926_0009"
down_revision: str | None = "20260925_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable statistics so existing ready snapshots remain valid legacy data."""
    op.add_column(
        "dataset_snapshots",
        sa.Column(
            "statistics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_dataset_snapshots_statistics_requires_ready"),
        "dataset_snapshots",
        "statistics IS NULL OR status = 'ready'",
    )


def downgrade() -> None:
    """Remove snapshot statistics without changing imported person records."""
    op.drop_constraint(
        op.f("ck_dataset_snapshots_statistics_requires_ready"),
        "dataset_snapshots",
        type_="check",
    )
    op.drop_column("dataset_snapshots", "statistics")
