from uuid import UUID

import pytest
from pydantic import ValidationError

from gendertagger.models.api import CursorPage
from gendertagger.services.pagination import CursorCodec, InvalidCursorError

RESOURCE_ID = UUID("40000000-0000-0000-0000-000000000001")


def test_cursor_round_trip_preserves_resource_scoped_position() -> None:
    codec = CursorCodec()

    cursor = codec.encode(
        resource="snapshot_people:fixture",
        sort_value="person-17",
        resource_id=RESOURCE_ID,
    )
    position = codec.decode(cursor, expected_resource="snapshot_people:fixture")

    assert "=" not in cursor
    assert position.sort_value == "person-17"
    assert position.id == RESOURCE_ID


def test_cursor_rejects_malformed_and_cross_resource_tokens() -> None:
    codec = CursorCodec()
    cursor = codec.encode(
        resource="snapshot_people:first",
        sort_value="person-17",
        resource_id=RESOURCE_ID,
    )

    with pytest.raises(InvalidCursorError, match="invalid"):
        codec.decode("not+a+base64url+cursor", expected_resource="snapshot_people:first")
    with pytest.raises(InvalidCursorError, match="different resource"):
        codec.decode(cursor, expected_resource="snapshot_people:second")


def test_cursor_page_requires_consistent_continuation_state() -> None:
    assert CursorPage[int](items=[1], next_cursor=None, has_more=False).items == [1]

    with pytest.raises(ValidationError, match="same continuation state"):
        CursorPage[int](items=[1], next_cursor=None, has_more=True)
    with pytest.raises(ValidationError, match="same continuation state"):
        CursorPage[int](items=[1], next_cursor="next", has_more=False)
