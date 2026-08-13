"""SQLAlchemy repository for aggregation executions and immutable results."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gendertagger.config.run import AggregationStrategy
from gendertagger.db.aggregations import (
    AggregatedResultRow,
    AggregationExecutionRow,
    AggregationMethodExecutionRow,
)
from gendertagger.db.executions import MethodExecutionRow, RunRow
from gendertagger.db.projects import PersonRecordRow
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationResultWrite,
    VoteCounts,
)
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.lifecycle import AggregationExecutionStatus, MethodExecutionStatus
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

_COMPLETED_METHOD_STATUSES = {
    MethodExecutionStatus.completed,
    MethodExecutionStatus.completed_with_errors,
}


class SqlAlchemyAggregationRepository:
    """Map aggregation contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_aggregation(self, command: AggregationExecutionCreate) -> AggregationExecution:
        """Persist an aggregation only for completed executions from one run."""
        run = self._session.get(RunRow, command.run_id)
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

    def add_results(
        self,
        aggregation_execution_id: UUID,
        results: Sequence[AggregationResultWrite],
    ) -> int:
        """Validate snapshot ownership and persist immutable aggregation outputs."""
        aggregation = self._session.get(AggregationExecutionRow, aggregation_execution_id)
        if aggregation is None:
            msg = f"aggregation execution {aggregation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if not results:
            return 0

        person_ids = {result.person_record_id for result in results}
        if len(person_ids) != len(results):
            msg = "an aggregation result batch must contain each person at most once"
            raise ValueError(msg)
        run_snapshot_id = self._session.scalar(
            select(RunRow.dataset_snapshot_id).where(RunRow.id == aggregation.run_id)
        )
        matching_person_ids = set(
            self._session.scalars(
                select(PersonRecordRow.id).where(
                    PersonRecordRow.id.in_(person_ids),
                    PersonRecordRow.dataset_snapshot_id == run_snapshot_id,
                )
            )
        )
        if matching_person_ids != person_ids:
            msg = "every aggregated result person must belong to the run snapshot"
            raise InvalidResourceStateError(msg)

        rows = []
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
                    agreement_score=result.agreement_score,
                    agreement_tier=result.agreement_tier,
                    certainty_tier=result.certainty_tier,
                    result_metadata=result_write.metadata,
                )
            )
        self._session.add_all(rows)
        self._session.flush()
        return len(rows)

    def get_result(self, aggregated_result_id: UUID) -> AggregatedResult | None:
        """Return one immutable aggregated result without exposing its row."""
        row = self._session.get(AggregatedResultRow, aggregated_result_id)
        return None if row is None else self._result_from_row(row)

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
            metadata=row.result_metadata,
            created_at=row.created_at,
        )
