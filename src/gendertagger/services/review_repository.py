"""Application repository contract for append-only human review."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from gendertagger.models.review import (
    Annotation,
    AnnotationCreate,
    ReviewItem,
    ReviewItemQuery,
    ReviewState,
)


@dataclass(frozen=True, slots=True)
class ReviewItemCursor:
    """Keyset continuation position for one review-item ordering.

    ``triage_rank`` carries the ``review_triage_v1`` rank of the last returned
    item under uncertainty-first ordering, and is ``None`` for plain register
    ordering.
    """

    tei_id: str
    person_record_id: UUID
    triage_rank: int | None = None


class ReviewRepository(Protocol):
    """Persist annotation history and its rebuildable concurrency projection."""

    def add_annotation(
        self,
        command: AnnotationCreate,
        *,
        reviewer_user_id: UUID,
    ) -> Annotation:
        """Append one annotation when the expected review revision is current."""
        ...

    def get_annotation(self, annotation_id: UUID) -> Annotation | None:
        """Return an annotation by ID, or ``None`` when absent."""
        ...

    def get_review_state(self, snapshot_id: UUID, tei_id: str) -> ReviewState | None:
        """Return the current review projection, or ``None`` for an absent person."""
        ...

    def list_review_items(
        self,
        query: ReviewItemQuery,
        *,
        limit: int,
        after: ReviewItemCursor | None = None,
    ) -> Sequence[ReviewItem]:
        """Return one filtered slice in the stable order the query selected."""
        ...
