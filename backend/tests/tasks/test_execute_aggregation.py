from typing import Protocol, cast
from unittest.mock import Mock
from uuid import UUID

import pytest
from celery.exceptions import Retry

import gendertagger.tasks.aggregation as aggregation_task
from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.services.aggregation_execution import (
    DEFAULT_MAX_AGGREGATION_ATTEMPTS,
    TransientAggregationError,
)

pytestmark = pytest.mark.unit

AGGREGATION_ID = UUID("10000000-0000-0000-0000-000000000001")


class _AggregationTask(Protocol):
    def run(self, *, aggregation_execution_id: str) -> None: ...


def _task_proxy() -> _AggregationTask:
    """Expose Celery's untyped runtime proxy through the interface under test."""
    return cast(_AggregationTask, aggregation_task.execute_aggregation)


def test_task_rebuilds_identifier_envelope_and_calls_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    monkeypatch.setattr(aggregation_task, "_aggregation_executor", lambda: executor)

    _task_proxy().run(
        aggregation_execution_id=str(AGGREGATION_ID),
    )

    executor.execute.assert_called_once_with(
        AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID),
        attempt_count=1,
        max_attempts=DEFAULT_MAX_AGGREGATION_ATTEMPTS,
    )


def test_task_retries_only_transient_aggregation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    executor.execute.side_effect = TransientAggregationError("retry aggregation")
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(aggregation_task, "_aggregation_executor", lambda: executor)
    monkeypatch.setattr(aggregation_task.execute_aggregation, "retry", retry)
    monkeypatch.setattr(aggregation_task, "_retry_countdown", lambda _retries: 2.0)

    with pytest.raises(Retry):
        _task_proxy().run(
            aggregation_execution_id=str(AGGREGATION_ID),
        )

    retry_kwargs = retry.call_args.kwargs
    assert isinstance(retry_kwargs["exc"], TransientAggregationError)
    assert retry_kwargs["countdown"] == 2.0
