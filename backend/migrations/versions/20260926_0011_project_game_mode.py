"""Add the project-level game-mode opt-in.

Revision ID: 20260926_0011
Revises: 20260926_0010
Created: 2026-09-26 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0011"
down_revision: str | None = "20260926_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Default every existing and future project to disabled game mode."""
    op.add_column(
        "projects",
        sa.Column(
            "game_mode_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove the project-level game-mode opt-in."""
    op.drop_column("projects", "game_mode_enabled")
