from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from gendertagger.db.keyset import newest_first_slice
from gendertagger.db.rows.executions import RunRow
from gendertagger.services.pagination import CreationPosition

pytestmark = pytest.mark.unit


def _sql(position: CreationPosition | None) -> str:
    statement = newest_first_slice(
        select(RunRow),
        created_at=RunRow.created_at,
        row_id=RunRow.id,
        limit=3,
        after=position,
    )
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]  # Dynamic factory.
    return str(statement.compile(dialect=dialect))


def test_newest_first_slice_orders_by_descending_creation_then_id() -> None:
    first_page = _sql(None)
    continuation = _sql(
        CreationPosition(
            created_at=datetime(2026, 9, 22, 10, 0, tzinfo=UTC),
            id=UUID("10000000-0000-0000-0000-000000000001"),
        )
    )

    assert "ORDER BY runs.created_at DESC, runs.id DESC" in first_page
    assert "WHERE" not in first_page
    assert (
        "runs.created_at < %(created_at_1)s OR "
        "runs.created_at = %(created_at_2)s AND runs.id < %(id_1)s::UUID"
    ) in continuation


def test_newest_first_slice_requires_a_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit must be positive"):
        newest_first_slice(
            select(RunRow),
            created_at=RunRow.created_at,
            row_id=RunRow.id,
            limit=0,
            after=None,
        )
