"""Application orchestration for executable reference aggregations."""

from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError

from gendertagger.domain.aggregation import (
    REFERENCE_REQUIRED_METHODS,
    ReferenceAggregationError,
)
from gendertagger.domain.aggregation_assessment import (
    ReferenceAssessmentError,
    assess_reference_predictions,
)
from gendertagger.models.aggregation import (
    AggregationExecution,
    AggregationPersonPredictions,
    AggregationResultWrite,
    AggregationTaskMessage,
)
from gendertagger.models.classification import PredictionStatus
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.services.diagnostics import sanitized_diagnostic
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

Clock = Callable[[], datetime]

DEFAULT_MAX_AGGREGATION_ATTEMPTS = 3


class PermanentAggregationError(RuntimeError):
    """Raised when persisted evidence cannot produce the selected aggregation."""


class TransientAggregationError(RuntimeError):
    """Raised when aggregation execution should be retried after rollback."""


class AggregationExecutor:
    """Assess and atomically persist one complete reference aggregation.

    The claim, complete prediction matrix, immutable results, and terminal
    lifecycle transition share one transaction. A worker crash therefore
    exposes either the prior claimable resource or the complete final result,
    never a committed partial aggregation.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def execute(
        self,
        message: AggregationTaskMessage,
        *,
        attempt_count: int,
        max_attempts: int = DEFAULT_MAX_AGGREGATION_ATTEMPTS,
    ) -> AggregationExecution:
        """Idempotently execute one aggregation with bounded retry policy.

        Invalid or incomplete scientific evidence is terminally persisted.
        Unclassified failures roll back and request a retry until the final
        attempt, when a fresh claim records the sanitized failure diagnostic.

        Args:
            message: Identifier-only task envelope.
            attempt_count: One-based delivery attempt number.
            max_attempts: Maximum attempts before an unclassified error becomes
                terminal.

        Returns:
            The completed, failed, or previously claimed aggregation resource.

        Raises:
            TransientAggregationError: If an unclassified failure occurred and
                another attempt remains.
            ValueError: If attempt counts are not positive.
        """
        if attempt_count <= 0:
            msg = "attempt_count must be positive"
            raise ValueError(msg)
        if max_attempts <= 0:
            msg = "max_attempts must be positive"
            raise ValueError(msg)

        try:
            return self._execute_once(message)
        except Exception as error:
            if attempt_count < max_attempts:
                msg = (
                    f"aggregation {message.aggregation_execution_id} failed "
                    f"on attempt {attempt_count}"
                )
                raise TransientAggregationError(msg) from error
            return self._fail_after_rollback(message, error)

    def _execute_once(
        self,
        message: AggregationTaskMessage,
    ) -> AggregationExecution:
        with self._unit_of_work_factory() as unit_of_work:
            aggregation = unit_of_work.aggregations.claim_aggregation(
                message.aggregation_execution_id,
                started_at=self._clock(),
            )
            if aggregation is None:
                return self._existing_aggregation(unit_of_work, message)

            try:
                writes = self._assess_people(
                    unit_of_work.aggregations.load_prediction_matrix(aggregation.id)
                )
            except (
                PermanentAggregationError,
                ReferenceAggregationError,
                ReferenceAssessmentError,
                InvalidResourceStateError,
                ValidationError,
            ) as error:
                failed = self._mark_failed(unit_of_work, aggregation.id, error)
                unit_of_work.commit()
                return failed

            unit_of_work.aggregations.add_results(aggregation.id, writes)
            completed = unit_of_work.aggregations.mark_aggregation_finished(
                aggregation.id,
                status=AggregationExecutionStatus.completed,
                finished_at=self._clock(),
            )
            unit_of_work.commit()
            return completed

    def _fail_after_rollback(
        self,
        message: AggregationTaskMessage,
        error: BaseException,
    ) -> AggregationExecution:
        with self._unit_of_work_factory() as unit_of_work:
            aggregation = unit_of_work.aggregations.claim_aggregation(
                message.aggregation_execution_id,
                started_at=self._clock(),
            )
            if aggregation is None:
                return self._existing_aggregation(unit_of_work, message)
            failed = self._mark_failed(unit_of_work, aggregation.id, error)
            unit_of_work.commit()
            return failed

    @staticmethod
    def _assess_people(
        prediction_matrix: Sequence[AggregationPersonPredictions],
    ) -> list[AggregationResultWrite]:
        writes: list[AggregationResultWrite] = []
        required_methods = set(REFERENCE_REQUIRED_METHODS)
        for person_predictions in prediction_matrix:
            missing_methods = sorted(required_methods - person_predictions.predictions.keys())
            if missing_methods:
                msg = (
                    f"person record {person_predictions.person_record_id} is missing "
                    f"required predictions: {', '.join(missing_methods)}"
                )
                raise PermanentAggregationError(msg)
            writes.append(
                AggregationResultWrite(
                    person_record_id=person_predictions.person_record_id,
                    result=assess_reference_predictions(person_predictions.predictions),
                    has_prediction_error=any(
                        prediction.status is PredictionStatus.error
                        for prediction in person_predictions.predictions.values()
                    ),
                    metadata={"strategy": "reference_v1"},
                )
            )
        return writes

    def _mark_failed(
        self,
        unit_of_work: UnitOfWork,
        aggregation_execution_id: UUID,
        error: BaseException,
    ) -> AggregationExecution:
        return unit_of_work.aggregations.mark_aggregation_finished(
            aggregation_execution_id,
            status=AggregationExecutionStatus.failed,
            finished_at=self._clock(),
            failure_class=type(error).__name__,
            failure_diagnostic=sanitized_diagnostic(error),
        )

    @staticmethod
    def _existing_aggregation(
        unit_of_work: UnitOfWork,
        message: AggregationTaskMessage,
    ) -> AggregationExecution:
        aggregation = unit_of_work.aggregations.get_aggregation(message.aggregation_execution_id)
        if aggregation is None:
            msg = f"aggregation execution {message.aggregation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        return aggregation
