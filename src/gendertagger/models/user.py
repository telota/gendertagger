"""Canonical authenticated-user contracts."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gendertagger.models.common import UtcDatetime


class GlobalRole(StrEnum):
    """Hierarchical authorization role that applies outside any one project (ADR-0033).

    ``operator`` may create projects and grants no access to existing ones. ``admin`` additionally
    holds operator capability in every project and administers project memberships.
    """

    operator = "operator"
    admin = "admin"

    def grants(self, required: Self) -> bool:
        """Return whether this role includes every capability of ``required``."""
        ranking = tuple(GlobalRole)
        return ranking.index(self) >= ranking.index(required)


class ProjectRole(StrEnum):
    """Hierarchical authorization role a user holds within one project (ADR-0033).

    ``viewer`` reads the project, ``reviewer`` also appends annotations, and ``operator`` also
    imports snapshots and creates runs, aggregations, evaluations, and exports.
    """

    viewer = "viewer"
    reviewer = "reviewer"
    operator = "operator"

    def grants(self, required: Self) -> bool:
        """Return whether this role includes every capability of ``required``."""
        ranking = tuple(ProjectRole)
        return ranking.index(self) >= ranking.index(required)


class CurrentUser(BaseModel):
    """Authenticated principal exposed at the public API boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    display_name: str = Field(min_length=1, max_length=200)
    roles: set[GlobalRole]

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        if not value.strip():
            msg = "display_name must not be blank"
            raise ValueError(msg)
        return value


class UserCreate(BaseModel):
    """Provider-neutral values used to create an attributable user."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(min_length=1, max_length=200)
    roles: set[GlobalRole] = Field(default_factory=set)
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
