"""Versioned, resource-scoped opaque cursor encoding."""

import base64
import binascii
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_MAX_CURSOR_LENGTH = 2048


class InvalidCursorError(ValueError):
    """Raised when a cursor is malformed or belongs to another resource."""


@dataclass(frozen=True, slots=True)
class CursorPosition:
    """Decoded stable sort value and UUID tie-breaker."""

    sort_value: str
    id: UUID


class _CursorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    resource: str = Field(min_length=1, max_length=200)
    sort_value: str = Field(max_length=1000)
    id: UUID


class CursorCodec:
    """Encode validated positions without treating cursors as authorization."""

    def encode(self, *, resource: str, sort_value: str, resource_id: UUID) -> str:
        """Return compact base64url JSON for one continuation position."""
        payload = _CursorPayload(
            resource=resource,
            sort_value=sort_value,
            id=resource_id,
        ).model_dump_json()
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

    def decode(self, cursor: str, *, expected_resource: str) -> CursorPosition:
        """Validate one cursor and require its exact collection scope."""
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
        return CursorPosition(sort_value=payload.sort_value, id=payload.id)
