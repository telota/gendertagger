"""Application repository contract for runs, executions, batches, and predictions."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.lifecycle import (
    MethodExecutionStatus,
    RunStatus,
    TaskBatchStatus,
)
from gendertagger.models.run import (
    MethodExecution,
    MethodExecutionCreate,
    Prediction,
    PredictionWrite,
    Run,
    RunCreate,
    TaskBatch,
    TaskBatchCreate,
    TaskBatchPlan,
)


class RunRepository(Protocol):
    """Persist canonical execution resources without owning the transaction."""

    def add_run(self, command: RunCreate) -> Run:
        """Persist a created run targeting one ready snapshot."""
        ...

    def get_run(self, run_id: UUID) -> Run | None:
        """Return a run by ID, or ``None`` when absent."""
        ...

    def add_method_execution(self, command: MethodExecutionCreate) -> MethodExecution:
        """Persist one configured method execution within its run."""
        ...

    def get_method_execution(self, method_execution_id: UUID) -> MethodExecution | None:
        """Return a method execution by ID, or ``None`` when absent."""
        ...

    def add_task_batch(self, command: TaskBatchCreate) -> TaskBatch:
        """Persist one retryable task batch for a method execution."""
        ...

    def get_task_batch(self, task_batch_id: UUID) -> TaskBatch | None:
        """Return a task batch by ID, or ``None`` when absent."""
        ...

    def create_task_batches(
        self,
        method_execution_id: UUID,
        plans: Sequence[TaskBatchPlan],
    ) -> list[TaskBatch]:
        """Idempotently persist a planned batch set for a method execution."""
        ...

    def mark_run_queued(self, run_id: UUID) -> Run:
        """Transition a created run to queued."""
        ...

    def mark_run_started(self, run_id: UUID, *, started_at: datetime) -> Run:
        """Transition a queued run to running."""
        ...

    def mark_run_finished(
        self,
        run_id: UUID,
        *,
        status: RunStatus,
        finished_at: datetime,
        failure_diagnostic: str | None = None,
    ) -> Run:
        """Transition a running run to a terminal outcome."""
        ...

    def mark_execution_queued(self, method_execution_id: UUID) -> MethodExecution:
        """Transition a pending method execution to queued."""
        ...

    def mark_execution_started(
        self, method_execution_id: UUID, *, started_at: datetime
    ) -> MethodExecution:
        """Transition a queued method execution to running."""
        ...

    def mark_execution_finished(
        self,
        method_execution_id: UUID,
        *,
        status: MethodExecutionStatus,
        finished_at: datetime,
        failure_class: str | None = None,
        failure_diagnostic: str | None = None,
    ) -> MethodExecution:
        """Transition a running method execution to a terminal outcome."""
        ...

    def mark_batch_started(
        self,
        task_batch_id: UUID,
        *,
        worker_task_id: str,
        started_at: datetime,
        attempt_count: int,
    ) -> TaskBatch:
        """Claim a not-yet-completed batch for one worker attempt."""
        ...

    def mark_batch_finished(
        self,
        task_batch_id: UUID,
        *,
        status: TaskBatchStatus,
        finished_at: datetime,
        success_count: int = 0,
        abstain_count: int = 0,
        error_count: int = 0,
        failure_class: str | None = None,
        failure_diagnostic: str | None = None,
    ) -> TaskBatch:
        """Transition a running batch to a terminal outcome with its tallies."""
        ...

    def add_predictions(
        self,
        method_execution_id: UUID,
        predictions: Sequence[PredictionWrite],
    ) -> int:
        """Persist one bounded immutable prediction batch and return its count."""
        ...

    def get_prediction(self, prediction_id: UUID) -> Prediction | None:
        """Return a prediction by ID, or ``None`` when absent."""
        ...
