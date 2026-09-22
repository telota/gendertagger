"""Keyset slicing shared by newest-first collection queries."""

from datetime import datetime
from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select, and_, or_
from sqlalchemy.orm import InstrumentedAttribute

from gendertagger.services.pagination import CreationPosition

_RowT = TypeVar("_RowT")


def newest_first_slice(
    statement: Select[tuple[_RowT]],
    *,
    created_at: InstrumentedAttribute[datetime],
    row_id: InstrumentedAttribute[UUID],
    limit: int,
    after: CreationPosition | None,
) -> Select[tuple[_RowT]]:
    """Order a statement by descending ``(created_at, id)`` and keep one slice after ``after``.

    ``created_at`` is a transaction timestamp, so rows created together share it and the UUID
    tie-breaker is what keeps the order total.
    """
    if limit <= 0:
        msg = "limit must be positive"
        raise ValueError(msg)
    if after is not None:
        statement = statement.where(
            or_(
                created_at < after.created_at,
                and_(created_at == after.created_at, row_id < after.id),
            )
        )
    return statement.order_by(created_at.desc(), row_id.desc()).limit(limit)
