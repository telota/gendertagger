"""Add the deployment-settings singleton for administrative branding reads.

Revision ID: 20260924_0006
Revises: 20260815_0001
Created: 2026-09-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260924_0006"
down_revision: str | None = "20260815_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create and initialize the one deployment-wide settings record."""
    op.create_table(
        "deployment_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "branding_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_deployment_settings_singleton_id")),
        sa.CheckConstraint(
            "revision >= 0", name=op.f("ck_deployment_settings_revision_nonnegative")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(branding_overrides) = 'object'",
            name=op.f("ck_deployment_settings_branding_overrides_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deployment_settings")),
    )
    op.execute(
        sa.text(
            "INSERT INTO deployment_settings (id, revision, branding_overrides) "
            "VALUES (1, 0, '{}'::jsonb)"
        )
    )


def downgrade() -> None:
    """Remove the deployment-settings singleton table."""
    op.drop_table("deployment_settings")
