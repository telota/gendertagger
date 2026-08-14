from unittest.mock import Mock
from uuid import UUID

import pytest
from celery.exceptions import Retry

from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.services.aggregation_execution import (
    DEFAULT_MAX_AGGREGATION_ATTEMPTS,
    TransientAggregationError,
)
from gendertagger.tasks import aggregation as aggregation_task

pytestmark = pytest.mark.unit

AGGREGATION_ID = UUID("10000000-0000-0000-0000-000000000001")


def test_task_rebuilds_identifier_envelope_and_calls_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock()
    monkeypatch.setattr(aggregation_task, "_aggregation_executor", lambda: executor)

    aggregation_task.execute_aggregation.run(
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
        aggregation_task.execute_aggregation.run(
            aggregation_execution_id=str(AGGREGATION_ID),
        )

    retry_kwargs = retry.call_args.kwargs
    assert isinstance(retry_kwargs["exc"], TransientAggregationError)
    assert retry_kwargs["countdown"] == 2.0
