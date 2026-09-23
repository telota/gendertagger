from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from gendertagger.models.api import CursorPage
from gendertagger.services.pagination import (
    CreationPosition,
    CursorCodec,
    InvalidCursorError,
    decode_creation_position,
    newest_first_page,
)

RESOURCE_ID = UUID("40000000-0000-0000-0000-000000000001")
CREATED_AT = datetime(2026, 9, 22, 10, 0, 0, 123456, tzinfo=UTC)


@dataclass(frozen=True)
class _Created:
    id: UUID
    created_at: datetime


def test_cursor_round_trip_preserves_resource_scoped_position() -> None:
    codec = CursorCodec()

    cursor = codec.encode(
        resource="snapshot_people:fixture",
        sort_values=("person-17",),
        resource_id=RESOURCE_ID,
    )
    position = codec.decode(cursor, expected_resource="snapshot_people:fixture")

    assert "=" not in cursor
    assert position.sort_values == ("person-17",)
    assert position.id == RESOURCE_ID


def test_cursor_round_trip_preserves_ordered_composite_sort_keys() -> None:
    codec = CursorCodec()

    cursor = codec.encode(
        resource="review_items:fixture",
        sort_values=("3", "person-17"),
        resource_id=RESOURCE_ID,
    )
    position = codec.decode(
        cursor,
        expected_resource="review_items:fixture",
        expected_sort_value_count=2,
    )

    assert position.sort_values == ("3", "person-17")
    assert position.id == RESOURCE_ID


def test_cursor_rejects_malformed_and_cross_resource_tokens() -> None:
    codec = CursorCodec()
    cursor = codec.encode(
        resource="snapshot_people:first",
        sort_values=("person-17",),
        resource_id=RESOURCE_ID,
    )

    with pytest.raises(InvalidCursorError, match="invalid"):
        codec.decode("not+a+base64url+cursor", expected_resource="snapshot_people:first")
    with pytest.raises(InvalidCursorError, match="different resource"):
        codec.decode(cursor, expected_resource="snapshot_people:second")


def test_cursor_rejects_a_sort_value_count_the_caller_cannot_consume() -> None:
    """A crafted arity must fail as an invalid cursor, never as an index error."""
    codec = CursorCodec()
    cursor = codec.encode(
        resource="review_items:fixture",
        sort_values=("person-17",),
        resource_id=RESOURCE_ID,
    )

    with pytest.raises(InvalidCursorError, match="sort-value count"):
        codec.decode(
            cursor,
            expected_resource="review_items:fixture",
            expected_sort_value_count=2,
        )


def test_cursor_page_requires_consistent_continuation_state() -> None:
    assert CursorPage[int](items=[1], next_cursor=None, has_more=False).items == [1]

    with pytest.raises(ValidationError, match="same continuation state"):
        CursorPage[int](items=[1], next_cursor=None, has_more=True)
    with pytest.raises(ValidationError, match="same continuation state"):
        CursorPage[int](items=[1], next_cursor="next", has_more=False)


def test_newest_first_page_continues_after_its_last_returned_resource() -> None:
    codec = CursorCodec()
    resources = [
        _Created(id=UUID(f"50000000-0000-0000-0000-00000000000{index}"), created_at=created_at)
        for index, created_at in enumerate(
            (CREATED_AT, CREATED_AT, CREATED_AT - timedelta(seconds=1)), start=1
        )
    ]

    page = newest_first_page(codec, resources, limit=2, resource="run_exports:fixture")
    position = decode_creation_position(codec, page.next_cursor, resource="run_exports:fixture")

    assert page.items == resources[:2]
    assert page.has_more is True
    assert position == CreationPosition(created_at=CREATED_AT, id=resources[1].id)


def test_newest_first_page_without_an_extra_row_is_the_last_page() -> None:
    resource = _Created(id=RESOURCE_ID, created_at=CREATED_AT)

    page = newest_first_page(CursorCodec(), [resource], limit=1, resource="run_exports:fixture")

    assert page == CursorPage(items=[resource], next_cursor=None, has_more=False)


def test_creation_position_is_absent_for_a_first_page() -> None:
    assert decode_creation_position(CursorCodec(), None, resource="run_exports:fixture") is None


@pytest.mark.parametrize("sort_value", ["yesterday", "2026-09-22T10:00:00"])
def test_creation_position_rejects_an_unusable_creation_time(sort_value: str) -> None:
    codec = CursorCodec()
    cursor = codec.encode(
        resource="run_exports:fixture",
        sort_values=(sort_value,),
        resource_id=RESOURCE_ID,
    )

    with pytest.raises(InvalidCursorError, match="creation time is invalid"):
        decode_creation_position(codec, cursor, resource="run_exports:fixture")


def test_creation_position_rejects_a_cursor_from_another_collection() -> None:
    codec = CursorCodec()
    cursor = codec.encode(
        resource="run_exports:first",
        sort_values=(CREATED_AT.isoformat(),),
        resource_id=RESOURCE_ID,
    )

    with pytest.raises(InvalidCursorError, match="different resource"):
        decode_creation_position(codec, cursor, resource="run_exports:second")
