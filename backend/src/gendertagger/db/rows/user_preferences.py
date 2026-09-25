"""Persistence-only account presentation preferences (ADR-0043)."""

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import Base
from gendertagger.models.user_preferences import InterfaceLocale, InterfaceTheme


class UserPreferencesRow(Base):
    """One optional presentation-preferences row owned by an existing user."""

    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("locale IN ('de', 'en')", name="locale_allowed"),
        CheckConstraint("theme IN ('system', 'light', 'dark')", name="theme_allowed"),
        CheckConstraint("revision >= 0", name="revision_nonnegative"),
    )

    user_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    locale: Mapped[InterfaceLocale | None] = mapped_column(String(2), nullable=True)
    theme: Mapped[InterfaceTheme] = mapped_column(
        String(6), nullable=False, default="system", server_default="system"
    )
    desktop_sidebar_collapsed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
