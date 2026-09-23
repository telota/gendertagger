"""Canonical transport-wide API support contracts."""

from typing import Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

API_ERROR_CODE_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
T = TypeVar("T")


class ApiErrorDetail(BaseModel):
    """Stable client-facing failure information for one HTTP request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=API_ERROR_CODE_PATTERN)
    message: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)
    request_id: str | None = None


class ApiErrorEnvelope(BaseModel):
    """Uniform public wrapper for every API failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ApiErrorDetail


class CursorPage(BaseModel, Generic[T]):
    """Opaque-cursor page for a stable server-ordered resource collection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[T]
    next_cursor: str | None = Field(default=None, min_length=1)
    has_more: bool

    @model_validator(mode="after")
    def _validate_cursor_consistency(self) -> Self:
        if self.has_more != (self.next_cursor is not None):
            msg = "has_more and next_cursor must describe the same continuation state"
            raise ValueError(msg)
        return self
