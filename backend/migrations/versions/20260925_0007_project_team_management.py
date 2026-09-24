"""Associate projects with teams, managers, and historical creators.

Revision ID: 20260925_0007
Revises: 20260924_0006
Created: 2026-09-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0007"
down_revision: str | None = "20260924_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the required project-team and manager relationships.

    ADR-0041 specifies that no legacy projects exist before this relationship is deployed.
    """
    op.add_column("projects", sa.Column("team_id", sa.UUID(), nullable=False))
    op.add_column("projects", sa.Column("manager_user_id", sa.UUID(), nullable=False))
    op.add_column("projects", sa.Column("created_by_user_id", sa.UUID(), nullable=False))
    op.create_foreign_key(
        op.f("fk_projects_team_id_teams"),
        "projects",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_projects_created_by_user_id_users"),
        "projects",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_projects_manager_team_membership",
        "projects",
        "team_memberships",
        ["team_id", "manager_user_id"],
        ["team_id", "user_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_projects_team_id", "projects", ["team_id"], unique=False)
    op.create_index("ix_projects_manager_user_id", "projects", ["manager_user_id"], unique=False)


def downgrade() -> None:
    """Remove the ADR-0041 project-team associations."""
    op.drop_index("ix_projects_manager_user_id", table_name="projects")
    op.drop_index("ix_projects_team_id", table_name="projects")
    op.drop_constraint("fk_projects_manager_team_membership", "projects", type_="foreignkey")
    op.drop_constraint(op.f("fk_projects_created_by_user_id_users"), "projects", type_="foreignkey")
    op.drop_constraint(op.f("fk_projects_team_id_teams"), "projects", type_="foreignkey")
    op.drop_column("projects", "created_by_user_id")
    op.drop_column("projects", "manager_user_id")
    op.drop_column("projects", "team_id")
