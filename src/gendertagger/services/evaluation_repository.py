"""Application repository contract for evaluation executions."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.evaluation import (
    EvaluationExecution,
    EvaluationExecutionCreate,
    EvaluationInputs,
)
from gendertagger.models.lifecycle import EvaluationExecutionStatus


class EvaluationRepository(Protocol):
    """Persist canonical evaluation resources without owning the transaction."""

    def add_evaluation(self, command: EvaluationExecutionCreate) -> EvaluationExecution:
        """Persist an evaluation over a locked run and exact completed selection."""
        ...

    def get_evaluation(self, evaluation_execution_id: UUID) -> EvaluationExecution | None:
        """Return an evaluation execution by ID, or ``None`` when absent."""
        ...

    def mark_evaluation_queued(self, evaluation_execution_id: UUID) -> EvaluationExecution:
        """Atomically transition a pending evaluation with durable intent to queued."""
        ...

    def claim_evaluation(
        self,
        evaluation_execution_id: UUID,
        *,
        started_at: datetime,
    ) -> EvaluationExecution | None:
        """Atomically claim a pending or queued evaluation.

        Return ``None`` when another delivery has already claimed or terminally
        finished the evaluation.
        """
        ...

    def load_evaluation_inputs(self, evaluation_execution_id: UUID) -> EvaluationInputs:
        """Load every snapshot person's selected predictions, plus optional ensemble evidence."""
        ...

    def mark_evaluation_finished(
        self,
        evaluation_execution_id: UUID,
        *,
        status: EvaluationExecutionStatus,
        finished_at: datetime,
        report_artifact_id: UUID | None = None,
        failure_class: str | None = None,
        failure_diagnostic: str | None = None,
    ) -> EvaluationExecution:
        """Finish a running evaluation with a persisted report or a diagnostic."""
        ...
