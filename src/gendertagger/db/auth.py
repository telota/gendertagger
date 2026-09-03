"""Persistence-only local-account credential and session mappings (ADR-0031)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import Base, CreatedAtMixin, UpdatedAtMixin


class UserCredentialRow(UpdatedAtMixin, Base):
    """Local-account credential, one row per admin-provisioned user.

    Kept separate from ``UserRow`` so a future SSO-provisioned user carries no credential row at all.
    """

    __tablename__ = "user_credentials"
    __table_args__ = (
        UniqueConstraint("username", name="uq_user_credentials_username"),
        CheckConstraint("btrim(username) <> ''", name="username_nonblank"),
    )

    user_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class UserSessionRow(CreatedAtMixin, Base):
    """Server-side session, addressed by a SHA-256 hash of its bearer token.

    The raw token is never persisted, only its hash, mirroring the repository's existing caution around
    not storing secrets in the clear. A session is revoked in place rather than deleted, so its lifetime
    remains auditable.
    """

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    csrf_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
