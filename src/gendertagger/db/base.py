"""Shared SQLAlchemy declarative infrastructure."""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, MetaData, column, func
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

EnumType = TypeVar("EnumType", bound=StrEnum)


def _enum_values(enum_class: type[StrEnum]) -> Sequence[str]:
    return [member.value for member in enum_class]


def stored_enum(enum_class: type[EnumType], *, name: str) -> Enum:
    """Build a validated string enum without a PostgreSQL enum type."""
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=False,
        validate_strings=True,
        values_callable=_enum_values,
    )


def enum_check(
    column_name: str,
    enum_class: type[StrEnum],
    *,
    name: str,
) -> CheckConstraint:
    """Build an explicit, Alembic-comparable enum value constraint."""
    return CheckConstraint(column(column_name).in_(_enum_values(enum_class)), name=name)


class Base(DeclarativeBase):
    """Declarative base carrying deterministic constraint names."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UuidPrimaryKeyMixin:
    """Application-generated UUID primary key shared by durable resources."""

    id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class CreatedAtMixin:
    """Timezone-aware creation timestamp populated by PostgreSQL."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class UpdatedAtMixin:
    """Timezone-aware modification timestamp for mutable projections."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
