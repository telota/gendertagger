"""Canonical project and dataset-snapshot resource contracts."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from gendertagger.models.common import UtcDatetime
from gendertagger.models.lifecycle import DatasetSnapshotStatus

SHA256_PATTERN = r"^[0-9a-f]{64}$"
PROJECT_SLUG_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"


class ProjectCreate(BaseModel):
    """Validated values used to create a long-lived editorial project."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(pattern=PROJECT_SLUG_PATTERN, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    description: str | None = None

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        if not value.strip():
            msg = "display_name must not be blank"
            raise ValueError(msg)
        return value


class Project(ProjectCreate):
    """Canonical read model for a persisted project."""

    id: UUID
    created_at: UtcDatetime


class DatasetSnapshotCreate(BaseModel):
    """Validated immutable import identity used to create a pending snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    source_artifact_id: UUID
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    parser_version: str = Field(min_length=1, max_length=100)
    import_config: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("parser_version")
    @classmethod
    def _validate_parser_version(cls, value: str) -> str:
        if not value.strip():
            msg = "parser_version must not be blank"
            raise ValueError(msg)
        return value


class DatasetSnapshot(DatasetSnapshotCreate):
    """Canonical read model for one imported snapshot lifecycle."""

    id: UUID
    status: DatasetSnapshotStatus
    record_count: int | None = Field(default=None, ge=0)
    ready_at: UtcDatetime | None = None
    failure_diagnostic: str | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_lifecycle_fields(self) -> Self:
        if self.status is DatasetSnapshotStatus.ready:
            if self.record_count is None or self.ready_at is None:
                msg = "a ready snapshot requires record_count and ready_at"
                raise ValueError(msg)
            if self.failure_diagnostic is not None:
                msg = "a ready snapshot must not have a failure diagnostic"
                raise ValueError(msg)
            return self

        if self.ready_at is not None:
            msg = "only a ready snapshot may have ready_at"
            raise ValueError(msg)
        if self.status is DatasetSnapshotStatus.failed:
            if self.failure_diagnostic is None or not self.failure_diagnostic.strip():
                msg = "a failed snapshot requires a failure diagnostic"
                raise ValueError(msg)
        elif self.failure_diagnostic is not None:
            msg = "only a failed snapshot may have a failure diagnostic"
            raise ValueError(msg)
        if self.record_count is not None:
            msg = "only a ready snapshot may have record_count"
            raise ValueError(msg)
        return self
