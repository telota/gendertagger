"""Canonical run, execution, batch, and persisted-prediction contracts."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from gendertagger.config.run import RunConfig
from gendertagger.models.classification import PredictionResult
from gendertagger.models.common import UtcDatetime, canonical_json_sha256
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus
from gendertagger.models.method import METHOD_NAME_PATTERN, MethodDescriptor
from gendertagger.models.project import SHA256_PATTERN

QUEUE_NAME_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"


class RunCreate(BaseModel):
    """Validated configuration and provenance used to create a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_snapshot_id: UUID
    resolved_config: RunConfig
    code_git_commit: str = Field(min_length=1, max_length=100)
    application_version: str = Field(min_length=1, max_length=100)
    container_image_digest: str | None = None
    python_version: str = Field(min_length=1, max_length=100)
    dependency_lock_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    dependency_lock_artifact_id: UUID | None = None

    @field_validator("code_git_commit", "application_version", "python_version")
    @classmethod
    def _validate_nonblank_provenance(cls, value: str) -> str:
        if not value.strip():
            msg = "run provenance values must not be blank"
            raise ValueError(msg)
        return value


class Run(RunCreate):
    """Canonical read model for one reproducible run lifecycle."""

    id: UUID
    status: RunStatus
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    failure_diagnostic: str | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_lifecycle_fields(self) -> Self:
        terminal_statuses = {
            RunStatus.completed,
            RunStatus.completed_with_errors,
            RunStatus.failed,
            RunStatus.cancelled,
        }
        if self.status in terminal_statuses:
            if self.finished_at is None:
                msg = "a terminal run requires finished_at"
                raise ValueError(msg)
        elif self.finished_at is not None:
            msg = "a non-terminal run must not have finished_at"
            raise ValueError(msg)

        if self.status in {RunStatus.running, RunStatus.completed, RunStatus.completed_with_errors}:
            if self.started_at is None:
                msg = "a running or completed run requires started_at"
                raise ValueError(msg)
        elif self.status in {RunStatus.created, RunStatus.queued} and self.started_at is not None:
            msg = "a run that has not started must not have started_at"
            raise ValueError(msg)

        if self.status is RunStatus.failed:
            if self.failure_diagnostic is None or not self.failure_diagnostic.strip():
                msg = "a failed run requires a failure diagnostic"
                raise ValueError(msg)
        elif self.failure_diagnostic is not None:
            msg = "only a failed run may have a failure diagnostic"
            raise ValueError(msg)
        return self


class MethodExecutionCreate(BaseModel):
    """Validated method provenance used to create one run execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    descriptor: MethodDescriptor
    resolved_config: dict[str, JsonValue] = Field(default_factory=dict)
    queue_name: str = Field(pattern=QUEUE_NAME_PATTERN, max_length=100)
    model_identifier: str | None = None
    model_revision: str | None = None
    model_checksum: str | None = Field(default=None, pattern=SHA256_PATTERN)
    model_artifact_id: UUID | None = None
    data_artifact_id: UUID | None = None
    prompt_version: str | None = Field(default=None, max_length=100)
    schema_version: str | None = Field(default=None, max_length=100)
    worker_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    total_count: int | None = Field(default=None, ge=0)

    def config_sha256(self) -> str:
        """Return the canonical hash of the resolved adapter configuration."""
        return canonical_json_sha256(self.resolved_config)


class MethodExecution(BaseModel):
    """Canonical read model for one persisted method execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    run_id: UUID
    method_name: str = Field(pattern=METHOD_NAME_PATTERN)
    implementation_version: str
    normalization_version: str
    resolved_config: dict[str, JsonValue]
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    status: MethodExecutionStatus
    queue_name: str = Field(pattern=QUEUE_NAME_PATTERN)
    model_identifier: str | None = None
    model_revision: str | None = None
    model_checksum: str | None = Field(default=None, pattern=SHA256_PATTERN)
    model_artifact_id: UUID | None = None
    data_artifact_id: UUID | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    worker_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    total_count: int | None = Field(default=None, ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    failure_class: str | None = None
    failure_diagnostic: str | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_progress(self) -> Self:
        if (
            self.total_count is not None
            and self.completed_count + self.failed_count > self.total_count
        ):
            msg = "execution progress must not exceed total_count"
            raise ValueError(msg)
        return self


class TaskBatchCreate(BaseModel):
    """Validated identity and routing used to create a retryable task batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_execution_id: UUID
    batch_index: int = Field(ge=0)
    queue_name: str = Field(pattern=QUEUE_NAME_PATTERN, max_length=100)


class TaskBatch(TaskBatchCreate):
    """Canonical read model for one persisted task batch."""

    id: UUID
    status: TaskBatchStatus
    worker_task_id: str | None = None
    attempt_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    abstain_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    failure_class: str | None = None
    failure_diagnostic: str | None = None
    created_at: UtcDatetime


class PredictionWrite(BaseModel):
    """Validated immutable method output prepared for persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    person_record_id: UUID
    task_batch_id: UUID | None = None
    input_fingerprint: str = Field(pattern=SHA256_PATTERN)
    result: PredictionResult


class Prediction(PredictionResult):
    """Canonical read model for one immutable persisted prediction."""

    id: UUID
    method_execution_id: UUID
    person_record_id: UUID
    task_batch_id: UUID | None = None
    input_fingerprint: str = Field(pattern=SHA256_PATTERN)
    created_at: UtcDatetime
