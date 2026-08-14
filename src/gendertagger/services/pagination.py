"""Versioned, resource-scoped opaque cursor encoding."""

import base64
import binascii
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_MAX_CURSOR_LENGTH = 2048
_MAX_SORT_VALUES = 8


class InvalidCursorError(ValueError):
    """Raised when a cursor is malformed or belongs to another resource."""


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
