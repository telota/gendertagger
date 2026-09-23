"""SQLAlchemy repository for aggregation executions and immutable results."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from gendertagger.config.run import AggregationStrategy
from gendertagger.db.keyset import newest_first_slice
from gendertagger.db.rows.aggregations import (
    AggregatedResultRow,
    AggregationExecutionRow,
    AggregationMethodExecutionRow,
)
from gendertagger.db.rows.executions import MethodExecutionRow, PredictionRow, RunRow
from gendertagger.db.rows.projects import DatasetSnapshotRow, PersonRecordRow
from gendertagger.domain.aggregation import (
    REFERENCE_IGNORED_METHODS,
    REFERENCE_REQUIRED_METHODS,
)
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationPersonPredictions,
    AggregationResultWrite,
    ResultMethodPrediction,
    VoteCounts,
)
from gendertagger.models.classification import CanonicalLabel, PredictionResult
from gendertagger.models.lifecycle import AggregationExecutionStatus, MethodExecutionStatus
from gendertagger.services.pagination import CreationPosition
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

_COMPLETED_METHOD_STATUSES = {
    MethodExecutionStatus.completed,
    MethodExecutionStatus.completed_with_errors,
}
_TERMINAL_AGGREGATION_STATUSES = {
    AggregationExecutionStatus.completed,
    AggregationExecutionStatus.failed,
}
_REUSABLE_AGGREGATION_STATUSES = (
    AggregationExecutionStatus.pending,
    AggregationExecutionStatus.queued,
    AggregationExecutionStatus.running,
    AggregationExecutionStatus.completed,
)
_REFERENCE_ALLOWED_METHODS = frozenset(REFERENCE_REQUIRED_METHODS + REFERENCE_IGNORED_METHODS)


class SqlAlchemyAggregationRepository:
    """Map aggregation contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_aggregation(self, command: AggregationExecutionCreate) -> AggregationExecution:
        """Persist an aggregation only for completed executions from one run."""
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
            msg = "every selected method execution must belong to the aggregation run"
            raise InvalidResourceStateError(msg)
        incomplete_method_names = sorted(
            row.method_name
            for row in execution_rows
            if row.status not in _COMPLETED_METHOD_STATUSES
        )
        if incomplete_method_names:
            msg = f"method executions are not complete: {', '.join(incomplete_method_names)}"
            raise InvalidResourceStateError(msg)
        self._validate_reference_method_selection(execution_rows)

        row = AggregationExecutionRow(
            run_id=command.run_id,
            strategy=command.strategy.value,
            resolved_config=command.resolved_config,
            config_sha256=command.canonical_config_sha256(),
            status=AggregationExecutionStatus.pending,
            started_at=None,
            finished_at=None,
            failure_class=None,
            failure_diagnostic=None,
        )
        self._session.add(row)
        self._session.flush()
        self._session.add_all(
            [
                AggregationMethodExecutionRow(
                    aggregation_execution_id=row.id,
                    method_execution_id=method_execution_id,
                    position=position,
                )
                for position, method_execution_id in enumerate(command.method_execution_ids)
            ]
        )
        self._session.flush()
        return self._aggregation_from_row(row, command.method_execution_ids)

    def find_reusable_aggregation(
        self,
        command: AggregationExecutionCreate,
    ) -> AggregationExecution | None:
        """Lock the run row, then return the oldest live or completed identical aggregation.

        ``FOR NO KEY UPDATE`` serializes concurrent creators on the run while still admitting the
        ``FOR KEY SHARE`` locks of foreign-key checks. Under ``READ COMMITTED`` the candidate
        query runs after the lock is granted, so it sees an identical aggregation that a
        concurrent request committed while this one waited (ADR-0034).
        """
        self._session.execute(
            select(RunRow.id).where(RunRow.id == command.run_id).with_for_update(key_share=True)
        )
        candidates = tuple(
            self._session.scalars(
                select(AggregationExecutionRow)
                .where(
                    AggregationExecutionRow.run_id == command.run_id,
                    AggregationExecutionRow.strategy == command.strategy.value,
                    AggregationExecutionRow.config_sha256 == command.canonical_config_sha256(),
                    AggregationExecutionRow.status.in_(_REUSABLE_AGGREGATION_STATUSES),
                )
                .order_by(AggregationExecutionRow.created_at, AggregationExecutionRow.id)
            )
        )
        selections = self._method_execution_ids_by_aggregation([row.id for row in candidates])
        for row in candidates:
            if selections[row.id] == command.method_execution_ids:
                return self._aggregation_from_row(row, selections[row.id])
        return None

    def get_aggregation(self, aggregation_execution_id: UUID) -> AggregationExecution | None:
        """Return an aggregation contract with its exact ordered execution IDs."""
        row = self._session.get(AggregationExecutionRow, aggregation_execution_id)
        if row is None:
            return None
        method_execution_ids = tuple(
            self._session.scalars(
                select(AggregationMethodExecutionRow.method_execution_id)
                .where(
                    AggregationMethodExecutionRow.aggregation_execution_id
                    == aggregation_execution_id
                )
                .order_by(AggregationMethodExecutionRow.position)
            )
        )
        return self._aggregation_from_row(row, method_execution_ids)

    def list_aggregations(
        self,
        run_id: UUID,
        *,
        limit: int,
        after: CreationPosition | None = None,
    ) -> Sequence[AggregationExecution]:
        """Return a run's aggregations newest first, in every lifecycle state."""
        rows = tuple(
            self._session.scalars(
                newest_first_slice(
                    select(AggregationExecutionRow).where(AggregationExecutionRow.run_id == run_id),
                    created_at=AggregationExecutionRow.created_at,
                    row_id=AggregationExecutionRow.id,
                    limit=limit,
                    after=after,
                )
            )
        )
        selections = self._method_execution_ids_by_aggregation([row.id for row in rows])
        return tuple(self._aggregation_from_row(row, selections[row.id]) for row in rows)

    def mark_aggregation_queued(
        self,
        aggregation_execution_id: UUID,
    ) -> AggregationExecution:
        """Atomically transition a pending aggregation to queued."""
        statement = (
            update(AggregationExecutionRow)
            .where(
                AggregationExecutionRow.id == aggregation_execution_id,
                AggregationExecutionRow.status == AggregationExecutionStatus.pending,
            )
            .values(status=AggregationExecutionStatus.queued)
            .returning(AggregationExecutionRow)
            .execution_options(populate_existing=True)
        )
        row = self._session.scalar(statement)
        if row is not None:
            self._session.flush()
            return self._aggregation_from_row(
                row,
                self._method_execution_ids(aggregation_execution_id),
            )

        existing = self._session.scalar(
            select(AggregationExecutionRow)
            .where(AggregationExecutionRow.id == aggregation_execution_id)
            .execution_options(populate_existing=True)
        )
        if existing is None:
            msg = f"aggregation execution {aggregation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        self._require_source(
            aggregation_execution_id,
            existing.status,
            {AggregationExecutionStatus.pending},
            AggregationExecutionStatus.queued.value,
        )
        raise AssertionError("unreachable aggregation queuing transition")

    def claim_aggregation(
        self,
        aggregation_execution_id: UUID,
        *,
        started_at: datetime,
    ) -> AggregationExecution | None:
        """Atomically claim a pending or queued aggregation for one worker."""
        statement = (
            update(AggregationExecutionRow)
            .where(
                AggregationExecutionRow.id == aggregation_execution_id,
                AggregationExecutionRow.status.in_(
                    (
                        AggregationExecutionStatus.pending,
                        AggregationExecutionStatus.queued,
                    )
                ),
            )
            .values(
                status=AggregationExecutionStatus.running,
                started_at=started_at,
            )
            .returning(AggregationExecutionRow)
            .execution_options(populate_existing=True)
        )
        row = self._session.scalar(statement)
        if row is not None:
            self._session.flush()
            return self._aggregation_from_row(
                row,
                self._method_execution_ids(aggregation_execution_id),
            )

        existing = self._session.scalar(
            select(AggregationExecutionRow)
            .where(AggregationExecutionRow.id == aggregation_execution_id)
            .execution_options(populate_existing=True)
        )
        if existing is None:
            msg = f"aggregation execution {aggregation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        self._session.flush()
        return None

    def load_prediction_matrix(
        self,
        aggregation_execution_id: UUID,
    ) -> Sequence[AggregationPersonPredictions]:
        """Load every snapshot person and only persisted selected predictions."""
        aggregation = self._require_aggregation(aggregation_execution_id)
        self._require_source(
            aggregation_execution_id,
            aggregation.status,
            {AggregationExecutionStatus.running},
            "load prediction matrix",
        )
        snapshot_id = self._snapshot_id_for_run(aggregation.run_id)
        selected_executions = tuple(
            self._session.execute(
                select(
                    AggregationMethodExecutionRow.method_execution_id,
                    MethodExecutionRow.method_name,
                    MethodExecutionRow.run_id,
                    MethodExecutionRow.status,
                )
                .join(
                    MethodExecutionRow,
                    MethodExecutionRow.id == AggregationMethodExecutionRow.method_execution_id,
                )
                .where(
                    AggregationMethodExecutionRow.aggregation_execution_id
                    == aggregation_execution_id
                )
                .order_by(AggregationMethodExecutionRow.position)
            ).tuples()
        )
        if any(run_id != aggregation.run_id for _, _, run_id, _ in selected_executions):
            msg = "every selected method execution must still belong to the aggregation run"
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
            msg = "an aggregation must select each stable method name exactly once"
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
                    self._prediction_result_from_row(prediction_row)
                )

        return tuple(
            AggregationPersonPredictions(
                person_record_id=person_id,
                predictions=predictions_by_person[person_id],
            )
            for person_id in person_ids
        )

    def add_results(
        self,
        aggregation_execution_id: UUID,
        results: Sequence[AggregationResultWrite],
    ) -> int:
        """Persist one complete run-snapshot result set while aggregation is running."""
        aggregation = self._session.scalar(
            select(AggregationExecutionRow)
            .where(AggregationExecutionRow.id == aggregation_execution_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if aggregation is None:
            msg = f"aggregation execution {aggregation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        self._require_source(
            aggregation_execution_id,
            aggregation.status,
            {AggregationExecutionStatus.running},
            "add results",
        )

        person_ids = {result.person_record_id for result in results}
        if len(person_ids) != len(results):
            msg = "an aggregation result batch must contain each person at most once"
            raise ValueError(msg)
        run_snapshot_id = self._snapshot_id_for_run(aggregation.run_id)
        snapshot = self._session.get(DatasetSnapshotRow, run_snapshot_id)
        if snapshot is None or snapshot.record_count is None:
            msg = f"dataset snapshot {run_snapshot_id} has no complete record count"
            raise InvalidResourceStateError(msg)
        snapshot_person_ids = set(
            self._session.scalars(
                select(PersonRecordRow.id).where(
                    PersonRecordRow.dataset_snapshot_id == run_snapshot_id
                )
            )
        )
        if len(snapshot_person_ids) != snapshot.record_count:
            msg = (
                f"dataset snapshot {run_snapshot_id} declares {snapshot.record_count} "
                f"records but contains {len(snapshot_person_ids)} people"
            )
            raise InvalidResourceStateError(msg)
        if person_ids != snapshot_person_ids:
            msg = (
                "aggregation results must exactly cover the run snapshot: "
                f"expected {len(snapshot_person_ids)} people, received {len(person_ids)}"
            )
            raise InvalidResourceStateError(msg)
        if not results:
            return 0

        rows: list[AggregatedResultRow] = []
        for result_write in results:
            result = result_write.result
            rows.append(
                AggregatedResultRow(
                    aggregation_execution_id=aggregation_execution_id,
                    person_record_id=result_write.person_record_id,
                    outcome=result.outcome,
                    label=result.label,
                    male_vote_count=result.pooled_vote_counts.male,
                    female_vote_count=result.pooled_vote_counts.female,
                    unknown_vote_count=result.pooled_vote_counts.unknown,
                    institution_vote_count=result.pooled_vote_counts.institution,
                    tied_labels=[label.value for label in result.tied_labels],
                    override_source=result.override_source,
                    override_agreeing_count=result.override_agreeing_count,
                    override_comparison_count=result.override_comparison_count,
                    has_prediction_error=result_write.has_prediction_error,
                    agreement_score=result.agreement_score,
                    agreement_tier=result.agreement_tier,
                    certainty_tier=result.certainty_tier,
                    result_metadata=result_write.metadata,
                )
            )
        self._session.add_all(rows)
        self._session.flush()
        return len(rows)

    def mark_aggregation_finished(
        self,
        aggregation_execution_id: UUID,
        *,
        status: AggregationExecutionStatus,
        finished_at: datetime,
        failure_class: str | None = None,
        failure_diagnostic: str | None = None,
    ) -> AggregationExecution:
        """Transition a running aggregation to a complete or failed outcome."""
        if status not in _TERMINAL_AGGREGATION_STATUSES:
            msg = f"{status} is not a supported terminal aggregation status"
            raise ValueError(msg)
        row = self._require_aggregation(aggregation_execution_id)
        self._require_source(
            aggregation_execution_id,
            row.status,
            {AggregationExecutionStatus.running},
            status.value,
        )
        failed = status is AggregationExecutionStatus.failed
        if failed and not (failure_diagnostic and failure_diagnostic.strip()):
            msg = "a failed aggregation requires a failure diagnostic"
            raise ValueError(msg)

        result_count = self._session.scalar(
            select(func.count(AggregatedResultRow.id)).where(
                AggregatedResultRow.aggregation_execution_id == aggregation_execution_id
            )
        )
        if failed:
            if result_count != 0:
                msg = "a failed aggregation must not retain partial results"
                raise InvalidResourceStateError(msg)
        else:
            snapshot_id = self._snapshot_id_for_run(row.run_id)
            snapshot = self._session.get(DatasetSnapshotRow, snapshot_id)
            if snapshot is None or snapshot.record_count is None:
                msg = f"dataset snapshot {snapshot_id} has no complete record count"
                raise InvalidResourceStateError(msg)
            person_count = self._session.scalar(
                select(func.count(PersonRecordRow.id)).where(
                    PersonRecordRow.dataset_snapshot_id == snapshot_id
                )
            )
            if person_count != snapshot.record_count:
                msg = (
                    f"dataset snapshot {snapshot_id} declares {snapshot.record_count} "
                    f"records but contains {person_count} people"
                )
                raise InvalidResourceStateError(msg)
            if result_count != snapshot.record_count:
                msg = (
                    "a completed aggregation requires exactly one result per "
                    f"snapshot person: expected {snapshot.record_count}, found {result_count}"
                )
                raise InvalidResourceStateError(msg)

        row.status = status
        row.finished_at = finished_at
        row.failure_class = failure_class if failed else None
        row.failure_diagnostic = failure_diagnostic if failed else None
        self._session.flush()
        return self._aggregation_from_row(
            row,
            self._method_execution_ids(aggregation_execution_id),
        )

    def get_result(self, aggregated_result_id: UUID) -> AggregatedResult | None:
        """Return one immutable aggregated result without exposing its row."""
        row = self._session.get(AggregatedResultRow, aggregated_result_id)
        return None if row is None else self._result_from_row(row)

    def list_result_predictions(
        self,
        aggregation_execution_id: UUID,
        person_record_id: UUID,
    ) -> Sequence[ResultMethodPrediction]:
        """Return each selected execution's prediction for one person, in selection order."""
        # The outer join yields no prediction row for an execution without one for this person.
        rows = cast(
            Sequence[tuple[MethodExecutionRow, PredictionRow | None]],
            self._session.execute(
                select(MethodExecutionRow, PredictionRow)
                .select_from(AggregationMethodExecutionRow)
                .join(
                    MethodExecutionRow,
                    MethodExecutionRow.id == AggregationMethodExecutionRow.method_execution_id,
                )
                .outerjoin(
                    PredictionRow,
                    and_(
                        PredictionRow.method_execution_id == MethodExecutionRow.id,
                        PredictionRow.person_record_id == person_record_id,
                    ),
                )
                .where(
                    AggregationMethodExecutionRow.aggregation_execution_id
                    == aggregation_execution_id
                )
                .order_by(AggregationMethodExecutionRow.position)
            )
            .tuples()
            .all(),
        )
        return tuple(
            ResultMethodPrediction(
                method_execution_id=execution.id,
                method_name=execution.method_name,
                implementation_version=execution.implementation_version,
                normalization_version=execution.normalization_version,
                prediction_id=None if prediction is None else prediction.id,
                prediction=(
                    None if prediction is None else self._prediction_result_from_row(prediction)
                ),
            )
            for execution, prediction in rows
        )

    def list_results(
        self,
        aggregation_execution_id: UUID,
        *,
        limit: int,
        after_person_record_id: UUID | None = None,
        after_result_id: UUID | None = None,
    ) -> Sequence[AggregatedResult]:
        """Return results in stable person-ID order using keyset continuation."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        if (after_person_record_id is None) != (after_result_id is None):
            msg = "result cursor fields must be supplied together"
            raise ValueError(msg)
        statement = select(AggregatedResultRow).where(
            AggregatedResultRow.aggregation_execution_id == aggregation_execution_id
        )
        if after_person_record_id is not None and after_result_id is not None:
            statement = statement.where(
                or_(
                    AggregatedResultRow.person_record_id > after_person_record_id,
                    and_(
                        AggregatedResultRow.person_record_id == after_person_record_id,
                        AggregatedResultRow.id > after_result_id,
                    ),
                )
            )
        rows = self._session.scalars(
            statement.order_by(
                AggregatedResultRow.person_record_id,
                AggregatedResultRow.id,
            ).limit(limit)
        )
        return tuple(self._result_from_row(row) for row in rows)

    @staticmethod
    def _prediction_result_from_row(row: PredictionRow) -> PredictionResult:
        return PredictionResult(
            label=row.label,
            status=row.status,
            method_confidence=row.method_confidence,
            raw_label=row.raw_label,
            raw_output=row.raw_output,
            metadata=row.prediction_metadata,
        )

    @staticmethod
    def _aggregation_from_row(
        row: AggregationExecutionRow,
        method_execution_ids: tuple[UUID, ...],
    ) -> AggregationExecution:
        return AggregationExecution(
            id=row.id,
            run_id=row.run_id,
            strategy=AggregationStrategy(row.strategy),
            resolved_config=row.resolved_config,
            method_execution_ids=method_execution_ids,
            config_sha256=row.config_sha256,
            status=row.status,
            started_at=row.started_at,
            finished_at=row.finished_at,
            failure_class=row.failure_class,
            failure_diagnostic=row.failure_diagnostic,
            created_at=row.created_at,
        )

    def _method_execution_ids_by_aggregation(
        self,
        aggregation_execution_ids: Sequence[UUID],
    ) -> dict[UUID, tuple[UUID, ...]]:
        """Return each aggregation's ordered selection, read in one query."""
        selections: defaultdict[UUID, list[UUID]] = defaultdict(list)
        if aggregation_execution_ids:
            for aggregation_execution_id, method_execution_id in self._session.execute(
                select(
                    AggregationMethodExecutionRow.aggregation_execution_id,
                    AggregationMethodExecutionRow.method_execution_id,
                )
                .where(
                    AggregationMethodExecutionRow.aggregation_execution_id.in_(
                        aggregation_execution_ids
                    )
                )
                .order_by(
                    AggregationMethodExecutionRow.aggregation_execution_id,
                    AggregationMethodExecutionRow.position,
                )
            ):
                selections[aggregation_execution_id].append(method_execution_id)
        return {
            aggregation_execution_id: tuple(selections[aggregation_execution_id])
            for aggregation_execution_id in aggregation_execution_ids
        }

    def _method_execution_ids(
        self,
        aggregation_execution_id: UUID,
    ) -> tuple[UUID, ...]:
        return self._method_execution_ids_by_aggregation([aggregation_execution_id])[
            aggregation_execution_id
        ]

    def _require_aggregation(
        self,
        aggregation_execution_id: UUID,
    ) -> AggregationExecutionRow:
        row = self._session.get(AggregationExecutionRow, aggregation_execution_id)
        if row is None:
            msg = f"aggregation execution {aggregation_execution_id} does not exist"
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
        aggregation_execution_id: UUID,
        current_status: AggregationExecutionStatus,
        allowed_statuses: set[AggregationExecutionStatus],
        action: str,
    ) -> None:
        if current_status not in allowed_statuses:
            msg = (
                f"aggregation execution {aggregation_execution_id} cannot {action} "
                f"from status {current_status.value}"
            )
            raise InvalidResourceStateError(msg)

    @staticmethod
    def _validate_reference_method_selection(
        execution_rows: Sequence[MethodExecutionRow],
    ) -> None:
        method_names = [row.method_name for row in execution_rows]
        if len(set(method_names)) != len(method_names):
            msg = "an aggregation must select each stable method name exactly once"
            raise InvalidResourceStateError(msg)
        supplied_methods = set(method_names)
        missing_methods = sorted(set(REFERENCE_REQUIRED_METHODS) - supplied_methods)
        unexpected_methods = sorted(supplied_methods - _REFERENCE_ALLOWED_METHODS)
        if missing_methods or unexpected_methods:
            problems: list[str] = []
            if missing_methods:
                problems.append(f"missing required methods: {', '.join(missing_methods)}")
            if unexpected_methods:
                problems.append(f"unexpected methods: {', '.join(unexpected_methods)}")
            msg = "invalid reference_v1 method selection: " + "; ".join(problems)
            raise InvalidResourceStateError(msg)

    @staticmethod
    def _result_from_row(row: AggregatedResultRow) -> AggregatedResult:
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
