"""Canonical checksummed artifact record contracts."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from gendertagger.models.common import UtcDatetime
from gendertagger.models.method import METHOD_NAME_PATTERN
from gendertagger.models.project import (
    SHA256_PATTERN,
    SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH,
    normalize_source_member_logical_name,
)

ARTIFACT_TYPE_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"

SQLITE_MEDIA_TYPE = "application/vnd.sqlite3"
MODEL_MANIFEST_MEDIA_TYPE = "application/vnd.gendertagger.model-manifest+json"


class LookupSourceArtifactReference(BaseModel):
    """Content identity of one retained source used to compile a lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: UUID
    sha256: str = Field(pattern=SHA256_PATTERN)


class LookupArtifactMetadata(BaseModel):
    """Canonical provenance for one compiled method lookup artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_name: str = Field(pattern=METHOD_NAME_PATTERN)
    lookup_schema_version: str = Field(min_length=1, max_length=100)
    compiler_version: str = Field(min_length=1, max_length=100)
    source_artifacts: tuple[LookupSourceArtifactReference, ...] = Field(min_length=1)
    source_version: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=2_000)
    license_identifier: str | None = Field(default=None, max_length=200)
    sqlite_version: str = Field(min_length=1, max_length=100)
    record_count: int = Field(ge=0)

    @field_validator(
        "lookup_schema_version",
        "compiler_version",
        "source_version",
        "source_url",
        "license_identifier",
        "sqlite_version",
    )
    @classmethod
    def _validate_nonblank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            msg = "lookup artifact text metadata must not be blank"
            raise ValueError(msg)
        return value


class ArtifactCreate(BaseModel):
    """Validated metadata used to register immutable externally stored bytes.

    ``storage_uri`` is an internal application locator and must not be exposed by
    public API response models.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    logical_type: str = Field(pattern=ARTIFACT_TYPE_PATTERN, max_length=100)
    storage_uri: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=255)
    project_id: UUID | None = None
    dataset_snapshot_id: UUID | None = None
    run_id: UUID | None = None
    method_execution_id: UUID | None = None
    aggregation_execution_id: UUID | None = None
    evaluation_execution_id: UUID | None = None
    export_execution_id: UUID | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("storage_uri", "media_type")
    @classmethod
    def _validate_nonblank_value(cls, value: str) -> str:
        if not value.strip():
            msg = "artifact storage_uri and media_type must not be blank"
            raise ValueError(msg)
        return value


class Artifact(ArtifactCreate):
    """Canonical application read model for an immutable artifact record."""

    id: UUID
    created_at: UtcDatetime


class ModelManifestMember(BaseModel):
    """Checksummed descriptor for one ordered file materializing a model artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str = Field(min_length=1, max_length=SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH)
    artifact_id: UUID
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(ge=0)

    @field_validator("relative_path")
    @classmethod
    def _normalize_relative_path(cls, value: str) -> str:
        return normalize_source_member_logical_name(value)


class ModelManifestMetadata(BaseModel):
    """Canonical provenance for one compiled multi-file model manifest artifact.

    Plays the same structural role for directory-shaped native model formats
    (Hugging Face transformer weights, HIVOTO-XGBoost's vectorizer and booster)
    that :class:`LookupArtifactMetadata` plays for compiled SQLite lookups. See
    ADR-0023 and ADR-0024.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_name: str = Field(pattern=METHOD_NAME_PATTERN)
    model_schema_version: str = Field(min_length=1, max_length=100)
    compiler_version: str = Field(min_length=1, max_length=100)
    source_identifier: str = Field(min_length=1, max_length=200)
    source_revision: str = Field(min_length=1, max_length=200)
    members: tuple[ModelManifestMember, ...] = Field(min_length=1)
    license_identifier: str | None = Field(default=None, max_length=200)

    @field_validator(
        "model_schema_version",
        "compiler_version",
        "source_identifier",
        "source_revision",
        "license_identifier",
    )
    @classmethod
    def _validate_nonblank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            msg = "model manifest text metadata must not be blank"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_unique_relative_paths(self) -> Self:
        relative_paths = [member.relative_path.casefold() for member in self.members]
        if len(relative_paths) != len(set(relative_paths)):
            msg = "model manifest member relative_path values must be unique"
            raise ValueError(msg)
        return self
