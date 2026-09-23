"""Persistence-only user, global-role, and project-membership mappings."""

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import (
    Base,
    CreatedAtMixin,
    UpdatedAtMixin,
    UuidPrimaryKeyMixin,
    enum_check,
    stored_enum,
)
from gendertagger.models.user import GlobalRole, ProjectRole


class UserRow(UuidPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """Provider-neutral persistence row for an attributable user."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("btrim(display_name) <> ''", name="display_name_nonblank"),)

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class UserRoleRow(Base):
    """Persistence row assigning one global authorization role to a user (ADR-0033)."""

    __tablename__ = "user_roles"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "role", name="pk_user_roles"),
        enum_check("role", GlobalRole, name="role_allowed"),
    )

    user_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[GlobalRole] = mapped_column(
        stored_enum(GlobalRole, name="user_role"),
        nullable=False,
    )


class ProjectMembershipRow(CreatedAtMixin, UpdatedAtMixin, Base):
    """Persistence row granting one user exactly one role within one project (ADR-0033)."""

    __tablename__ = "project_memberships"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "user_id", name="pk_project_memberships"),
        enum_check("role", ProjectRole, name="role_allowed"),
        Index("ix_project_memberships_user_id", "user_id"),
    )

    project_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[ProjectRole] = mapped_column(
        stored_enum(ProjectRole, name="project_role"),
        nullable=False,
    )
