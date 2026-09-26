"""Canonical run, execution, batch, and persisted-prediction contracts."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from gendertagger.config.run import RunConfig
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.common import UtcDatetime, canonical_json_sha256
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus
from gendertagger.models.method import METHOD_NAME_PATTERN, MethodDescriptor
from gendertagger.models.project import SHA256_PATTERN

QUEUE_NAME_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
METHOD_EXECUTION_FAILURE_CLASS = "MethodExecutionFailure"
"""``failure_class`` of a run failed because a method execution failed, rather than by an exception.

Recorded when ``fail_run_on_optional_method_error`` is set and at least one execution failed; per-method
exception classes stay on the method executions and their batches.
"""


class RunListFilter(BaseModel):
    """Filter runs by completed aggregation existence, independent of run status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_completed_aggregations: bool | None = None


class MethodExecutionResultState(StrEnum):
    """Visible outcome state for one snapshot person in one method execution.

    ``missing`` means that the execution has not persisted a prediction for the
    person. It is deliberately separate from a method-level ``abstain`` or
    ``error`` prediction.
    """

    missing = "missing"
    success = "success"
    abstain = "abstain"
    error = "error"


class MethodExecutionPredictionSummary(BaseModel):
    """Bounded public summary of one persisted method prediction.

    The collection deliberately excludes raw output and normalization metadata.
    They remain immutable persisted evidence and can be exposed by a focused
    detail resource when the product needs an audit view.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: CanonicalLabel | None
    status: PredictionStatus
    method_confidence: float | None = Field(default=None, allow_inf_nan=False)
    raw_label: str | None = None

    @model_validator(mode="after")
    def _validate_status_label(self) -> Self:
        if self.status is PredictionStatus.success and self.label is None:
            msg = "a successful prediction requires a canonical label"
            raise ValueError(msg)
        if (
            self.status in {PredictionStatus.abstain, PredictionStatus.error}
            and self.label is not None
        ):
            msg = "an abstained or failed prediction must not have a label"
            raise ValueError(msg)
        return self


class MethodExecutionResult(BaseModel):
    """One person's bounded method-result projection for an execution.

    The collection contains every person in the execution's immutable snapshot.
    A null ``prediction`` makes an unpersisted output visible, rather than
    silently omitting it from a partially completed or failed execution.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_execution_id: UUID
    dataset_snapshot_id: UUID
    person_record_id: UUID
    tei_id: str = Field(min_length=1)
    surname: str | None = None
    forenames: list[str] = Field(default_factory=list)
    result_state: MethodExecutionResultState
    prediction_id: UUID | None = None
    prediction: MethodExecutionPredictionSummary | None = None

    @model_validator(mode="after")
    def _validate_prediction_projection(self) -> Self:
        if self.prediction is None:
            if self.prediction_id is not None:
                msg = "a missing prediction must not have a prediction ID"
                raise ValueError(msg)
            if self.result_state is not MethodExecutionResultState.missing:
                msg = "a missing prediction requires the missing result state"
                raise ValueError(msg)
            return self
        if self.prediction_id is None:
            msg = "a persisted prediction requires a prediction ID"
            raise ValueError(msg)
        if self.result_state.value != self.prediction.status.value:
            msg = "the result state must match the persisted prediction status"
            raise ValueError(msg)
        return self


class MethodExecutionResultFilter(BaseModel):
    """Server-side filters for one method execution's per-person result list."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    q: str | None = Field(default=None, min_length=1, max_length=200)
    result_state: MethodExecutionResultState | None = None
    label: CanonicalLabel | None = None

    @field_validator("q")
    @classmethod
    def _normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            msg = "q must not be blank"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _validate_label_filter(self) -> Self:
        if self.label is not None and self.result_state not in {
            None,
            MethodExecutionResultState.success,
        }:
            msg = "a label filter requires successful results or no result-state filter"
            raise ValueError(msg)
        return self


class MethodExecutionResultQuery(MethodExecutionResultFilter):
    """Filters and opaque-cursor controls for a method execution result collection."""

    limit: int = Field(default=100, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)

    def collection_filter(self) -> MethodExecutionResultFilter:
        """Return only the values that scope a continuation cursor."""
        return MethodExecutionResultFilter(
            q=self.q,
            result_state=self.result_state,
            label=self.label,
        )


class Progress(BaseModel):
    """Derived completion counts for a run or method execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: int | None = Field(default=None, ge=0)
    completed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    percentage: float | None = Field(default=None, ge=0, le=100)

    @classmethod
    def of(cls, *, total: int | None, completed: int, failed: int) -> Self:
        """Build progress from counts, deriving the completion percentage."""
        percentage = round((completed + failed) / total * 100, 2) if total else None
        return cls(total=total, completed=completed, failed=failed, percentage=percentage)


class RunCreateRequest(BaseModel):
    """Public command selecting one snapshot and raw run configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_snapshot_id: UUID
    config: RunConfig


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
    failure_class: str | None = Field(default=None, max_length=255)
    failure_diagnostic: str | None = None
    created_at: UtcDatetime
    progress: Progress

    @model_validator(mode="after")
    def _validate_lifecycle_fields(self) -> Self:
        terminal_statuses = {
            RunStatus.completed,
            RunStatus.completed_with_errors,
            RunStatus.failed,
            RunStatus.cancelled,
        }
        if self.status is not RunStatus.failed and self.failure_class is not None:
            msg = "only a failed run may have a failure class"
            raise ValueError(msg)
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


class MethodExecutionSummary(BaseModel):
    """Public read model for one method execution, free of queue internals.

    Operational routing and worker provenance are deliberately absent: clients
    of ``/api/v1`` never see queue names or worker identities. ``MethodExecution``
    adds those internal fields for services, repositories, and workers.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    run_id: UUID
    method_name: str = Field(pattern=METHOD_NAME_PATTERN)
    implementation_version: str
    normalization_version: str
    resolved_config: dict[str, JsonValue]
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    status: MethodExecutionStatus
    model_identifier: str | None = None
    model_revision: str | None = None
    model_checksum: str | None = Field(default=None, pattern=SHA256_PATTERN)
    model_artifact_id: UUID | None = None
    data_artifact_id: UUID | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    total_count: int | None = Field(default=None, ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    failure_class: str | None = None
    failure_diagnostic: str | None = None
    created_at: UtcDatetime
    progress: Progress

    @model_validator(mode="after")
    def _validate_progress(self) -> Self:
        if (
            self.total_count is not None
            and self.completed_count + self.failed_count > self.total_count
        ):
            msg = "execution progress must not exceed total_count"
            raise ValueError(msg)
        return self


class MethodExecution(MethodExecutionSummary):
    """Canonical internal read model adding routing and worker provenance."""

    queue_name: str = Field(pattern=QUEUE_NAME_PATTERN)
    worker_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class TaskBatchPlan(BaseModel):
    """Deterministic person slice covered by one planned task batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_index: int = Field(ge=0)
    record_offset: int = Field(ge=0)
    record_count: int = Field(ge=1)


class TaskBatchCreate(BaseModel):
    """Validated identity and routing used to create a retryable task batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_execution_id: UUID
    batch_index: int = Field(ge=0)
    queue_name: str = Field(pattern=QUEUE_NAME_PATTERN, max_length=100)
    record_offset: int = Field(ge=0)
    record_count: int = Field(ge=1)


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


class TaskBatchMessage(BaseModel):
    """Small validated Celery envelope identifying one batch to execute.

    Task messages carry only identifiers, never person data or predictions.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_execution_id: UUID
    task_batch_id: UUID


class PredictionWrite(BaseModel):
    """Validated immutable method output prepared for persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    person_record_id: UUID
    task_batch_id: UUID
    input_fingerprint: str = Field(pattern=SHA256_PATTERN)
    result: PredictionResult


class Prediction(PredictionResult):
    """Canonical read model for one immutable persisted prediction."""

    id: UUID
    method_execution_id: UUID
    person_record_id: UUID
    task_batch_id: UUID
    input_fingerprint: str = Field(pattern=SHA256_PATTERN)
    created_at: UtcDatetime


class RunStateEvent(BaseModel):
    """SSE payload projecting one run's current lifecycle state and progress."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    status: RunStatus
    progress: Progress


class MethodExecutionStateEvent(BaseModel):
    """SSE payload projecting one method execution's state and progress."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_execution_id: UUID
    method_name: str = Field(pattern=METHOD_NAME_PATTERN)
    status: MethodExecutionStatus
    progress: Progress
