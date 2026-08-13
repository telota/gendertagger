"""Application repository contract for append-only human review."""

from typing import Protocol
from uuid import UUID

from gendertagger.models.review import Annotation, AnnotationCreate, ReviewState


class ReviewRepository(Protocol):
    """Persist annotation history and its rebuildable concurrency projection."""

    def add_annotation(
        self,
        command: AnnotationCreate,
        *,
        reviewer_user_id: UUID,
        aggregated_result_id: UUID | None = None,
    ) -> Annotation:
        """Append one annotation when the expected review revision is current."""
        ...

    def get_annotation(self, annotation_id: UUID) -> Annotation | None:
        """Return an annotation by ID, or ``None`` when absent."""
        ...

    def get_review_state(self, snapshot_id: UUID, tei_id: str) -> ReviewState | None:
        """Return the current review projection, or ``None`` for an absent person."""
        ...
