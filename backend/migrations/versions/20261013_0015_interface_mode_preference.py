"""Add the guided/advanced interface-mode presentation preference.

Revision ID: 20261013_0015
Revises: 20261004_0014
Created: 2026-10-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_0015"
down_revision: str | None = "20261004_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `interface_mode`, defaulting existing and new rows to the guided path."""
    op.add_column(
        "user_preferences",
        sa.Column("interface_mode", sa.String(length=8), server_default="guided", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_user_preferences_interface_mode_allowed"),
        "user_preferences",
        "interface_mode IN ('guided', 'advanced')",
    )


def downgrade() -> None:
    """Remove the interface-mode choice while preserving every other saved preference."""
    op.drop_constraint(
        op.f("ck_user_preferences_interface_mode_allowed"),
        "user_preferences",
        type_="check",
    )
    op.drop_column("user_preferences", "interface_mode")
