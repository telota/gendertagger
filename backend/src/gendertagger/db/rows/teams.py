"""Persistence-only team and direct-team-membership mappings (ADR-0041 slice 1)."""

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import Base, CreatedAtMixin, UpdatedAtMixin, UuidPrimaryKeyMixin


class TeamRow(UuidPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """Persistence row for one administrator-managed direct-membership team."""

    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'", name="slug_format"),
        CheckConstraint("btrim(display_name) <> ''", name="display_name_nonblank"),
        UniqueConstraint("slug", name="slug"),
    )

    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)


class TeamMembershipRow(CreatedAtMixin, Base):
    """Persistence row recording one user's direct membership in one team."""

    __tablename__ = "team_memberships"
    __table_args__ = (
        PrimaryKeyConstraint("team_id", "user_id", name="pk_team_memberships"),
        Index("ix_team_memberships_user_id", "user_id"),
    )

    team_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
