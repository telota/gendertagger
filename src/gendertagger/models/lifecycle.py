"""Canonical lifecycle state contracts for persisted resources."""

from enum import StrEnum


class DatasetSnapshotStatus(StrEnum):
    """Import lifecycle for one immutable dataset snapshot."""

    pending = "pending"
    importing = "importing"
    ready = "ready"
    failed = "failed"


class RunStatus(StrEnum):
    """Lifecycle for one reproducible run."""

    created = "created"
    queued = "queued"
    running = "running"
    completed = "completed"
    completed_with_errors = "completed_with_errors"
    failed = "failed"
    cancelled = "cancelled"


class MethodExecutionStatus(StrEnum):
    """Lifecycle for one method execution within a run."""

    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    completed_with_errors = "completed_with_errors"
    failed = "failed"
    cancelled = "cancelled"


class AggregationExecutionStatus(StrEnum):
    """Lifecycle for one independently rerunnable aggregation."""

    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class EvaluationExecutionStatus(StrEnum):
    """Lifecycle for one independently rerunnable evaluation."""

    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ExportExecutionStatus(StrEnum):
    """Lifecycle for one independently rerunnable export."""

    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TaskBatchStatus(StrEnum):
    """Lifecycle for one retryable method-execution batch."""

    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
