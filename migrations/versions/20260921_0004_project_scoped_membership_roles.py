"""Project-scoped membership roles (ADR-0033).

Revision ID: 20260921_0004
Revises: 20260921_0003
Created: 2026-09-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0004"
down_revision: str | None = "20260921_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create project memberships and narrow global roles to operator and admin."""
    op.create_table(
        "project_memberships",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("viewer", "reviewer", "operator", name="project_role", native_enum=False),
            nullable=False,
        ),
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
            "role IN ('viewer', 'reviewer', 'operator')",
            name=op.f("ck_project_memberships_role_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_memberships_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_project_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("project_id", "user_id", name="pk_project_memberships"),
    )
    op.create_index(
        "ix_project_memberships_user_id",
        "project_memberships",
        ["user_id"],
        unique=False,
    )
    # Global viewer and reviewer no longer exist. Their holders get no automatic memberships: an
    # administrator assigns project roles after the upgrade.
    op.execute("DELETE FROM user_roles WHERE role IN ('viewer', 'reviewer')")
    op.drop_constraint(op.f("ck_user_roles_role_allowed"), "user_roles", type_="check")
    op.create_check_constraint(
        op.f("ck_user_roles_role_allowed"),
        "user_roles",
        "role IN ('operator', 'admin')",
    )


def downgrade() -> None:
    """Drop project memberships and restore the four global roles; deleted rows stay deleted."""
    op.drop_constraint(op.f("ck_user_roles_role_allowed"), "user_roles", type_="check")
    op.create_check_constraint(
        op.f("ck_user_roles_role_allowed"),
        "user_roles",
        "role IN ('viewer', 'reviewer', 'operator', 'admin')",
    )
    op.drop_index("ix_project_memberships_user_id", table_name="project_memberships")
    op.drop_table("project_memberships")
