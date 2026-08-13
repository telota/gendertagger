"""Application use cases for independently rerunnable aggregations."""

from uuid import UUID

from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationCreateRequest,
    AggregationExecution,
    AggregationExecutionCreate,
)
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.unit_of_work import UnitOfWorkFactory


class AggregationService:
    """Persist pending aggregation commands and read immutable outputs."""

    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def create_aggregation(
        self,
        *,
        run_id: UUID,
        command: AggregationCreateRequest,
    ) -> AggregationExecution:
        """Persist one pending aggregation over exact completed executions."""
        with self._unit_of_work_factory() as unit_of_work:
            aggregation = unit_of_work.aggregations.add_aggregation(
                AggregationExecutionCreate(
                    run_id=run_id,
                    strategy=command.strategy,
                    resolved_config={},
                    method_execution_ids=command.method_execution_ids,
                )
            )
            unit_of_work.commit()
        return aggregation

    def get_aggregation(self, aggregation_id: UUID) -> AggregationExecution:
        """Return one aggregation execution or raise a not-found failure."""
        with self._unit_of_work_factory() as unit_of_work:
            aggregation = unit_of_work.aggregations.get_aggregation(aggregation_id)
        if aggregation is None:
            msg = f"aggregation execution {aggregation_id} does not exist"
            raise ResourceNotFoundError(msg)
        return aggregation

    def get_result(self, *, aggregation_id: UUID, result_id: UUID) -> AggregatedResult:
        """Return one immutable result only under its owning aggregation."""
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.aggregations.get_result(result_id)
        if result is None or result.aggregation_execution_id != aggregation_id:
            msg = f"aggregation result {result_id} does not exist under {aggregation_id}"
            raise ResourceNotFoundError(msg)
        return result
