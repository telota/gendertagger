"""Versioned, resource-scoped opaque cursor encoding."""

import base64
import binascii
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gendertagger.models.api import CursorPage
from gendertagger.models.common import canonical_json_sha256

_MAX_CURSOR_LENGTH = 2048
_MAX_SORT_VALUES = 8


class InvalidCursorError(ValueError):
    """Raised when a cursor is malformed or belongs to another resource."""


def filtered_collection_resource(resource: str, filters: BaseModel) -> str:
    """Bind a collection cursor to all filters, preserving the unfiltered scope."""
    values = filters.model_dump(mode="json")
    if all(value is None for value in values.values()):
        return resource
    return f"{resource}:{canonical_json_sha256(values)}"


@dataclass(frozen=True, slots=True)
class CursorPosition:
    """Decoded stable sort values and UUID tie-breaker."""

    sort_values: tuple[str, ...]
    id: UUID


class _CursorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[2] = 2
    resource: str = Field(min_length=1, max_length=200)
    sort_values: tuple[Annotated[str, Field(max_length=1000)], ...] = Field(
        min_length=1,
        max_length=_MAX_SORT_VALUES,
    )
    id: UUID


class CursorCodec:
    """Encode validated positions without treating cursors as authorization."""

    def encode(
        self,
        *,
        resource: str,
        sort_values: Sequence[str],
        resource_id: UUID,
    ) -> str:
        """Return compact base64url JSON for one continuation position.

        Args:
            resource: Exact collection scope, including the filters and sort
                order that produced the position.
            sort_values: Ordered sort-key values of the last returned item,
                excluding its UUID tie-breaker.
            resource_id: UUID tie-breaker of the last returned item.

        Returns:
            An opaque unpadded base64url cursor.
        """
        payload = _CursorPayload(
            resource=resource,
            sort_values=tuple(sort_values),
            id=resource_id,
        ).model_dump_json()
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

    def decode(
        self,
        cursor: str,
        *,
        expected_resource: str,
        expected_sort_value_count: int = 1,
    ) -> CursorPosition:
        """Validate one cursor and require its exact collection scope and arity.

        Args:
            cursor: Opaque cursor supplied by the client.
            expected_resource: Collection scope the caller is paginating.
            expected_sort_value_count: Number of sort-key values the caller's
                keyset predicate consumes.

        Returns:
            The decoded continuation position.

        Raises:
            InvalidCursorError: If the cursor is malformed, belongs to another
                collection scope, or carries a different number of sort values.
        """
        if not cursor or len(cursor) > _MAX_CURSOR_LENGTH:
            raise InvalidCursorError("cursor length is invalid")
        try:
            padding = "=" * (-len(cursor) % 4)
            payload_bytes = base64.b64decode(
                f"{cursor}{padding}",
                altchars=b"-_",
                validate=True,
            )
            payload = _CursorPayload.model_validate_json(payload_bytes)
        except (binascii.Error, ValidationError, ValueError) as error:
            raise InvalidCursorError("cursor payload is invalid") from error
        if payload.resource != expected_resource:
            raise InvalidCursorError("cursor belongs to a different resource")
        if len(payload.sort_values) != expected_sort_value_count:
            raise InvalidCursorError("cursor carries an unexpected sort-value count")
        return CursorPosition(sort_values=payload.sort_values, id=payload.id)


@dataclass(frozen=True, slots=True)
class CreationPosition:
    """Keyset position in a newest-first collection.

    Attributes:
        created_at: Creation time of the last returned resource.
        id: UUID of the last returned resource, which orders resources created at the same time.
    """

    created_at: datetime
    id: UUID


class _CreatedResource(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def created_at(self) -> datetime: ...


_CreatedResourceT = TypeVar("_CreatedResourceT", bound=_CreatedResource)


def decode_creation_position(
    codec: CursorCodec,
    cursor: str | None,
    *,
    resource: str,
) -> CreationPosition | None:
    """Return the position a newest-first cursor continues after, or ``None`` for a first page.

    Raises:
        InvalidCursorError: If the cursor is malformed, belongs to another collection, or does
            not carry a timezone-aware creation time.
    """
    if cursor is None:
        return None
    position = codec.decode(cursor, expected_resource=resource)
    try:
        created_at = datetime.fromisoformat(position.sort_values[0])
    except ValueError as error:
        raise InvalidCursorError("cursor creation time is invalid") from error
    if created_at.tzinfo is None:
        raise InvalidCursorError("cursor creation time is invalid")
    return CreationPosition(created_at=created_at, id=position.id)


def newest_first_page(
    codec: CursorCodec,
    resources: Sequence[_CreatedResourceT],
    *,
    limit: int,
    resource: str,
) -> "CursorPage[_CreatedResourceT]":
    """Return one page of a newest-first slice that was fetched with ``limit + 1`` rows.

    The extra row only signals that another page exists; the cursor continues after the last
    returned resource. The return annotation is quoted because parametrizing the Pydantic
    generic at import time would make Pydantic build a schema for the Protocol bound.
    """
    has_more = len(resources) > limit
    items = list(resources[:limit])
    next_cursor = None
    if has_more:
        last_item = items[-1]
        next_cursor = codec.encode(
            resource=resource,
            sort_values=(last_item.created_at.isoformat(),),
            resource_id=last_item.id,
        )
    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)
