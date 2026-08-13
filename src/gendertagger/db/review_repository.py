"""SQLAlchemy repository for append-only annotations and review state."""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from gendertagger.db.aggregations import (
    AggregatedResultRow,
    AggregationMethodExecutionRow,
)
from gendertagger.db.executions import MethodExecutionRow, PredictionRow
from gendertagger.db.projects import PersonExternalIdRow, PersonRecordRow
from gendertagger.db.reviews import AnnotationRow, ReviewStateRow, UserRow
from gendertagger.models.classification import CanonicalLabel, PredictionStatus
from gendertagger.models.review import (
    Annotation,
    AnnotationCreate,
    ReviewAction,
    ReviewItem,
    ReviewItemQuery,
    ReviewMethodResult,
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

    def list_review_items(
        self,
        query: ReviewItemQuery,
        *,
        limit: int,
        after_tei_id: str | None = None,
        after_person_record_id: UUID | None = None,
    ) -> Sequence[ReviewItem]:
        """Project and filter review summaries in stable TEI-ID order."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        if (after_tei_id is None) != (after_person_record_id is None):
            msg = "review cursor fields must be supplied together"
            raise ValueError(msg)

        selected_membership = aliased(AggregationMethodExecutionRow)
        selected_execution = aliased(MethodExecutionRow)
        selected_prediction = aliased(PredictionRow)
        selected_execution_id = (
            select(selected_execution.id)
            .join(
                selected_membership,
                selected_membership.method_execution_id == selected_execution.id,
            )
            .where(
                selected_membership.aggregation_execution_id == query.aggregation_id,
                selected_execution.method_name == query.method_name,
            )
            .scalar_subquery()
        )

        error_membership = aliased(AggregationMethodExecutionRow)
        error_prediction = aliased(PredictionRow)
        has_prediction_error = exists(
            select(1)
            .select_from(error_membership)
            .join(
                error_prediction,
                error_prediction.method_execution_id == error_membership.method_execution_id,
            )
            .where(
                error_membership.aggregation_execution_id == query.aggregation_id,
                error_prediction.person_record_id == PersonRecordRow.id,
                error_prediction.status == PredictionStatus.error,
            )
        )
        has_authority_conflict = and_(
            AggregatedResultRow.override_source.is_not(None),
            AggregatedResultRow.override_comparison_count > 0,
            AggregatedResultRow.override_agreeing_count
            < AggregatedResultRow.override_comparison_count,
        )
        final_label = case(
            (
                AnnotationRow.action.in_((ReviewAction.verify, ReviewAction.correct)),
                AnnotationRow.label,
            ),
            else_=AggregatedResultRow.label,
        )

        statement = (
            select(
                PersonRecordRow,
                AggregatedResultRow,
                ReviewStateRow.revision,
                ReviewStateRow.workflow_state,
                ReviewStateRow.current_annotation_id,
                AnnotationRow.action,
                AnnotationRow.label,
                has_prediction_error.label("has_prediction_error"),
                selected_prediction,
            )
            .join(
                AggregatedResultRow,
                AggregatedResultRow.person_record_id == PersonRecordRow.id,
            )
            .outerjoin(
                ReviewStateRow,
                and_(
                    ReviewStateRow.dataset_snapshot_id == PersonRecordRow.dataset_snapshot_id,
                    ReviewStateRow.person_record_id == PersonRecordRow.id,
                ),
            )
            .outerjoin(
                AnnotationRow,
                AnnotationRow.id == ReviewStateRow.current_annotation_id,
            )
            .outerjoin(
                selected_prediction,
                and_(
                    selected_prediction.method_execution_id == selected_execution_id,
                    selected_prediction.person_record_id == PersonRecordRow.id,
                ),
            )
            .where(AggregatedResultRow.aggregation_execution_id == query.aggregation_id)
        )

        if query.final_label is not None:
            statement = statement.where(final_label == query.final_label)
        if query.certainty_tier is not None:
            statement = statement.where(AggregatedResultRow.certainty_tier == query.certainty_tier)
        if query.agreement_tier is not None:
            statement = statement.where(AggregatedResultRow.agreement_tier == query.agreement_tier)
        if query.workflow_state is ReviewWorkflowState.unreviewed:
            statement = statement.where(
                or_(
                    ReviewStateRow.workflow_state.is_(None),
                    ReviewStateRow.workflow_state == ReviewWorkflowState.unreviewed,
                )
            )
        elif query.workflow_state is not None:
            statement = statement.where(ReviewStateRow.workflow_state == query.workflow_state)
        if query.has_authority_conflict is not None:
            statement = statement.where(has_authority_conflict.is_(query.has_authority_conflict))
        if query.has_prediction_error is not None:
            statement = statement.where(has_prediction_error.is_(query.has_prediction_error))
        if query.method_name is not None:
            statement = statement.where(selected_prediction.id.is_not(None))
            if query.method_label is not None:
                statement = statement.where(selected_prediction.label == query.method_label)
            if query.prediction_status is not None:
                statement = statement.where(selected_prediction.status == query.prediction_status)
        if query.q is not None:
            pattern = self._contains_pattern(query.q)
            external_id_match = exists(
                select(1).where(
                    PersonExternalIdRow.person_record_id == PersonRecordRow.id,
                    PersonExternalIdRow.value.ilike(pattern, escape="\\"),
                )
            )
            statement = statement.where(
                or_(
                    PersonRecordRow.tei_id.ilike(pattern, escape="\\"),
                    PersonRecordRow.surname.ilike(pattern, escape="\\"),
                    func.array_to_string(PersonRecordRow.forenames, " ").ilike(
                        pattern,
                        escape="\\",
                    ),
                    func.array_to_string(PersonRecordRow.alt_names, " ").ilike(
                        pattern,
                        escape="\\",
                    ),
                    external_id_match,
                )
            )
        if after_tei_id is not None and after_person_record_id is not None:
            statement = statement.where(
                or_(
                    PersonRecordRow.tei_id > after_tei_id,
                    and_(
                        PersonRecordRow.tei_id == after_tei_id,
                        PersonRecordRow.id > after_person_record_id,
                    ),
                )
            )
        rows = self._session.execute(
            statement.order_by(PersonRecordRow.tei_id, PersonRecordRow.id).limit(limit)
        )
        items: list[ReviewItem] = []
        for row in rows:
            person = cast(PersonRecordRow, row[0])
            result = cast(AggregatedResultRow, row[1])
            revision = cast(int | None, row[2])
            workflow_state = cast(ReviewWorkflowState | None, row[3])
            current_annotation_id = cast(UUID | None, row[4])
            annotation_action = cast(ReviewAction | None, row[5])
            annotation_label = cast(CanonicalLabel | None, row[6])
            prediction_error = cast(bool, row[7])
            selected_prediction_row = cast(PredictionRow | None, row[8])
            final_label_value = (
                annotation_label
                if annotation_action in {ReviewAction.verify, ReviewAction.correct}
                else result.label
            )
            selected_method_result = None
            if query.method_name is not None and selected_prediction_row is not None:
                selected_method_result = ReviewMethodResult(
                    method_name=query.method_name,
                    status=selected_prediction_row.status,
                    label=selected_prediction_row.label,
                )
            items.append(
                ReviewItem(
                    aggregation_execution_id=result.aggregation_execution_id,
                    aggregated_result_id=result.id,
                    snapshot_id=person.dataset_snapshot_id,
                    person_record_id=person.id,
                    tei_id=person.tei_id,
                    surname=person.surname,
                    forenames=person.forenames,
                    aggregation_outcome=result.outcome,
                    machine_label=result.label,
                    final_label=final_label_value,
                    agreement_tier=result.agreement_tier,
                    certainty_tier=result.certainty_tier,
                    override_source=result.override_source,
                    has_authority_conflict=self._has_authority_conflict(result),
                    has_prediction_error=prediction_error,
                    workflow_state=workflow_state or ReviewWorkflowState.unreviewed,
                    review_revision=revision or 0,
                    current_annotation_id=current_annotation_id,
                    selected_method_result=selected_method_result,
                )
            )
        return tuple(items)

    @staticmethod
    def _contains_pattern(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @staticmethod
    def _has_authority_conflict(result: AggregatedResultRow) -> bool:
        agreeing_count = result.override_agreeing_count
        comparison_count = result.override_comparison_count
        return (
            result.override_source is not None
            and agreeing_count is not None
            and comparison_count is not None
            and comparison_count > 0
            and agreeing_count < comparison_count
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
