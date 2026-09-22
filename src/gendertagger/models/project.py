"""Canonical project and dataset-snapshot resource contracts."""

import json
import unicodedata
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from gendertagger.models.common import UtcDatetime
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.user import ProjectRole

SHA256_PATTERN = r"^[0-9a-f]{64}$"
PROJECT_SLUG_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH = 1024


class TeiImportProfile(StrEnum):
    """Supported TEI extraction profile persisted with a snapshot import."""

    tei_p5_person_register = "tei_p5_person_register"


class SourceFormat(StrEnum):
    """Semantic encoding of one snapshot source collection."""

    tei = "tei"
    csv = "csv"
    xlsx = "xlsx"
    json = "json"


class SourcePackaging(StrEnum):
    """Transport packaging used to deliver one snapshot source collection."""

    single = "single"
    loose = "loose"
    zip = "zip"
    tar_gz = "tar_gz"


class TabularImportProfile(StrEnum):
    """Versioned person-register extraction profile for tabular sources."""

    tei_equivalent_person_register_v1 = "tei_equivalent_person_register_v1"


DEFAULT_TEI_IMPORT_PROFILE = TeiImportProfile.tei_p5_person_register
DEFAULT_SOURCE_FORMAT = SourceFormat.tei
DEFAULT_SOURCE_PACKAGING = SourcePackaging.single

ImportProfile = TeiImportProfile | TabularImportProfile


def normalize_source_member_logical_name(value: str) -> str:
    """Return one safe, Unicode-normalized relative source-member name."""
    logical_name = unicodedata.normalize("NFC", value.strip())
    if not logical_name:
        msg = "source member logical_name must not be blank"
        raise ValueError(msg)
    if len(logical_name) > SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH:
        msg = (
            "source member logical_name must not exceed "
            f"{SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH} characters"
        )
        raise ValueError(msg)
    if "\\" in logical_name:
        msg = "source member logical_name must use forward slashes"
        raise ValueError(msg)
    if logical_name.startswith("/") or (logical_name[:1].isalpha() and logical_name[1:2] == ":"):
        msg = "source member logical_name must be relative"
        raise ValueError(msg)
    parts = logical_name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        msg = "source member logical_name contains an unsafe path segment"
        raise ValueError(msg)
    if any(unicodedata.category(character).startswith("C") for character in logical_name):
        msg = "source member logical_name contains a control character"
        raise ValueError(msg)
    return logical_name


class SourceManifestMember(BaseModel):
    """Checksummed descriptor for one ordered member of a source manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    logical_name: str = Field(min_length=1, max_length=SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH)
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=255)

    @field_validator("logical_name")
    @classmethod
    def _normalize_logical_name(cls, value: str) -> str:
        return normalize_source_member_logical_name(value)

    @field_validator("media_type")
    @classmethod
    def _validate_media_type(cls, value: str) -> str:
        if not value.strip():
            msg = "source member media_type must not be blank"
            raise ValueError(msg)
        return value


class SourceManifestV1(BaseModel):
    """Immutable ordered manifest of exact staged source members."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    source_format: SourceFormat
    packaging: SourcePackaging
    members: tuple[SourceManifestMember, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_logical_names(self) -> Self:
        if (
            self.source_format is not SourceFormat.tei
            and self.packaging is not SourcePackaging.single
        ):
            msg = "tabular source manifests require packaging='single'"
            raise ValueError(msg)
        if self.packaging is not SourcePackaging.loose and len(self.members) != 1:
            msg = "single-file and archive source manifests require exactly one container member"
            raise ValueError(msg)
        logical_names = [member.logical_name.casefold() for member in self.members]
        if len(logical_names) != len(set(logical_names)):
            msg = "source manifest member logical_name values must be unique"
            raise ValueError(msg)
        basenames = [PurePosixPath(member.logical_name).name.casefold() for member in self.members]
        if len(basenames) != len(set(basenames)):
            msg = "source manifest member basenames must be unique"
            raise ValueError(msg)
        return self

    def canonical_bytes(self) -> bytes:
        """Return deterministic UTF-8 JSON bytes for content addressing."""
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class SnapshotSourceMemberCreate(SourceManifestMember):
    """Validated source-member metadata attached to one pending snapshot."""

    artifact_id: UUID
    ordinal: int = Field(ge=0)


class SnapshotSourceMember(SnapshotSourceMemberCreate):
    """Canonical read model for one persisted snapshot source member."""

    id: UUID
    dataset_snapshot_id: UUID
    created_at: UtcDatetime


class SnapshotImportRequest(BaseModel):
    """Public multipart options for one source-preserving snapshot import."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_format: SourceFormat = DEFAULT_SOURCE_FORMAT
    packaging: SourcePackaging = DEFAULT_SOURCE_PACKAGING

    @model_validator(mode="after")
    def _validate_packaging_for_source(self) -> Self:
        if (
            self.packaging is not SourcePackaging.single
            and self.source_format is not SourceFormat.tei
        ):
            msg = "tabular imports require packaging='single'"
            raise ValueError(msg)
        return self


class SnapshotImportLimits(BaseModel):
    """Resolved immutable safety bounds applied by one snapshot import."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_member_count: int = Field(default=128, gt=0)
    max_member_expanded_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_total_expanded_bytes: int = Field(default=500 * 1024 * 1024, gt=0)
    max_compression_ratio: float = Field(default=100.0, gt=1.0, allow_inf_nan=False)
    max_record_count: int = Field(default=1_000_000, gt=0)
    max_cell_bytes: int = Field(default=1024 * 1024, gt=0)


class SnapshotImportConfig(SnapshotImportRequest):
    """Persisted import choices plus the exact resolved safety limits."""

    profile: ImportProfile
    limits: SnapshotImportLimits

    @model_validator(mode="after")
    def _validate_profile_for_source(self) -> Self:
        if self.source_format is SourceFormat.tei:
            if self.profile is not DEFAULT_TEI_IMPORT_PROFILE:
                msg = "TEI import provenance requires the supported TEI profile"
                raise ValueError(msg)
            return self
        if self.profile is not TabularImportProfile.tei_equivalent_person_register_v1:
            msg = "tabular import provenance requires the supported tabular profile"
            raise ValueError(msg)
        return self


def import_profile_for_source_format(source_format: SourceFormat) -> ImportProfile:
    """Return the sole supported profile for a public source format."""
    if source_format is SourceFormat.tei:
        return DEFAULT_TEI_IMPORT_PROFILE
    return TabularImportProfile.tei_equivalent_person_register_v1


class SnapshotImportTaskMessage(BaseModel):
    """Identifier-only envelope for one asynchronous snapshot import."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_snapshot_id: UUID


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
    working_aggregation_execution_id: UUID | None = Field(
        default=None,
        description=(
            "The completed AggregationExecution, from one of this project's own runs, that its "
            "review queue and dashboard currently summarize (ADR-0035). Set explicitly through "
            "PUT /projects/{project_id}/working-aggregation; never inferred from recency."
        ),
    )


class AccessibleProject(Project):
    """A project as its caller sees it, with the caller's effective role in it (ADR-0033)."""

    current_user_role: ProjectRole


class ProjectWorkingAggregationUpdate(BaseModel):
    """Command setting or clearing a project's working-aggregation pointer (ADR-0035)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    aggregation_execution_id: UUID | None = None


class ProjectMemberUpdate(BaseModel):
    """Administrative command granting or changing one user's role in a project."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: ProjectRole


class ProjectMember(BaseModel):
    """Canonical read model for one user's membership in a project (ADR-0033)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    user_id: UUID
    display_name: str = Field(min_length=1, max_length=200)
    role: ProjectRole
    created_at: UtcDatetime
    updated_at: UtcDatetime


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
