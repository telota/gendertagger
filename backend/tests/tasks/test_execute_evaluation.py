from typing import Protocol, cast
from unittest.mock import Mock
from uuid import UUID

import pytest
from celery.exceptions import Retry

import gendertagger.tasks.evaluation as evaluation_task
from gendertagger.models.evaluation import EvaluationTaskMessage
from gendertagger.services.evaluation_execution import (
    DEFAULT_MAX_EVALUATION_ATTEMPTS,
    TransientEvaluationError,
)

pytestmark = pytest.mark.unit

EVALUATION_ID = UUID("10000000-0000-0000-0000-000000000001")


class _EvaluationTask(Protocol):
    def run(self, *, evaluation_execution_id: str) -> None: ...


def _task_proxy() -> _EvaluationTask:
    """Expose Celery's untyped runtime proxy through the interface under test."""
    return cast(_EvaluationTask, evaluation_task.execute_evaluation)


def test_task_rebuilds_identifier_envelope_and_calls_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    monkeypatch.setattr(evaluation_task, "_evaluation_executor", lambda: executor)

    _task_proxy().run(
        evaluation_execution_id=str(EVALUATION_ID),
    )

    executor.execute.assert_called_once_with(
        EvaluationTaskMessage(evaluation_execution_id=EVALUATION_ID),
        attempt_count=1,
        max_attempts=DEFAULT_MAX_EVALUATION_ATTEMPTS,
    )


def test_task_retries_only_transient_evaluation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    executor.execute.side_effect = TransientEvaluationError("retry evaluation")
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(evaluation_task, "_evaluation_executor", lambda: executor)
    monkeypatch.setattr(evaluation_task.execute_evaluation, "retry", retry)
    monkeypatch.setattr("gendertagger.services.dispatch.random.uniform", lambda _low, _high: 2.0)

    with pytest.raises(Retry):
        _task_proxy().run(
            evaluation_execution_id=str(EVALUATION_ID),
        )

    retry_kwargs = retry.call_args.kwargs
    assert isinstance(retry_kwargs["exc"], TransientEvaluationError)
    assert retry_kwargs["countdown"] == 2.0
