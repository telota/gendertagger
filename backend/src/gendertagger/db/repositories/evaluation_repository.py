"""SQLAlchemy repository for evaluation executions."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gendertagger.db.keyset import newest_first_slice
from gendertagger.db.rows.aggregations import AggregatedResultRow, AggregationExecutionRow
from gendertagger.db.rows.evaluations import EvaluationExecutionRow, EvaluationMethodExecutionRow
from gendertagger.db.rows.executions import MethodExecutionRow, PredictionRow, RunRow
from gendertagger.db.rows.projects import DatasetSnapshotRow, PersonRecordRow
from gendertagger.db.rows.reviews import AnnotationRow, ReviewStateRow
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationPersonPredictions,
    VoteCounts,
)
from gendertagger.models.classification import CanonicalLabel, PredictionResult
from gendertagger.models.evaluation import (
    EvaluationDefinition,
    EvaluationDefinitionId,
    EvaluationExecution,
    EvaluationExecutionCreate,
    EvaluationInputs,
)
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    EvaluationExecutionStatus,
    MethodExecutionStatus,
)
from gendertagger.models.review import ReviewAction
from gendertagger.services.pagination import CreationPosition
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

_COMPLETED_METHOD_STATUSES = {
    MethodExecutionStatus.completed,
    MethodExecutionStatus.completed_with_errors,
}
_TERMINAL_EVALUATION_STATUSES = {
    EvaluationExecutionStatus.completed,
    EvaluationExecutionStatus.failed,
}


class SqlAlchemyEvaluationRepository:
    """Map evaluation contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_evaluation(self, command: EvaluationExecutionCreate) -> EvaluationExecution:
        """Persist an evaluation only for completed executions from one run."""
        run = self._session.scalar(
            select(RunRow)
            .where(RunRow.id == command.run_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if run is None:
            msg = f"run {command.run_id} does not exist"
            raise ResourceNotFoundError(msg)

        execution_rows = tuple(
            self._session.scalars(
                select(MethodExecutionRow).where(
                    MethodExecutionRow.id.in_(command.method_execution_ids),
                    MethodExecutionRow.run_id == command.run_id,
                )
            )
        )
        executions_by_id = {row.id: row for row in execution_rows}
        if set(executions_by_id) != set(command.method_execution_ids):
            msg = "every selected method execution must belong to the evaluation run"
            raise InvalidResourceStateError(msg)
        incomplete_method_names = sorted(
            row.method_name
            for row in execution_rows
            if row.status not in _COMPLETED_METHOD_STATUSES
        )
        if incomplete_method_names:
            msg = f"method executions are not complete: {', '.join(incomplete_method_names)}"
            raise InvalidResourceStateError(msg)

        definition = EvaluationDefinition.model_validate(command.resolved_config)
        self._validate_method_selection(execution_rows, definition)

        if command.aggregation_execution_id is not None:
            aggregation = self._session.get(
                AggregationExecutionRow,
                command.aggregation_execution_id,
            )
            if aggregation is None:
                msg = f"aggregation execution {command.aggregation_execution_id} does not exist"
                raise ResourceNotFoundError(msg)
            if aggregation.run_id != command.run_id:
                msg = "the selected aggregation execution must belong to the evaluation run"
                raise InvalidResourceStateError(msg)
            if aggregation.status is not AggregationExecutionStatus.completed:
                msg = f"aggregation execution {aggregation.id} is not completed"
                raise InvalidResourceStateError(msg)

        row = EvaluationExecutionRow(
            run_id=command.run_id,
            aggregation_execution_id=command.aggregation_execution_id,
            definition=command.definition.value,
            resolved_config=command.resolved_config,
            config_sha256=command.canonical_config_sha256(),
            status=EvaluationExecutionStatus.pending,
            report_artifact_id=None,
            started_at=None,
            finished_at=None,
            failure_class=None,
            failure_diagnostic=None,
        )
        self._session.add(row)
        self._session.flush()
        self._session.add_all(
            [
                EvaluationMethodExecutionRow(
                    evaluation_execution_id=row.id,
                    method_execution_id=method_execution_id,
                    position=position,
                )
                for position, method_execution_id in enumerate(command.method_execution_ids)
            ]
        )
        self._session.flush()
        return self._evaluation_from_row(row, command.method_execution_ids)

    def get_evaluation(self, evaluation_execution_id: UUID) -> EvaluationExecution | None:
        """Return an evaluation contract with its exact ordered execution IDs."""
        row = self._session.get(EvaluationExecutionRow, evaluation_execution_id)
        if row is None:
            return None
        return self._evaluation_from_row(row, self._method_execution_ids(evaluation_execution_id))

    def list_evaluations(
        self,
        run_id: UUID,
        *,
        limit: int,
        after: CreationPosition | None = None,
    ) -> Sequence[EvaluationExecution]:
        """Return a run's evaluations newest first, in every lifecycle state."""
        rows = tuple(
            self._session.scalars(
                newest_first_slice(
                    select(EvaluationExecutionRow).where(EvaluationExecutionRow.run_id == run_id),
                    created_at=EvaluationExecutionRow.created_at,
                    row_id=EvaluationExecutionRow.id,
                    limit=limit,
                    after=after,
                )
            )
        )
        selections: defaultdict[UUID, list[UUID]] = defaultdict(list)
        if rows:
            for evaluation_execution_id, method_execution_id in self._session.execute(
                select(
                    EvaluationMethodExecutionRow.evaluation_execution_id,
                    EvaluationMethodExecutionRow.method_execution_id,
                )
                .where(
                    EvaluationMethodExecutionRow.evaluation_execution_id.in_(
                        [row.id for row in rows]
                    )
                )
                .order_by(
                    EvaluationMethodExecutionRow.evaluation_execution_id,
                    EvaluationMethodExecutionRow.position,
                )
            ):
                selections[evaluation_execution_id].append(method_execution_id)
        return tuple(self._evaluation_from_row(row, tuple(selections[row.id])) for row in rows)

    def mark_evaluation_queued(self, evaluation_execution_id: UUID) -> EvaluationExecution:
        """Atomically transition a pending evaluation to queued."""
        statement = (
            select(EvaluationExecutionRow)
            .where(
                EvaluationExecutionRow.id == evaluation_execution_id,
                EvaluationExecutionRow.status == EvaluationExecutionStatus.pending,
            )
            .with_for_update()
        )
        row = self._session.scalar(statement)
        if row is not None:
            row.status = EvaluationExecutionStatus.queued
            self._session.flush()
            return self._evaluation_from_row(
                row,
                self._method_execution_ids(evaluation_execution_id),
            )

        existing = self._require_evaluation(evaluation_execution_id)
        self._require_source(
            evaluation_execution_id,
            existing.status,
            {EvaluationExecutionStatus.pending},
            EvaluationExecutionStatus.queued.value,
        )
        raise AssertionError("unreachable evaluation queuing transition")  # pragma: no cover

    def claim_evaluation(
        self,
        evaluation_execution_id: UUID,
        *,
        started_at: datetime,
    ) -> EvaluationExecution | None:
        """Atomically claim a pending or queued evaluation for one worker."""
        statement = (
            select(EvaluationExecutionRow)
            .where(
                EvaluationExecutionRow.id == evaluation_execution_id,
                EvaluationExecutionRow.status.in_(
                    (
                        EvaluationExecutionStatus.pending,
                        EvaluationExecutionStatus.queued,
                    )
                ),
            )
            .with_for_update()
        )
        row = self._session.scalar(statement)
        if row is not None:
            row.status = EvaluationExecutionStatus.running
            row.started_at = started_at
            self._session.flush()
            return self._evaluation_from_row(
                row,
                self._method_execution_ids(evaluation_execution_id),
            )

        existing = self._session.scalar(
            select(EvaluationExecutionRow).where(
                EvaluationExecutionRow.id == evaluation_execution_id
            )
        )
        if existing is None:
            msg = f"evaluation execution {evaluation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        return None

    def load_evaluation_inputs(self, evaluation_execution_id: UUID) -> EvaluationInputs:
        """Load every snapshot person's selected predictions and optional ensemble evidence."""
        evaluation = self._require_evaluation(evaluation_execution_id)
        self._require_source(
            evaluation_execution_id,
            evaluation.status,
            {EvaluationExecutionStatus.running},
            "load evaluation inputs",
        )
        snapshot_id = self._snapshot_id_for_run(evaluation.run_id)

        selected_executions = tuple(
            self._session.execute(
                select(
                    EvaluationMethodExecutionRow.method_execution_id,
                    MethodExecutionRow.method_name,
                    MethodExecutionRow.run_id,
                    MethodExecutionRow.status,
                )
                .join(
                    MethodExecutionRow,
                    MethodExecutionRow.id == EvaluationMethodExecutionRow.method_execution_id,
                )
                .where(
                    EvaluationMethodExecutionRow.evaluation_execution_id == evaluation_execution_id
                )
                .order_by(EvaluationMethodExecutionRow.position)
            ).tuples()
        )
        if any(run_id != evaluation.run_id for _, _, run_id, _ in selected_executions):
            msg = "every selected method execution must still belong to the evaluation run"
            raise InvalidResourceStateError(msg)
        incomplete_method_names = sorted(
            method_name
            for _, method_name, _, status in selected_executions
            if status not in _COMPLETED_METHOD_STATUSES
        )
        if incomplete_method_names:
            msg = "selected method executions are no longer complete: " + ", ".join(
                incomplete_method_names
            )
            raise InvalidResourceStateError(msg)
        execution_names = {
            execution_id: method_name for execution_id, method_name, _, _ in selected_executions
        }
        if len(set(execution_names.values())) != len(selected_executions):
            msg = "an evaluation must select each stable method name exactly once"
            raise InvalidResourceStateError(msg)

        person_ids = tuple(
            self._session.scalars(
                select(PersonRecordRow.id)
                .where(PersonRecordRow.dataset_snapshot_id == snapshot_id)
                .order_by(PersonRecordRow.tei_id, PersonRecordRow.id)
            )
        )
        snapshot = self._session.get(DatasetSnapshotRow, snapshot_id)
        if snapshot is None or snapshot.record_count is None:
            msg = f"dataset snapshot {snapshot_id} has no complete record count"
            raise InvalidResourceStateError(msg)
        if len(person_ids) != snapshot.record_count:
            msg = (
                f"dataset snapshot {snapshot_id} declares {snapshot.record_count} "
                f"records but contains {len(person_ids)} people"
            )
            raise InvalidResourceStateError(msg)

        predictions_by_person: dict[UUID, dict[str, PredictionResult]] = defaultdict(dict)
        if execution_names and person_ids:
            prediction_rows = self._session.scalars(
                select(PredictionRow)
                .join(PersonRecordRow, PersonRecordRow.id == PredictionRow.person_record_id)
                .where(
                    PredictionRow.method_execution_id.in_(execution_names),
                    PersonRecordRow.dataset_snapshot_id == snapshot_id,
                )
            )
            for prediction_row in prediction_rows:
                method_name = execution_names[prediction_row.method_execution_id]
                predictions_by_person[prediction_row.person_record_id][method_name] = (
                    PredictionResult(
                        label=prediction_row.label,
                        status=prediction_row.status,
                        method_confidence=prediction_row.method_confidence,
                        raw_label=prediction_row.raw_label,
                        raw_output=prediction_row.raw_output,
                        metadata=prediction_row.prediction_metadata,
                    )
                )

        corpus = tuple(
            AggregationPersonPredictions(
                person_record_id=person_id,
                predictions=predictions_by_person[person_id],
            )
            for person_id in person_ids
        )

        if evaluation.aggregation_execution_id is None:
            return EvaluationInputs(corpus=corpus)

        aggregation = self._session.get(
            AggregationExecutionRow,
            evaluation.aggregation_execution_id,
        )
        if aggregation is None or aggregation.status is not AggregationExecutionStatus.completed:
            msg = (
                f"aggregation execution {evaluation.aggregation_execution_id} "
                "is no longer completed"
            )
            raise InvalidResourceStateError(msg)
        result_rows = self._session.scalars(
            select(AggregatedResultRow).where(
                AggregatedResultRow.aggregation_execution_id == evaluation.aggregation_execution_id
            )
        )
        aggregated_results = tuple(self._aggregated_result_from_row(row) for row in result_rows)

        human_reviewed_count = (
            self._session.scalar(
                select(func.count())
                .select_from(ReviewStateRow)
                .where(
                    ReviewStateRow.dataset_snapshot_id == snapshot_id,
                    ReviewStateRow.revision > 0,
                )
            )
            or 0
        )
        human_correction_count = (
            self._session.scalar(
                select(func.count())
                .select_from(ReviewStateRow)
                .join(AnnotationRow, AnnotationRow.id == ReviewStateRow.current_annotation_id)
                .where(
                    ReviewStateRow.dataset_snapshot_id == snapshot_id,
                    AnnotationRow.action == ReviewAction.correct,
                )
            )
            or 0
        )

        return EvaluationInputs(
            corpus=corpus,
            aggregated_results=aggregated_results,
            human_reviewed_count=human_reviewed_count,
            human_correction_count=human_correction_count,
        )

    def mark_evaluation_finished(
        self,
        evaluation_execution_id: UUID,
        *,
        status: EvaluationExecutionStatus,
        finished_at: datetime,
        report_artifact_id: UUID | None = None,
        failure_class: str | None = None,
        failure_diagnostic: str | None = None,
    ) -> EvaluationExecution:
        """Transition a running evaluation to a complete or failed outcome."""
        if status not in _TERMINAL_EVALUATION_STATUSES:
            msg = f"{status} is not a supported terminal evaluation status"
            raise ValueError(msg)
        row = self._require_evaluation(evaluation_execution_id)
        self._require_source(
            evaluation_execution_id,
            row.status,
            {EvaluationExecutionStatus.running},
            status.value,
        )
        failed = status is EvaluationExecutionStatus.failed
        if failed:
            if not (failure_diagnostic and failure_diagnostic.strip()):
                msg = "a failed evaluation requires a failure diagnostic"
                raise ValueError(msg)
            if report_artifact_id is not None:
                msg = "a failed evaluation must not retain a report artifact"
                raise InvalidResourceStateError(msg)
        elif report_artifact_id is None:
            msg = "a completed evaluation requires a report artifact"
            raise ValueError(msg)

        row.status = status
        row.finished_at = finished_at
        row.report_artifact_id = None if failed else report_artifact_id
        row.failure_class = failure_class if failed else None
        row.failure_diagnostic = failure_diagnostic if failed else None
        self._session.flush()
        return self._evaluation_from_row(
            row,
            self._method_execution_ids(evaluation_execution_id),
        )

    @staticmethod
    def _evaluation_from_row(
        row: EvaluationExecutionRow,
        method_execution_ids: tuple[UUID, ...],
    ) -> EvaluationExecution:
        return EvaluationExecution(
            id=row.id,
            run_id=row.run_id,
            aggregation_execution_id=row.aggregation_execution_id,
            definition=EvaluationDefinitionId(row.definition),
            resolved_config=row.resolved_config,
            method_execution_ids=method_execution_ids,
            config_sha256=row.config_sha256,
            status=row.status,
            report_artifact_id=row.report_artifact_id,
            started_at=row.started_at,
            finished_at=row.finished_at,
            failure_class=row.failure_class,
            failure_diagnostic=row.failure_diagnostic,
            created_at=row.created_at,
        )

    def _method_execution_ids(self, evaluation_execution_id: UUID) -> tuple[UUID, ...]:
        return tuple(
            self._session.scalars(
                select(EvaluationMethodExecutionRow.method_execution_id)
                .where(
                    EvaluationMethodExecutionRow.evaluation_execution_id == evaluation_execution_id
                )
                .order_by(EvaluationMethodExecutionRow.position)
            )
        )

    def _require_evaluation(self, evaluation_execution_id: UUID) -> EvaluationExecutionRow:
        row = self._session.get(EvaluationExecutionRow, evaluation_execution_id)
        if row is None:
            msg = f"evaluation execution {evaluation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        return row

    def _snapshot_id_for_run(self, run_id: UUID) -> UUID:
        snapshot_id = self._session.scalar(
            select(RunRow.dataset_snapshot_id).where(RunRow.id == run_id)
        )
        if snapshot_id is None:
            msg = f"run {run_id} does not exist"
            raise ResourceNotFoundError(msg)
        return snapshot_id

    @staticmethod
    def _require_source(
        evaluation_execution_id: UUID,
        current_status: EvaluationExecutionStatus,
        allowed_statuses: set[EvaluationExecutionStatus],
        action: str,
    ) -> None:
        if current_status not in allowed_statuses:
            msg = (
                f"evaluation execution {evaluation_execution_id} cannot {action} "
                f"from status {current_status.value}"
            )
            raise InvalidResourceStateError(msg)

    @staticmethod
    def _validate_method_selection(
        execution_rows: Sequence[MethodExecutionRow],
        definition: EvaluationDefinition,
    ) -> None:
        method_names = [row.method_name for row in execution_rows]
        if len(set(method_names)) != len(method_names):
            msg = "an evaluation must select each stable method name exactly once"
            raise InvalidResourceStateError(msg)
        supplied_methods = set(method_names)
        required_methods = set(definition.required_methods)
        missing_methods = sorted(required_methods - supplied_methods)
        unexpected_methods = sorted(supplied_methods - required_methods)
        if missing_methods or unexpected_methods:
            problems: list[str] = []
            if missing_methods:
                problems.append(f"missing required methods: {', '.join(missing_methods)}")
            if unexpected_methods:
                problems.append(f"unexpected methods: {', '.join(unexpected_methods)}")
            msg = f"invalid {definition.id.value} method selection: " + "; ".join(problems)
            raise InvalidResourceStateError(msg)

    @staticmethod
    def _aggregated_result_from_row(row: AggregatedResultRow) -> AggregatedResult:
        return AggregatedResult(
            id=row.id,
            aggregation_execution_id=row.aggregation_execution_id,
            person_record_id=row.person_record_id,
            outcome=row.outcome,
            label=row.label,
            pooled_vote_counts=VoteCounts(
                male=row.male_vote_count,
                female=row.female_vote_count,
                unknown=row.unknown_vote_count,
                institution=row.institution_vote_count,
            ),
            tied_labels=tuple(CanonicalLabel(label) for label in row.tied_labels),
            override_source=row.override_source,
            override_agreeing_count=row.override_agreeing_count,
            override_comparison_count=row.override_comparison_count,
            agreement_score=row.agreement_score,
            agreement_tier=row.agreement_tier,
            certainty_tier=row.certainty_tier,
            has_prediction_error=row.has_prediction_error,
            metadata=row.result_metadata,
            created_at=row.created_at,
        )
