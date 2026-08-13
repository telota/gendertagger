"""Canonical authenticated-user contracts."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gendertagger.models.common import UtcDatetime


class Role(StrEnum):
    """Global v1 authorization role assigned to a user."""

    viewer = "viewer"
    reviewer = "reviewer"
    operator = "operator"
    admin = "admin"


class UserCreate(BaseModel):
    """Provider-neutral values used to create an attributable user."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(min_length=1, max_length=200)
    roles: set[Role] = Field(default_factory=set)
    is_active: bool = True

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        if not value.strip():
            msg = "display_name must not be blank"
            raise ValueError(msg)
        return value


class User(UserCreate):
    """Canonical read model for one provider-neutral persisted user."""

    id: UUID
    created_at: UtcDatetime
    updated_at: UtcDatetime
