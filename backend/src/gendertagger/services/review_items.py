"""Application use cases for filtered human-review candidate lists and their counts."""

from typing import cast
from uuid import UUID

from pydantic import JsonValue

from gendertagger.domain.review_triage import review_triage_rank
from gendertagger.models.api import CursorPage
from gendertagger.models.common import canonical_json_sha256
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.models.review import ReviewItem, ReviewItemQuery, ReviewItemSort, ReviewSummary
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.review_repository import ReviewItemCursor
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory


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
        """Return one filter- and sort-scoped opaque-cursor page.

        The cursor scope covers every filter and the requested sort, so a cursor
        minted under one review query is never continued under another.
        """
        self._require_completed_aggregation(query.aggregation_id)
        filter_payload = cast(
            JsonValue,
            query.model_dump(mode="json", exclude={"cursor", "limit"}),
        )
        filter_sha256 = canonical_json_sha256(filter_payload)
        resource = f"review_items:{query.aggregation_id}:{filter_sha256}"
        sorts_by_uncertainty = query.sort is ReviewItemSort.uncertainty
        after = (
            self._decode_position(
                query.cursor,
                resource=resource,
                sorts_by_uncertainty=sorts_by_uncertainty,
            )
            if query.cursor is not None
            else None
        )
        with self._unit_of_work_factory() as unit_of_work:
            review_items = unit_of_work.reviews.list_review_items(
                query,
                limit=query.limit + 1,
                after=after,
            )
        has_more = len(review_items) > query.limit
        items = list(review_items[: query.limit])
        next_cursor = None
        if has_more:
            last_item = items[-1]
            sort_values = (
                (str(self._triage_rank(last_item)), last_item.tei_id)
                if sorts_by_uncertainty
                else (last_item.tei_id,)
            )
            next_cursor = self._cursor_codec.encode(
                resource=resource,
                sort_values=sort_values,
                resource_id=last_item.person_record_id,
            )
        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    def summarize_review(self, aggregation_id: UUID) -> ReviewSummary:
        """Return a completed aggregation's result counts by tier, label, action, and state."""
        self._require_completed_aggregation(aggregation_id)
        with self._unit_of_work_factory() as unit_of_work:
            data = unit_of_work.reviews.count_review_groups(aggregation_id)
        return ReviewSummary(
            aggregation_execution_id=aggregation_id,
            result_count=sum(group.result_count for group in data.groups),
            last_annotated_at=data.last_annotated_at,
            groups=list(data.groups),
        )

    def _require_completed_aggregation(self, aggregation_id: UUID) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            aggregation = unit_of_work.aggregations.get_aggregation(aggregation_id)
        if aggregation is None:
            msg = f"aggregation execution {aggregation_id} does not exist"
            raise ResourceNotFoundError(msg)
        if aggregation.status is not AggregationExecutionStatus.completed:
            msg = f"aggregation execution {aggregation_id} is not completed"
            raise InvalidResourceStateError(msg)

    def _decode_position(
        self,
        cursor: str,
        *,
        resource: str,
        sorts_by_uncertainty: bool,
    ) -> ReviewItemCursor:
        position = self._cursor_codec.decode(
            cursor,
            expected_resource=resource,
            expected_sort_value_count=2 if sorts_by_uncertainty else 1,
        )
        if not sorts_by_uncertainty:
            return ReviewItemCursor(
                tei_id=position.sort_values[0],
                person_record_id=position.id,
            )
        try:
            triage_rank = int(position.sort_values[0])
        except ValueError as error:
            raise InvalidCursorError("review cursor triage rank is invalid") from error
        return ReviewItemCursor(
            tei_id=position.sort_values[1],
            person_record_id=position.id,
            triage_rank=triage_rank,
        )

    @staticmethod
    def _triage_rank(item: ReviewItem) -> int:
        return review_triage_rank(
            certainty_tier=item.certainty_tier,
            has_authority_conflict=item.has_authority_conflict,
            has_prediction_error=item.has_prediction_error,
        )
