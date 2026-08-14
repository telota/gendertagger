"""Canonical checksummed artifact record contracts."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from gendertagger.models.common import UtcDatetime
from gendertagger.models.method import METHOD_NAME_PATTERN
from gendertagger.models.project import SHA256_PATTERN

ARTIFACT_TYPE_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"

SQLITE_MEDIA_TYPE = "application/vnd.sqlite3"


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
