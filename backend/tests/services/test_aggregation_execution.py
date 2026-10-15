from datetime import UTC, datetime
from types import TracebackType
from typing import Self, cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.config.run import AggregationStrategy
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import (
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationPersonPredictions,
    AggregationPredictionMatrix,
    AggregationResultWrite,
    AggregationTaskMessage,
)
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.services.aggregation_execution import (
    AggregationExecutor,
    TransientAggregationError,
)
from gendertagger.services.ports.aggregation_repository import AggregationRepository
from gendertagger.services.ports.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
AGGREGATION_ID = UUID("20000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("30000000-0000-0000-0000-000000000001")
SECOND_PERSON_ID = UUID("30000000-0000-0000-0000-000000000002")
METHOD_EXECUTION_IDS = tuple(
    UUID(f"40000000-0000-0000-0000-{index:012d}")
    for index, _method_name in enumerate(REFERENCE_REQUIRED_METHODS, start=1)
)


class _StubUnitOfWork:
    def __init__(self, repository: AggregationRepository) -> None:
        self._repository = repository
        self.commit_count = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    @property
    def aggregations(self) -> AggregationRepository:
        return self._repository

    def commit(self) -> None:
        self.commit_count += 1


class _UnitOfWorkFactory:
    def __init__(self, repository: AggregationRepository) -> None:
        self._repository = repository
        self.units: list[_StubUnitOfWork] = []

    def __call__(self) -> UnitOfWork:
        unit_of_work = _StubUnitOfWork(self._repository)
        self.units.append(unit_of_work)
        return cast(UnitOfWork, unit_of_work)


def _aggregation(
    status: AggregationExecutionStatus,
    *,
    strategy: AggregationStrategy = AggregationStrategy.reference_v1,
    method_execution_ids: tuple[UUID, ...] = METHOD_EXECUTION_IDS,
) -> AggregationExecution:
    command = AggregationExecutionCreate(
        run_id=RUN_ID,
        strategy=strategy,
        method_execution_ids=method_execution_ids,
    )
    started_at = NOW if status is not AggregationExecutionStatus.pending else None
    finished_at = (
        NOW
        if status in {AggregationExecutionStatus.completed, AggregationExecutionStatus.failed}
        else None
    )
    return AggregationExecution(
        id=AGGREGATION_ID,
        config_sha256=command.canonical_config_sha256(),
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        failure_class="PermanentAggregationError"
        if status is AggregationExecutionStatus.failed
        else None,
        failure_diagnostic="missing evidence"
        if status is AggregationExecutionStatus.failed
        else None,
        created_at=NOW,
        **command.model_dump(),
    )


def _prediction_matrix(*, omit: str | None = None) -> list[AggregationPersonPredictions]:
    predictions = {
        method_name: PredictionResult(
            label=CanonicalLabel.female if method_name == "gender_guesser" else None,
            status=(
                PredictionStatus.success
                if method_name == "gender_guesser"
                else PredictionStatus.error
                if method_name == "gnd"
                else PredictionStatus.abstain
            ),
        )
        for method_name in REFERENCE_REQUIRED_METHODS
        if method_name != omit
    }
    return [
        AggregationPersonPredictions(
            person_record_id=PERSON_ID,
            predictions=predictions,
        )
    ]


def _matrix(
    people: list[AggregationPersonPredictions],
    *,
    selected_methods: frozenset[str] = frozenset(REFERENCE_REQUIRED_METHODS),
) -> AggregationPredictionMatrix:
    return AggregationPredictionMatrix(selected_methods=selected_methods, people=tuple(people))


def _executor(repository: AggregationRepository) -> tuple[AggregationExecutor, _UnitOfWorkFactory]:
    factory = _UnitOfWorkFactory(repository)
    return AggregationExecutor(unit_of_work_factory=factory, clock=lambda: NOW), factory


def test_executor_persists_complete_results_with_explicit_abstains_and_errors() -> None:
    repository = Mock(spec=AggregationRepository)
    repository.claim_aggregation.return_value = _aggregation(AggregationExecutionStatus.running)
    repository.load_prediction_matrix.return_value = _matrix(_prediction_matrix())
    repository.mark_aggregation_finished.return_value = _aggregation(
        AggregationExecutionStatus.completed
    )
    executor, factory = _executor(repository)

    result = executor.execute(
        AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID),
        attempt_count=1,
    )

    assert result.status is AggregationExecutionStatus.completed
    writes = cast(list[AggregationResultWrite], repository.add_results.call_args.args[1])
    assert len(writes) == 1
    assert writes[0].person_record_id == PERSON_ID
    assert writes[0].result.label is CanonicalLabel.female
    assert writes[0].result.pooled_vote_counts.female == 1
    assert writes[0].has_prediction_error is True
    assert factory.units[0].commit_count == 1


def test_executor_projects_error_free_evidence_without_a_prediction_error_flag() -> None:
    repository = Mock(spec=AggregationRepository)
    repository.claim_aggregation.return_value = _aggregation(AggregationExecutionStatus.running)
    repository.load_prediction_matrix.return_value = _matrix(
        [
            _prediction_matrix()[0].model_copy(
                update={
                    "predictions": {
                        method_name: PredictionResult(
                            label=None,
                            status=PredictionStatus.abstain,
                        )
                        for method_name in REFERENCE_REQUIRED_METHODS
                    }
                }
            )
        ]
    )
    repository.mark_aggregation_finished.return_value = _aggregation(
        AggregationExecutionStatus.completed
    )
    executor, _ = _executor(repository)

    executor.execute(
        AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID),
        attempt_count=1,
    )

    writes = cast(list[AggregationResultWrite], repository.add_results.call_args.args[1])
    assert writes[0].has_prediction_error is False


def test_executor_fails_when_a_required_prediction_row_is_missing() -> None:
    repository = Mock(spec=AggregationRepository)
    repository.claim_aggregation.return_value = _aggregation(AggregationExecutionStatus.running)
    missing_person = _prediction_matrix(omit="gnd")[0].model_copy(
        update={"person_record_id": SECOND_PERSON_ID}
    )
    repository.load_prediction_matrix.return_value = _matrix(
        [*_prediction_matrix(), missing_person]
    )
    repository.mark_aggregation_finished.return_value = _aggregation(
        AggregationExecutionStatus.failed
    )
    executor, factory = _executor(repository)

    result = executor.execute(
        AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID),
        attempt_count=1,
    )

    assert result.status is AggregationExecutionStatus.failed
    repository.add_results.assert_not_called()
    finish_keywords = repository.mark_aggregation_finished.call_args.kwargs
    assert finish_keywords["failure_class"] == "PermanentAggregationError"
    assert "missing required predictions: gnd" in finish_keywords["failure_diagnostic"]
    assert factory.units[0].commit_count == 1


_PARTIAL_EXECUTION_IDS = (
    METHOD_EXECUTION_IDS[2],  # gender_guesser
    METHOD_EXECUTION_IDS[5],  # nomquamgender
)


def test_executor_accepts_a_partial_strategy_selection_missing_required_methods() -> None:
    # ADR-0051: `reference_partial_v1` requires only its own (smaller) selection, not the full
    # nine `reference_v1` methods — the whole point of the strategy.
    repository = Mock(spec=AggregationRepository)
    repository.claim_aggregation.return_value = _aggregation(
        AggregationExecutionStatus.running,
        strategy=AggregationStrategy.reference_partial_v1,
        method_execution_ids=_PARTIAL_EXECUTION_IDS,
    )
    repository.load_prediction_matrix.return_value = _matrix(
        [
            AggregationPersonPredictions(
                person_record_id=PERSON_ID,
                predictions={
                    "gender_guesser": PredictionResult(
                        label=CanonicalLabel.female, status=PredictionStatus.success
                    ),
                    "nomquamgender": PredictionResult(
                        label=CanonicalLabel.female, status=PredictionStatus.success
                    ),
                },
            )
        ],
        selected_methods=frozenset({"gender_guesser", "nomquamgender"}),
    )
    repository.mark_aggregation_finished.return_value = _aggregation(
        AggregationExecutionStatus.completed,
        strategy=AggregationStrategy.reference_partial_v1,
        method_execution_ids=_PARTIAL_EXECUTION_IDS,
    )
    executor, _ = _executor(repository)

    result = executor.execute(
        AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID),
        attempt_count=1,
    )

    assert result.status is AggregationExecutionStatus.completed
    writes = cast(list[AggregationResultWrite], repository.add_results.call_args.args[1])
    assert writes[0].result.label is CanonicalLabel.female
    assert writes[0].metadata == {"strategy": "reference_partial_v1"}


def test_executor_still_fails_partial_strategy_when_its_own_selection_is_incomplete() -> None:
    # A partial aggregation is lenient about which methods it needs overall, never about whether
    # every method it did select actually produced a prediction for every person.
    repository = Mock(spec=AggregationRepository)
    repository.claim_aggregation.return_value = _aggregation(
        AggregationExecutionStatus.running,
        strategy=AggregationStrategy.reference_partial_v1,
        method_execution_ids=_PARTIAL_EXECUTION_IDS,
    )
    repository.load_prediction_matrix.return_value = _matrix(
        [
            AggregationPersonPredictions(
                person_record_id=PERSON_ID,
                predictions={
                    "gender_guesser": PredictionResult(
                        label=CanonicalLabel.female, status=PredictionStatus.success
                    ),
                },
            )
        ],
        selected_methods=frozenset({"gender_guesser", "nomquamgender"}),
    )
    repository.mark_aggregation_finished.return_value = _aggregation(
        AggregationExecutionStatus.failed,
        strategy=AggregationStrategy.reference_partial_v1,
        method_execution_ids=_PARTIAL_EXECUTION_IDS,
    )
    executor, factory = _executor(repository)

    result = executor.execute(
        AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID),
        attempt_count=1,
    )

    assert result.status is AggregationExecutionStatus.failed
    repository.add_results.assert_not_called()
    finish_keywords = repository.mark_aggregation_finished.call_args.kwargs
    assert "missing required predictions: nomquamgender" in finish_keywords["failure_diagnostic"]
    assert factory.units[0].commit_count == 1


def test_executor_duplicate_delivery_returns_terminal_resource_without_reexecution() -> None:
    repository = Mock(spec=AggregationRepository)
    repository.claim_aggregation.return_value = None
    repository.get_aggregation.return_value = _aggregation(AggregationExecutionStatus.completed)
    executor, factory = _executor(repository)

    result = executor.execute(
        AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID),
        attempt_count=2,
    )

    assert result.status is AggregationExecutionStatus.completed
    repository.load_prediction_matrix.assert_not_called()
    repository.add_results.assert_not_called()
    repository.mark_aggregation_finished.assert_not_called()
    assert factory.units[0].commit_count == 0


def test_executor_retries_unclassified_errors_then_redacts_final_diagnostic() -> None:
    repository = Mock(spec=AggregationRepository)
    repository.claim_aggregation.side_effect = [
        _aggregation(AggregationExecutionStatus.running),
        _aggregation(AggregationExecutionStatus.running),
        _aggregation(AggregationExecutionStatus.running),
    ]
    repository.load_prediction_matrix.side_effect = ConnectionError(
        "database postgresql://operator:secret@localhost/gendertagger unavailable"
    )
    repository.mark_aggregation_finished.return_value = _aggregation(
        AggregationExecutionStatus.failed
    )
    executor, factory = _executor(repository)
    message = AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID)

    with pytest.raises(TransientAggregationError):
        executor.execute(message, attempt_count=1, max_attempts=2)
    failed = executor.execute(message, attempt_count=2, max_attempts=2)

    assert failed.status is AggregationExecutionStatus.failed
    finish_keywords = repository.mark_aggregation_finished.call_args.kwargs
    diagnostic = cast(str, finish_keywords["failure_diagnostic"])
    assert "secret" not in diagnostic
    assert "postgresql://<redacted>@localhost" in diagnostic
    assert len(factory.units) == 3
