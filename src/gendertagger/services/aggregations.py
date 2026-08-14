"""Application use cases for independently rerunnable aggregations."""

from collections.abc import Callable
from uuid import UUID

from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationCreateRequest,
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationTaskMessage,
)
from gendertagger.models.api import CursorPage
from gendertagger.models.common import UtcDatetime
from gendertagger.models.dispatch import AggregationDispatchCreate
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.unit_of_work import UnitOfWorkFactory

Clock = Callable[[], UtcDatetime]


class AggregationService:
    """Persist durable aggregation commands and read immutable outputs."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        cursor_codec: CursorCodec,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._cursor_codec = cursor_codec
        self._clock = clock

    def create_aggregation(
        self,
        *,
        run_id: UUID,
        command: AggregationCreateRequest,
    ) -> AggregationExecution:
        """Persist one aggregation and its durable dispatch intent atomically."""
        with self._unit_of_work_factory() as unit_of_work:
            aggregation = unit_of_work.aggregations.add_aggregation(
                AggregationExecutionCreate(
                    run_id=run_id,
                    strategy=command.strategy,
                    resolved_config={},
                    method_execution_ids=command.method_execution_ids,
                )
            )
            unit_of_work.dispatches.ensure_dispatch(
                AggregationDispatchCreate(
                    aggregation_execution_id=aggregation.id,
                    queue_name=CPU_QUEUE,
                    payload=AggregationTaskMessage(
                        aggregation_execution_id=aggregation.id,
                    ),
                    available_at=self._clock(),
                )
            )
            aggregation = unit_of_work.aggregations.mark_aggregation_queued(aggregation.id)
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

    def list_results(
        self,
        aggregation_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[AggregatedResult]:
        """Return one stable opaque-cursor page of immutable results."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        self.get_aggregation(aggregation_id)
        resource = f"aggregation_results:{aggregation_id}"
        position = (
            self._cursor_codec.decode(cursor, expected_resource=resource)
            if cursor is not None
            else None
        )
        after_person_record_id = None
        if position is not None:
            try:
                after_person_record_id = UUID(position.sort_value)
            except ValueError as error:
                raise InvalidCursorError("result cursor sort value is invalid") from error
        with self._unit_of_work_factory() as unit_of_work:
            results = unit_of_work.aggregations.list_results(
                aggregation_id,
                limit=limit + 1,
                after_person_record_id=after_person_record_id,
                after_result_id=position.id if position is not None else None,
            )
        has_more = len(results) > limit
        items = list(results[:limit])
        next_cursor = None
        if has_more:
            last_item = items[-1]
            next_cursor = self._cursor_codec.encode(
                resource=resource,
                sort_value=str(last_item.person_record_id),
                resource_id=last_item.id,
            )
        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)
