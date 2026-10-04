from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Protocol, cast
from unittest.mock import Mock

import pytest
from celery.exceptions import Retry
from sqlalchemy.exc import OperationalError

from gendertagger.services.aggregation_execution import TransientAggregationError
from gendertagger.services.evaluation_execution import TransientEvaluationError
from gendertagger.services.execution import TransientBatchError
from gendertagger.services.export_execution import TransientExportError
from gendertagger.services.snapshot_import import TransientSnapshotImportError
from gendertagger.tasks import (
    aggregation,
    evaluation,
    execution,
    export,
    public_classification,
    snapshot_import,
)

pytestmark = pytest.mark.unit

_IDENTIFIER = "10000000-0000-0000-0000-000000000001"


class _RetryingTask(Protocol):
    max_retries: int

    def run(self, **kwargs: str) -> None: ...

    def push_request(self, *, retries: int, is_eager: bool, called_directly: bool) -> None: ...

    def pop_request(self) -> None: ...


@dataclass(frozen=True)
class _TaskFailure:
    module: ModuleType
    task_name: str
    factory_name: str
    execution_name: str
    identifiers: dict[str, str]
    error_factory: Callable[[], Exception]
    max_retries: int


_FAILURES = (
    _TaskFailure(
        execution,
        "execute_batch",
        "_batch_executor",
        "execute",
        {"method_execution_id": _IDENTIFIER, "task_batch_id": _IDENTIFIER},
        lambda: TransientBatchError("retry batch"),
        2,
    ),
    _TaskFailure(
        aggregation,
        "execute_aggregation",
        "_aggregation_executor",
        "execute",
        {"aggregation_execution_id": _IDENTIFIER},
        lambda: TransientAggregationError("retry aggregation"),
        2,
    ),
    _TaskFailure(
        evaluation,
        "execute_evaluation",
        "_evaluation_executor",
        "execute",
        {"evaluation_execution_id": _IDENTIFIER},
        lambda: TransientEvaluationError("retry evaluation"),
        2,
    ),
    _TaskFailure(
        export,
        "execute_export",
        "_export_executor",
        "execute",
        {"export_execution_id": _IDENTIFIER},
        lambda: TransientExportError("retry export"),
        2,
    ),
    _TaskFailure(
        snapshot_import,
        "execute_snapshot_import",
        "_snapshot_import_executor",
        "execute",
        {"dataset_snapshot_id": _IDENTIFIER},
        lambda: TransientSnapshotImportError("retry import"),
        2,
    ),
    _TaskFailure(
        public_classification,
        "execute_public_classification",
        "_public_classification_service",
        "execute_job",
        {"classification_job_id": _IDENTIFIER},
        lambda: OperationalError("synthetic statement", {}, RuntimeError("connection lost")),
        5,
    ),
)


@pytest.mark.parametrize("failure", _FAILURES, ids=lambda failure: failure.task_name)
def test_worker_retry_windows_and_exhaustion_preserve_original_error(
    failure: _TaskFailure,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = failure.error_factory()
    executor = Mock()
    getattr(executor, failure.execution_name).side_effect = error
    monkeypatch.setattr(failure.module, failure.factory_name, lambda: executor)
    monkeypatch.setattr(
        "gendertagger.services.dispatch.random.uniform",
        lambda _minimum, maximum: maximum,
    )
    task = cast(_RetryingTask, getattr(failure.module, failure.task_name))
    assert task.max_retries == failure.max_retries

    for retries in range(failure.max_retries):
        task.push_request(retries=retries, is_eager=True, called_directly=False)
        try:
            with pytest.raises(Retry) as raised:
                task.run(**failure.identifiers)
            assert raised.value.exc is error
            assert raised.value.when == min(2.0 * 2**retries, 60.0)
        finally:
            task.pop_request()

    task.push_request(retries=failure.max_retries, is_eager=True, called_directly=False)
    try:
        with pytest.raises(type(error)) as exhausted:
            task.run(**failure.identifiers)
        assert exhausted.value is error
    finally:
        task.pop_request()


@pytest.mark.parametrize("failure", _FAILURES, ids=lambda failure: failure.task_name)
def test_worker_retry_jitter_can_start_at_zero(
    failure: _TaskFailure,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    getattr(executor, failure.execution_name).side_effect = failure.error_factory()
    monkeypatch.setattr(failure.module, failure.factory_name, lambda: executor)
    monkeypatch.setattr("gendertagger.services.dispatch.random.uniform", lambda _low, _high: 0.0)
    task = cast(_RetryingTask, getattr(failure.module, failure.task_name))
    task.push_request(retries=0, is_eager=True, called_directly=False)
    try:
        with pytest.raises(Retry) as raised:
            task.run(**failure.identifiers)
        assert raised.value.when == 0.0
    finally:
        task.pop_request()
