"""Sliding session lifetime with an opt-in persistent sign-in (ADR-0032).

Revision ID: 20260921_0003
Revises: 20260903_0002
Created: 2026-09-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0003"
down_revision: str | None = "20260903_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the session kind and absolute limit; existing sessions keep their original end."""
    op.add_column(
        "user_sessions",
        sa.Column("keep_signed_in", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "user_sessions",
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # A pre-existing session was issued under ADR-0031's fixed lifetime. Capping it at its current
    # expiry means the sliding renewal can never extend it.
    op.execute("UPDATE user_sessions SET absolute_expires_at = expires_at")
    op.alter_column("user_sessions", "absolute_expires_at", nullable=False)
    op.create_check_constraint(
        op.f("ck_user_sessions_expiry_within_lifetime"),
        "user_sessions",
        "expires_at <= absolute_expires_at",
    )


def downgrade() -> None:
    """Drop the session kind and absolute limit, returning to fixed-lifetime sessions."""
    op.drop_constraint(
        op.f("ck_user_sessions_expiry_within_lifetime"), "user_sessions", type_="check"
    )
    op.drop_column("user_sessions", "absolute_expires_at")
    op.drop_column("user_sessions", "keep_signed_in")
