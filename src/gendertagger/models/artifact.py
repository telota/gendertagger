"""Canonical checksummed artifact record contracts."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from gendertagger.models.common import UtcDatetime
from gendertagger.models.project import SHA256_PATTERN

ARTIFACT_TYPE_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"


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
