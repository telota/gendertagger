from datetime import UTC, datetime
from types import TracebackType
from typing import BinaryIO, Self, cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.models.aggregation import AggregationPersonPredictions
from gendertagger.models.artifact import Artifact
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.evaluation import (
    EvaluationDefinition,
    EvaluationExecution,
    EvaluationExecutionCreate,
    EvaluationInputs,
    EvaluationTaskMessage,
)
from gendertagger.models.lifecycle import EvaluationExecutionStatus
from gendertagger.services.evaluation_execution import (
    EvaluationExecutor,
    TransientEvaluationError,
)
from gendertagger.services.ports.artifact_storage import ArtifactStorage, StoredArtifact
from gendertagger.services.ports.evaluation_repository import EvaluationRepository
from gendertagger.services.ports.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
EVALUATION_ID = UUID("20000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("30000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("50000000-0000-0000-0000-000000000001")
DEFINITION = EvaluationDefinition()


class _StubUnitOfWork:
    def __init__(self, evaluations: EvaluationRepository, artifacts: Mock) -> None:
        self._evaluations = evaluations
        self._artifacts = artifacts
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
    def evaluations(self) -> EvaluationRepository:
        return self._evaluations

    @property
    def artifacts(self) -> Mock:
        return self._artifacts

    def commit(self) -> None:
        self.commit_count += 1


class _UnitOfWorkFactory:
    def __init__(self, evaluations: EvaluationRepository, artifacts: Mock) -> None:
        self._evaluations = evaluations
        self._artifacts = artifacts
        self.units: list[_StubUnitOfWork] = []

    def __call__(self) -> UnitOfWork:
        unit_of_work = _StubUnitOfWork(self._evaluations, self._artifacts)
        self.units.append(unit_of_work)
        return cast(UnitOfWork, unit_of_work)


class _StubArtifactStorage:
    def __init__(self) -> None:
        self.stored: list[bytes] = []

    def store(self, source: BinaryIO, *, max_byte_size: int) -> StoredArtifact:
        content = source.read()
        assert len(content) <= max_byte_size
        self.stored.append(content)
        return StoredArtifact(storage_uri="local:test", sha256="a" * 64, byte_size=len(content))

    def open(self, storage_uri: str) -> BinaryIO:  # pragma: no cover - unused here
        raise NotImplementedError

    def materialize(self, storage_uri: str) -> object:  # pragma: no cover - unused here
        raise NotImplementedError


def _evaluation(
    status: EvaluationExecutionStatus,
    *,
    aggregation_execution_id: UUID | None = None,
) -> EvaluationExecution:
    command = EvaluationExecutionCreate(
        run_id=RUN_ID,
        resolved_config=DEFINITION.model_dump(mode="json"),
        method_execution_ids=tuple(UUID(int=index) for index in range(1, 10)),
        aggregation_execution_id=aggregation_execution_id,
    )
    started_at = NOW if status is not EvaluationExecutionStatus.pending else None
    finished_at = (
        NOW
        if status in {EvaluationExecutionStatus.completed, EvaluationExecutionStatus.failed}
        else None
    )
    return EvaluationExecution(
        id=EVALUATION_ID,
        config_sha256=command.canonical_config_sha256(),
        status=status,
        report_artifact_id=(ARTIFACT_ID if status is EvaluationExecutionStatus.completed else None),
        started_at=started_at,
        finished_at=finished_at,
        failure_class="EvaluationInputError"
        if status is EvaluationExecutionStatus.failed
        else None,
        failure_diagnostic=(
            "missing evidence" if status is EvaluationExecutionStatus.failed else None
        ),
        created_at=NOW,
        **command.model_dump(),
    )


def _complete_corpus() -> tuple[AggregationPersonPredictions, ...]:
    predictions = {
        method_name: PredictionResult(
            label=CanonicalLabel.male,
            status=PredictionStatus.success,
        )
        for method_name in DEFINITION.required_methods
    }
    return (AggregationPersonPredictions(person_record_id=PERSON_ID, predictions=predictions),)


def _executor(
    repository: EvaluationRepository,
    artifact_storage: ArtifactStorage,
    artifacts: Mock,
) -> tuple[EvaluationExecutor, _UnitOfWorkFactory]:
    factory = _UnitOfWorkFactory(repository, artifacts)
    executor = EvaluationExecutor(
        unit_of_work_factory=factory,
        artifact_storage=artifact_storage,
        max_report_bytes=1_000_000,
        clock=lambda: NOW,
    )
    return executor, factory


def test_executor_persists_a_report_artifact_and_completes() -> None:
    repository = Mock(spec=EvaluationRepository)
    repository.claim_evaluation.return_value = _evaluation(EvaluationExecutionStatus.running)
    repository.load_evaluation_inputs.return_value = EvaluationInputs(corpus=_complete_corpus())
    repository.mark_evaluation_finished.return_value = _evaluation(
        EvaluationExecutionStatus.completed
    )
    artifacts = Mock()
    artifacts.add_artifact.return_value = Artifact(
        id=ARTIFACT_ID,
        logical_type="evaluation_report",
        storage_uri="local:test",
        sha256="a" * 64,
        byte_size=10,
        media_type="application/json",
        created_at=NOW,
    )
    storage = _StubArtifactStorage()
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)

    result = executor.execute(
        EvaluationTaskMessage(evaluation_execution_id=EVALUATION_ID),
        attempt_count=1,
    )

    assert result.status is EvaluationExecutionStatus.completed
    assert len(storage.stored) == 1
    finish_kwargs = repository.mark_evaluation_finished.call_args.kwargs
    assert finish_kwargs["report_artifact_id"] == ARTIFACT_ID
    assert factory.units[0].commit_count == 1


def test_executor_fails_when_a_required_prediction_row_is_missing() -> None:
    repository = Mock(spec=EvaluationRepository)
    repository.claim_evaluation.return_value = _evaluation(EvaluationExecutionStatus.running)
    incomplete_predictions = {
        method_name: PredictionResult(label=CanonicalLabel.male, status=PredictionStatus.success)
        for method_name in DEFINITION.required_methods
        if method_name != "gnd"
    }
    repository.load_evaluation_inputs.return_value = EvaluationInputs(
        corpus=(
            AggregationPersonPredictions(
                person_record_id=PERSON_ID,
                predictions=incomplete_predictions,
            ),
        )
    )
    repository.mark_evaluation_finished.return_value = _evaluation(EvaluationExecutionStatus.failed)
    artifacts = Mock()
    storage = _StubArtifactStorage()
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)

    result = executor.execute(
        EvaluationTaskMessage(evaluation_execution_id=EVALUATION_ID),
        attempt_count=1,
    )

    assert result.status is EvaluationExecutionStatus.failed
    artifacts.add_artifact.assert_not_called()
    finish_kwargs = repository.mark_evaluation_finished.call_args.kwargs
    assert finish_kwargs["failure_class"] == "EvaluationInputError"
    assert "missing required predictions: gnd" in finish_kwargs["failure_diagnostic"]
    assert finish_kwargs.get("report_artifact_id") is None
    assert factory.units[0].commit_count == 1


def test_executor_duplicate_delivery_returns_terminal_resource_without_reexecution() -> None:
    repository = Mock(spec=EvaluationRepository)
    repository.claim_evaluation.return_value = None
    repository.get_evaluation.return_value = _evaluation(EvaluationExecutionStatus.completed)
    artifacts = Mock()
    storage = _StubArtifactStorage()
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)

    result = executor.execute(
        EvaluationTaskMessage(evaluation_execution_id=EVALUATION_ID),
        attempt_count=2,
    )

    assert result.status is EvaluationExecutionStatus.completed
    repository.load_evaluation_inputs.assert_not_called()
    repository.mark_evaluation_finished.assert_not_called()
    assert factory.units[0].commit_count == 0


def test_executor_retries_unclassified_errors_then_redacts_final_diagnostic() -> None:
    repository = Mock(spec=EvaluationRepository)
    repository.claim_evaluation.side_effect = [
        _evaluation(EvaluationExecutionStatus.running),
        _evaluation(EvaluationExecutionStatus.running),
        _evaluation(EvaluationExecutionStatus.running),
    ]
    repository.load_evaluation_inputs.side_effect = ConnectionError(
        "database postgresql://operator:secret@localhost/gendertagger unavailable"
    )
    repository.mark_evaluation_finished.return_value = _evaluation(EvaluationExecutionStatus.failed)
    artifacts = Mock()
    storage = _StubArtifactStorage()
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)
    message = EvaluationTaskMessage(evaluation_execution_id=EVALUATION_ID)

    with pytest.raises(TransientEvaluationError):
        executor.execute(message, attempt_count=1, max_attempts=2)
    failed = executor.execute(message, attempt_count=2, max_attempts=2)

    assert failed.status is EvaluationExecutionStatus.failed
    finish_kwargs = repository.mark_evaluation_finished.call_args.kwargs
    diagnostic = cast(str, finish_kwargs["failure_diagnostic"])
    assert "secret" not in diagnostic
    assert "postgresql://<redacted>@localhost" in diagnostic
    assert len(factory.units) == 3
