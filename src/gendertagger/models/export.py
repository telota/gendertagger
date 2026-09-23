"""Canonical contracts for versioned TEI/JSON/CSV result exports."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.common import UtcDatetime
from gendertagger.models.lifecycle import ExportExecutionStatus
from gendertagger.models.project import SHA256_PATTERN, SourceFormat, SourcePackaging

_TEI_CERT_VALUES = ("high", "low", "unknown")


class ExportFormat(StrEnum):
    """Supported result-export encodings."""

    tei = "tei"
    json = "json"
    csv = "csv"


class LabelSourcePolicy(StrEnum):
    """Which final-decision label an export projects for each person."""

    machine_aggregation = "machine_aggregation"
    human_overrides = "human_overrides"


class TeiExportProfile(StrEnum):
    """Versioned TEI export encoding for the ``<gender>`` annotation."""

    tei_p5_gender_v1 = "tei_p5_gender_v1"


class ExportCreateRequest(BaseModel):
    """Public command selecting one completed aggregation and export shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    aggregation_execution_id: UUID
    format: ExportFormat
    label_source_policy: LabelSourcePolicy = LabelSourcePolicy.machine_aggregation
    tei_profile: TeiExportProfile | None = None
    human_resp_id: str = Field(default="#editor", pattern=r"^#\S+$", max_length=200)

    @model_validator(mode="after")
    def _validate_tei_profile_scope(self) -> Self:
        if self.format is not ExportFormat.tei and self.tei_profile is not None:
            msg = "tei_profile is only valid when format='tei'"
            raise ValueError(msg)
        return self


class ExportTaskMessage(BaseModel):
    """Small validated envelope requesting one persisted export execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    export_execution_id: UUID


class ExportExecutionCreate(BaseModel):
    """Validated export command bound to one run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    aggregation_execution_id: UUID
    format: ExportFormat
    label_source_policy: LabelSourcePolicy = LabelSourcePolicy.machine_aggregation
    tei_profile: TeiExportProfile | None = None
    human_resp_id: str = Field(default="#editor", pattern=r"^#\S+$", max_length=200)

    @model_validator(mode="after")
    def _validate_tei_profile_scope(self) -> Self:
        if self.format is ExportFormat.tei:
            if self.tei_profile is None:
                msg = "format='tei' requires a resolved tei_profile"
                raise ValueError(msg)
        elif self.tei_profile is not None:
            msg = "tei_profile is only valid when format='tei'"
            raise ValueError(msg)
        return self


class ExportExecution(ExportExecutionCreate):
    """Canonical read model for one independently rerunnable export."""

    id: UUID
    status: ExportExecutionStatus
    manifest_artifact_id: UUID | None = None
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    failure_class: str | None = None
    failure_diagnostic: str | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_lifecycle_fields(self) -> Self:
        terminal_statuses = {
            ExportExecutionStatus.completed,
            ExportExecutionStatus.failed,
            ExportExecutionStatus.cancelled,
        }
        if self.status in terminal_statuses:
            if self.finished_at is None:
                msg = "a terminal export requires finished_at"
                raise ValueError(msg)
        elif self.finished_at is not None:
            msg = "a non-terminal export must not have finished_at"
            raise ValueError(msg)
        if (
            self.status in {ExportExecutionStatus.running, ExportExecutionStatus.completed}
            and self.started_at is None
        ):
            msg = "a running or completed export requires started_at"
            raise ValueError(msg)
        if self.status is ExportExecutionStatus.completed:
            if self.manifest_artifact_id is None:
                msg = "a completed export requires a manifest artifact"
                raise ValueError(msg)
        elif self.manifest_artifact_id is not None:
            msg = "only a completed export may have a manifest artifact"
            raise ValueError(msg)
        if self.status is ExportExecutionStatus.failed:
            if self.failure_diagnostic is None or not self.failure_diagnostic.strip():
                msg = "a failed export requires a failure diagnostic"
                raise ValueError(msg)
        elif self.failure_class is not None or self.failure_diagnostic is not None:
            msg = "only a failed export may have failure details"
            raise ValueError(msg)
        return self


class ExportPersonRecord(BaseModel):
    """One person's projected final-decision label and TEI certainty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tei_id: str = Field(min_length=1)
    person_record_id: UUID
    source_member_name: str | None = None
    label: CanonicalLabel | None
    evidence: str | None = None
    resp: str | None = None
    cert: str | None = None
    agreement_tier: AgreementTier
    certainty_tier: CertaintyTier
    is_human_reviewed: bool

    @model_validator(mode="after")
    def _validate_label_evidence_consistency(self) -> Self:
        if self.label is None:
            if self.evidence is not None or self.resp is not None or self.cert is not None:
                msg = "a person without a final label must not have evidence, resp, or cert"
                raise ValueError(msg)
            return self
        if self.evidence != "assigned" or not self.resp or self.cert not in _TEI_CERT_VALUES:
            msg = "a person with a final label requires evidence, resp, and a valid cert"
            raise ValueError(msg)
        return self


class ExportManifestOutput(BaseModel):
    """Checksummed descriptor for one produced export output artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    logical_name: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=255)


class ExportManifest(BaseModel):
    """Provenance record persisted alongside every export's output artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    export_execution_id: UUID
    dataset_snapshot_id: UUID
    source_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    run_id: UUID
    aggregation_execution_id: UUID
    format: ExportFormat
    label_source_policy: LabelSourcePolicy
    tei_profile: TeiExportProfile | None = None
    outputs: tuple[ExportManifestOutput, ...] = Field(min_length=1)
    generated_at: UtcDatetime


class ExportSourceMember(BaseModel):
    """One ordered exact source member available for TEI re-export."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    logical_name: str = Field(min_length=1, max_length=1024)
    artifact_id: UUID
    media_type: str = Field(min_length=1, max_length=255)


class ExportInputs(BaseModel):
    """Loaded evidence for one running export, ready for pure computation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_snapshot_id: UUID
    source_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    source_format: SourceFormat
    packaging: SourcePackaging
    records: tuple[ExportPersonRecord, ...]
    source_members: tuple[ExportSourceMember, ...] = ()
