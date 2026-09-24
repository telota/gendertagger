"""Canonical team and direct-team-membership contracts (ADR-0041 slice 1)."""

import re
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from gendertagger.models.common import UtcDatetime

TEAM_SLUG_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
TEAM_SLUG_MAX_LENGTH = 100
_TEAM_SLUG_RE = re.compile(TEAM_SLUG_PATTERN)


def normalize_team_slug(value: str) -> str:
    """Return the canonical stored team slug for a user-supplied identifier."""
    normalized = value.strip().lower()
    if len(normalized) > TEAM_SLUG_MAX_LENGTH or not _TEAM_SLUG_RE.fullmatch(normalized):
        msg = "team slug must be 1-100 lowercase letters, digits, and single hyphens"
        raise ValueError(msg)
    return normalized


class TeamCreate(BaseModel):
    """Global-administrator command creating one direct-membership team."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(max_length=TEAM_SLUG_MAX_LENGTH)
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("slug")
    @classmethod
    def _normalize_slug(cls, value: str) -> str:
        return normalize_team_slug(value)

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        if not value.strip():
            msg = "display_name must not be blank"
            raise ValueError(msg)
        return value


class TeamUpdate(BaseModel):
    """Global-administrator patch for a team's mutable display name only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str | SkipJsonSchema[None] = Field(default=None, max_length=200)

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            msg = "display_name must not be blank"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        if "display_name" in self.model_fields_set and self.display_name is None:
            msg = "display_name must not be null"
            raise ValueError(msg)
        return self


class TeamSummary(BaseModel):
    """Stable, roster-free representation of one direct-membership team."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    slug: str = Field(pattern=TEAM_SLUG_PATTERN, max_length=TEAM_SLUG_MAX_LENGTH)
    display_name: str = Field(min_length=1, max_length=200)
    created_at: UtcDatetime
    updated_at: UtcDatetime


class TeamMember(BaseModel):
    """Administrator-visible direct membership in one team."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    team_id: UUID
    user_id: UUID
    display_name: str = Field(min_length=1, max_length=200)
    is_active: bool
    created_at: UtcDatetime


class TeamMemberAdd(BaseModel):
    """Global-administrator command adding one active account to a team."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
