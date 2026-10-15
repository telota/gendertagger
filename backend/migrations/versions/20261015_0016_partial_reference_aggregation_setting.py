"""Add the deployment-wide partial-reference-aggregation setting (ADR-0051).

Revision ID: 20261015_0016
Revises: 20261013_0015
Created: 2026-10-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261015_0016"
down_revision: str | None = "20261013_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `allow_partial_reference_aggregation`, defaulting to enabled (ADR-0051)."""
    op.add_column(
        "deployment_settings",
        sa.Column(
            "allow_partial_reference_aggregation",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove the partial-reference-aggregation setting."""
    op.drop_column("deployment_settings", "allow_partial_reference_aggregation")
