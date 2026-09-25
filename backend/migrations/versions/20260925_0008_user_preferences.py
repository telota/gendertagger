"""Add account-owned presentation preferences without materializing defaults.

Revision ID: 20260925_0008
Revises: 20260925_0007
Created: 2026-09-25 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0008"
down_revision: str | None = "20260925_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create typed account preferences; missing rows retain virtual defaults."""
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("locale", sa.String(length=2), nullable=True),
        sa.Column("theme", sa.String(length=6), server_default="system", nullable=False),
        sa.Column(
            "desktop_sidebar_collapsed", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "locale IN ('de', 'en')", name=op.f("ck_user_preferences_locale_allowed")
        ),
        sa.CheckConstraint(
            "theme IN ('system', 'light', 'dark')", name=op.f("ck_user_preferences_theme_allowed")
        ),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_user_preferences_revision_nonnegative")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_preferences")),
    )


def downgrade() -> None:
    """Remove presentation preferences while preserving accounts and credentials."""
    op.drop_table("user_preferences")
