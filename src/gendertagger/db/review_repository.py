"""SQLAlchemy repository for append-only annotations and review state."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gendertagger.db.aggregations import AggregatedResultRow
from gendertagger.db.projects import PersonRecordRow
from gendertagger.db.reviews import AnnotationRow, ReviewStateRow, UserRow
from gendertagger.models.review import (
    Annotation,
    AnnotationCreate,
    ReviewAction,
    ReviewState,
    ReviewWorkflowState,
)
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
    ReviewConflictError,
)


class SqlAlchemyReviewRepository:
    """Append review history and update its projection in one caller transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_annotation(
        self,
        command: AnnotationCreate,
        *,
        reviewer_user_id: UUID,
    ) -> Annotation:
        """Lock one person stream, compare revision, append, and advance its head."""
        person = self._session.scalar(
            select(PersonRecordRow)
            .where(
                PersonRecordRow.dataset_snapshot_id == command.snapshot_id,
                PersonRecordRow.tei_id == command.tei_id,
            )
            .with_for_update()
        )
        if person is None:
            msg = f"person {command.tei_id!r} does not exist in snapshot {command.snapshot_id}"
            raise ResourceNotFoundError(msg)

        reviewer = self._session.get(UserRow, reviewer_user_id)
        if reviewer is None:
            msg = f"reviewer user {reviewer_user_id} does not exist"
            raise ResourceNotFoundError(msg)
        if not reviewer.is_active:
            msg = f"reviewer user {reviewer_user_id} is inactive"
            raise InvalidResourceStateError(msg)

        if command.aggregated_result_id is not None:
            aggregated_result = self._session.get(
                AggregatedResultRow,
                command.aggregated_result_id,
            )
            if aggregated_result is None:
                msg = f"aggregated result {command.aggregated_result_id} does not exist"
                raise ResourceNotFoundError(msg)
            if aggregated_result.person_record_id != person.id:
                msg = "referenced aggregated result belongs to a different person"
                raise InvalidResourceStateError(msg)

        state = self._session.scalar(
            select(ReviewStateRow)
            .where(
                ReviewStateRow.dataset_snapshot_id == command.snapshot_id,
                ReviewStateRow.person_record_id == person.id,
            )
            .with_for_update()
        )
        if state is None:
            state = ReviewStateRow(
                dataset_snapshot_id=command.snapshot_id,
                person_record_id=person.id,
                revision=0,
                current_annotation_id=None,
                workflow_state=ReviewWorkflowState.unreviewed,
            )
            self._session.add(state)
            self._session.flush()

        if state.revision != command.expected_revision:
            raise ReviewConflictError(
                expected_revision=command.expected_revision,
                current_revision=state.revision,
            )

        annotation = AnnotationRow(
            dataset_snapshot_id=command.snapshot_id,
            person_record_id=person.id,
            action=command.action,
            label=command.label,
            reviewer_user_id=reviewer_user_id,
            comment=command.comment,
            aggregated_result_id=command.aggregated_result_id,
            supersedes_annotation_id=state.current_annotation_id,
            resulting_revision=state.revision + 1,
        )
        self._session.add(annotation)
        self._session.flush()

        state.revision = annotation.resulting_revision
        state.current_annotation_id = annotation.id
        state.workflow_state = (
            ReviewWorkflowState.deferred
            if command.action is ReviewAction.defer
            else ReviewWorkflowState.reviewed
        )
        self._session.flush()
        return self._annotation_from_row(annotation, person.tei_id)

    def get_annotation(self, annotation_id: UUID) -> Annotation | None:
        """Return one immutable annotation without exposing its row."""
        row = self._session.get(AnnotationRow, annotation_id)
        if row is None:
            return None
        tei_id = self._session.scalar(
            select(PersonRecordRow.tei_id).where(PersonRecordRow.id == row.person_record_id)
        )
        if tei_id is None:
            msg = f"annotation {annotation_id} references a missing person"
            raise ResourceNotFoundError(msg)
        return self._annotation_from_row(row, tei_id)

    def get_review_state(self, snapshot_id: UUID, tei_id: str) -> ReviewState | None:
        """Return persisted state or a derived unreviewed state for an existing person."""
        person = self._session.scalar(
            select(PersonRecordRow).where(
                PersonRecordRow.dataset_snapshot_id == snapshot_id,
                PersonRecordRow.tei_id == tei_id,
            )
        )
        if person is None:
            return None
        state = self._session.get(ReviewStateRow, (snapshot_id, person.id))
        if state is None:
            return ReviewState(
                snapshot_id=snapshot_id,
                person_record_id=person.id,
                tei_id=tei_id,
                revision=0,
                workflow_state=ReviewWorkflowState.unreviewed,
                current_annotation_id=None,
            )
        return ReviewState(
            snapshot_id=snapshot_id,
            person_record_id=person.id,
            tei_id=tei_id,
            revision=state.revision,
            workflow_state=state.workflow_state,
            current_annotation_id=state.current_annotation_id,
        )

    @staticmethod
    def _annotation_from_row(row: AnnotationRow, tei_id: str) -> Annotation:
        return Annotation(
            id=row.id,
            snapshot_id=row.dataset_snapshot_id,
            person_record_id=row.person_record_id,
            tei_id=tei_id,
            action=row.action,
            label=row.label,
            reviewer_user_id=row.reviewer_user_id,
            comment=row.comment,
            aggregated_result_id=row.aggregated_result_id,
            supersedes_annotation_id=row.supersedes_annotation_id,
            resulting_revision=row.resulting_revision,
            created_at=row.created_at,
        )
