from collections.abc import Iterator
from threading import Event
from typing import cast
from unittest.mock import Mock
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.models.run import TaskBatchMessage
from gendertagger.services.dispatch import (
    DispatchReconciler,
    OutboxRelay,
    ReconciliationResult,
    RelayCycleResult,
)
from gendertagger.tasks.aggregation import EXECUTE_AGGREGATION_TASK_NAME
from gendertagger.tasks.dispatch import CeleryMessagePublisher
from gendertagger.tasks.execution import EXECUTE_BATCH_TASK_NAME
from gendertagger.tasks.relay import DispatchCoordinator, DispatchCoordinatorSettings

pytestmark = pytest.mark.unit

BATCH_ID = UUID("20000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("30000000-0000-0000-0000-000000000001")
AGGREGATION_ID = UUID("40000000-0000-0000-0000-000000000001")


class _FakeRelay:
    def __init__(self, stop_event: Event) -> None:
        self._stop_event = stop_event
        self.limits: list[int] = []

    def run_once(self, *, limit: int = 100) -> RelayCycleResult:
        self.limits.append(limit)
        if len(self.limits) == 4:
            self._stop_event.set()
        return RelayCycleResult(claimed=limit, published=limit, failed=0)


class _FakeReconciler:
    def __init__(self) -> None:
        self.limits: list[int] = []

    def run_once(self, *, limit: int = 100) -> ReconciliationResult:
        self.limits.append(limit)
        return ReconciliationResult(missing_created=0, stale_rearmed=0)


def test_celery_publisher_sends_small_envelope_with_stable_task_id() -> None:
    celery_app = Mock()
    publisher = CeleryMessagePublisher(celery_app)
    message = TaskBatchMessage(
        method_execution_id=EXECUTION_ID,
        task_batch_id=BATCH_ID,
    )

    publisher.publish(message, queue_name="cpu", task_id=BATCH_ID)

    celery_app.send_task.assert_called_once_with(
        EXECUTE_BATCH_TASK_NAME,
        kwargs={
            "method_execution_id": str(EXECUTION_ID),
            "task_batch_id": str(BATCH_ID),
        },
        queue="cpu",
        task_id=str(BATCH_ID),
        retry=False,
    )


def test_celery_publisher_routes_aggregation_envelope_by_stable_task_id() -> None:
    celery_app = Mock()
    publisher = CeleryMessagePublisher(celery_app)
    message = AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID)

    publisher.publish(message, queue_name="cpu", task_id=AGGREGATION_ID)

    celery_app.send_task.assert_called_once_with(
        EXECUTE_AGGREGATION_TASK_NAME,
        kwargs={"aggregation_execution_id": str(AGGREGATION_ID)},
        queue="cpu",
        task_id=str(AGGREGATION_ID),
        retry=False,
    )


def test_celery_publisher_rejects_a_mismatched_stable_task_id() -> None:
    publisher = CeleryMessagePublisher(Mock())
    message = AggregationTaskMessage(aggregation_execution_id=AGGREGATION_ID)

    with pytest.raises(ValueError, match="must match the aggregation"):
        publisher.publish(message, queue_name="cpu", task_id=BATCH_ID)


def test_coordinator_relays_frequently_and_reconciles_on_slower_schedule() -> None:
    stop_event = Event()
    relay = _FakeRelay(stop_event)
    reconciler = _FakeReconciler()
    timestamps: Iterator[float] = iter((0.0, 0.0, 10.0, 59.0, 60.0))
    coordinator = DispatchCoordinator(
        relay=cast(OutboxRelay, relay),
        reconciler=cast(DispatchReconciler, reconciler),
        stop_event=stop_event,
        poll_interval_seconds=0.01,
        reconciliation_interval_seconds=60.0,
        relay_batch_size=20,
        reconciliation_batch_size=30,
        monotonic=lambda: next(timestamps),
    )

    coordinator.run()

    assert relay.limits == [20, 20, 20, 20]
    assert reconciler.limits == [30, 30]


def test_coordinator_settings_validate_database_and_retry_window() -> None:
    settings = DispatchCoordinatorSettings(
        database_url=SecretStr("postgresql+psycopg://user:pass@db/gendertagger"),
        dispatch_retry_base_seconds=2,
        dispatch_retry_max_seconds=10,
    )

    assert settings.dispatch_poll_interval_seconds == 0.5

    with pytest.raises(ValidationError, match=r"postgresql\+psycopg"):
        DispatchCoordinatorSettings(database_url=SecretStr("sqlite:///local.db"))

    with pytest.raises(ValidationError, match="must not be less"):
        DispatchCoordinatorSettings(
            database_url=SecretStr("postgresql+psycopg://user:pass@db/gendertagger"),
            dispatch_retry_base_seconds=20,
            dispatch_retry_max_seconds=10,
        )
