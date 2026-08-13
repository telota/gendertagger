"""Application use case for append-only human annotations."""

from uuid import UUID

from gendertagger.models.review import Annotation, AnnotationCreate
from gendertagger.services.unit_of_work import UnitOfWorkFactory


class AnnotationService:
    """Append auditable review decisions under optimistic concurrency."""

    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def create_annotation(
        self,
        command: AnnotationCreate,
        *,
        reviewer_user_id: UUID,
    ) -> Annotation:
        """Append one immutable annotation and advance its review projection."""
        with self._unit_of_work_factory() as unit_of_work:
            annotation = unit_of_work.reviews.add_annotation(
                command,
                reviewer_user_id=reviewer_user_id,
            )
            unit_of_work.commit()
        return annotation
