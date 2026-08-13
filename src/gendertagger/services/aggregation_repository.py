"""Application repository contract for aggregation executions and results."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationResultWrite,
)


class AggregationRepository(Protocol):
    """Persist canonical aggregation resources without owning the transaction."""

    def add_aggregation(self, command: AggregationExecutionCreate) -> AggregationExecution:
        """Persist an aggregation over an exact ordered execution selection."""
        ...

    def get_aggregation(self, aggregation_execution_id: UUID) -> AggregationExecution | None:
        """Return an aggregation execution by ID, or ``None`` when absent."""
        ...

    def add_results(
        self,
        aggregation_execution_id: UUID,
        results: Sequence[AggregationResultWrite],
    ) -> int:
        """Persist one bounded immutable result batch and return its count."""
        ...

    def get_result(self, aggregated_result_id: UUID) -> AggregatedResult | None:
        """Return an aggregated result by ID, or ``None`` when absent."""
        ...
