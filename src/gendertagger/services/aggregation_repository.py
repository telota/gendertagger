"""Application repository contract for aggregation executions and results."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationPersonPredictions,
    AggregationResultWrite,
)
from gendertagger.models.lifecycle import AggregationExecutionStatus


class AggregationRepository(Protocol):
    """Persist canonical aggregation resources without owning the transaction."""

    def add_aggregation(self, command: AggregationExecutionCreate) -> AggregationExecution:
        """Persist an aggregation over an exact ordered execution selection."""
        ...

    def get_aggregation(self, aggregation_execution_id: UUID) -> AggregationExecution | None:
        """Return an aggregation execution by ID, or ``None`` when absent."""
        ...

    def mark_aggregation_queued(
        self,
        aggregation_execution_id: UUID,
    ) -> AggregationExecution:
        """Atomically transition a pending aggregation with durable intent to queued."""
        ...

    def claim_aggregation(
        self,
        aggregation_execution_id: UUID,
        *,
        started_at: datetime,
    ) -> AggregationExecution | None:
        """Atomically claim a pending or queued aggregation.

        Return ``None`` when another delivery has already claimed or terminally
        finished the aggregation.
        """
        ...

    def load_prediction_matrix(
        self,
        aggregation_execution_id: UUID,
    ) -> Sequence[AggregationPersonPredictions]:
        """Load every snapshot person and its present selected predictions."""
        ...

    def add_results(
        self,
        aggregation_execution_id: UUID,
        results: Sequence[AggregationResultWrite],
    ) -> int:
        """Persist one immutable result batch while the aggregation is running."""
        ...

    def mark_aggregation_finished(
        self,
        aggregation_execution_id: UUID,
        *,
        status: AggregationExecutionStatus,
        finished_at: datetime,
        failure_class: str | None = None,
        failure_diagnostic: str | None = None,
    ) -> AggregationExecution:
        """Finish a running aggregation with a complete result set or diagnostic."""
        ...

    def get_result(self, aggregated_result_id: UUID) -> AggregatedResult | None:
        """Return an aggregated result by ID, or ``None`` when absent."""
        ...

    def list_results(
        self,
        aggregation_execution_id: UUID,
        *,
        limit: int,
        after_person_record_id: UUID | None = None,
        after_result_id: UUID | None = None,
    ) -> Sequence[AggregatedResult]:
        """Return one stable ``(person_record_id, id)`` keyset slice."""
        ...
