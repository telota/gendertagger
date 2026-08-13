"""Application repository contract for runs, executions, batches, and predictions."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from gendertagger.models.run import (
    MethodExecution,
    MethodExecutionCreate,
    Prediction,
    PredictionWrite,
    Run,
    RunCreate,
    TaskBatch,
    TaskBatchCreate,
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
