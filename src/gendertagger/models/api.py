"""Canonical transport-wide API support contracts."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue

API_ERROR_CODE_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"


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
