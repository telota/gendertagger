"""Application use case for filtered human-review candidate lists."""

from typing import cast

from pydantic import JsonValue

from gendertagger.models.api import CursorPage
from gendertagger.models.common import canonical_json_sha256
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.models.review import ReviewItem, ReviewItemQuery
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.unit_of_work import UnitOfWorkFactory


class ReviewItemService:
    """Query one completed aggregation through explicit server-side filters."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        cursor_codec: CursorCodec,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._cursor_codec = cursor_codec

    def list_review_items(self, query: ReviewItemQuery) -> CursorPage[ReviewItem]:
        """Return one filter-scoped opaque-cursor page in stable TEI-ID order."""
        with self._unit_of_work_factory() as unit_of_work:
            aggregation = unit_of_work.aggregations.get_aggregation(query.aggregation_id)
        if aggregation is None:
            msg = f"aggregation execution {query.aggregation_id} does not exist"
            raise ResourceNotFoundError(msg)
        if aggregation.status is not AggregationExecutionStatus.completed:
            msg = f"aggregation execution {query.aggregation_id} is not completed"
            raise InvalidResourceStateError(msg)

        filter_payload = cast(
            JsonValue,
            query.model_dump(mode="json", exclude={"cursor", "limit"}),
        )
        filter_sha256 = canonical_json_sha256(filter_payload)
        resource = f"review_items:{query.aggregation_id}:{filter_sha256}"
        position = (
            self._cursor_codec.decode(query.cursor, expected_resource=resource)
            if query.cursor is not None
            else None
        )
        with self._unit_of_work_factory() as unit_of_work:
            review_items = unit_of_work.reviews.list_review_items(
                query,
                limit=query.limit + 1,
                after_tei_id=position.sort_value if position is not None else None,
                after_person_record_id=position.id if position is not None else None,
            )
        has_more = len(review_items) > query.limit
        items = list(review_items[: query.limit])
        next_cursor = None
        if has_more:
            last_item = items[-1]
            next_cursor = self._cursor_codec.encode(
                resource=resource,
                sort_value=last_item.tei_id,
                resource_id=last_item.person_record_id,
            )
        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)
