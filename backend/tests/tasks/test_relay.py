import logging
import signal
from collections.abc import Callable, Iterator
from threading import Event
from types import FrameType
from typing import cast
from unittest.mock import Mock
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.models.project import SnapshotImportTaskMessage
from gendertagger.models.run import TaskBatchMessage
from gendertagger.services.dispatch import (
    DispatchReconciler,
    OutboxRelay,
    ReconciliationResult,
    RelayCycleResult,
)
from gendertagger.tasks import relay as relay_module
from gendertagger.tasks.aggregation import EXECUTE_AGGREGATION_TASK_NAME
from gendertagger.tasks.dispatch import CeleryMessagePublisher
from gendertagger.tasks.execution import EXECUTE_BATCH_TASK_NAME
from gendertagger.tasks.relay import DispatchCoordinator, DispatchCoordinatorSettings
from gendertagger.tasks.snapshot_import import EXECUTE_SNAPSHOT_IMPORT_TASK_NAME

pytestmark = pytest.mark.unit

BATCH_ID = UUID("20000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("30000000-0000-0000-0000-000000000001")
AGGREGATION_ID = UUID("40000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("50000000-0000-0000-0000-000000000001")


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


def test_celery_publisher_routes_snapshot_import_by_stable_task_id() -> None:
    celery_app = Mock()
    publisher = CeleryMessagePublisher(celery_app)
    message = SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID)

    publisher.publish(message, queue_name="cpu", task_id=SNAPSHOT_ID)

    celery_app.send_task.assert_called_once_with(
        EXECUTE_SNAPSHOT_IMPORT_TASK_NAME,
        kwargs={"dataset_snapshot_id": str(SNAPSHOT_ID)},
        queue="cpu",
        task_id=str(SNAPSHOT_ID),
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

    with pytest.raises(ValidationError, match="valid SQLAlchemy URL"):
        DispatchCoordinatorSettings(database_url=SecretStr("not-a-database-url"))

    with pytest.raises(ValidationError, match="must not be less"):
        DispatchCoordinatorSettings(
            database_url=SecretStr("postgresql+psycopg://user:pass@db/gendertagger"),
            dispatch_retry_base_seconds=20,
            dispatch_retry_max_seconds=10,
        )


def test_coordinator_rejects_nonpositive_intervals_and_batch_sizes() -> None:
    relay = cast(OutboxRelay, Mock())
    reconciler = cast(DispatchReconciler, Mock())

    with pytest.raises(ValueError, match="intervals must be positive"):
        DispatchCoordinator(
            relay=relay,
            reconciler=reconciler,
            stop_event=Event(),
            poll_interval_seconds=0,
            reconciliation_interval_seconds=1,
            relay_batch_size=1,
            reconciliation_batch_size=1,
        )

    with pytest.raises(ValueError, match="batch sizes must be positive"):
        DispatchCoordinator(
            relay=relay,
            reconciler=reconciler,
            stop_event=Event(),
            poll_interval_seconds=1,
            reconciliation_interval_seconds=1,
            relay_batch_size=0,
            reconciliation_batch_size=1,
        )


def test_coordinator_logs_failures_and_waits_after_partial_cycle(
    caplog: pytest.LogCaptureFixture,
) -> None:
    relay = Mock()
    relay.run_once.return_value = RelayCycleResult(
        claimed=1,
        published=0,
        failed=1,
        lease_conflicts=1,
    )
    reconciler = Mock()
    reconciler.run_once.return_value = ReconciliationResult(
        missing_created=2,
        stale_rearmed=3,
    )
    stop_event = Mock()
    stop_event.is_set.side_effect = [False, True]
    coordinator = DispatchCoordinator(
        relay=cast(OutboxRelay, relay),
        reconciler=cast(DispatchReconciler, reconciler),
        stop_event=stop_event,
        poll_interval_seconds=0.25,
        reconciliation_interval_seconds=60,
        relay_batch_size=10,
        reconciliation_batch_size=20,
        monotonic=Mock(side_effect=[0.0, 0.0]),
    )

    with caplog.at_level(logging.INFO, logger=relay_module.__name__):
        coordinator.run()

    stop_event.wait.assert_called_once_with(0.25)
    assert "deferred 1 of 1 claimed messages" in caplog.text
    assert "lost 1 leases" in caplog.text
    assert "created 2 missing and rearmed 3 stale rows" in caplog.text


def test_compose_dispatch_coordinator_wires_owned_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock()
    session_factory = Mock()
    celery_app = Mock()
    relay = Mock()
    reconciler = Mock()
    coordinator = Mock()
    monkeypatch.setattr(relay_module, "create_database_engine", Mock(return_value=engine))
    monkeypatch.setattr(relay_module, "create_session_factory", Mock(return_value=session_factory))
    monkeypatch.setattr(relay_module, "create_celery_app", Mock(return_value=celery_app))
    outbox_relay = Mock(return_value=relay)
    dispatch_reconciler = Mock(return_value=reconciler)
    dispatch_coordinator = Mock(return_value=coordinator)
    monkeypatch.setattr(relay_module, "OutboxRelay", outbox_relay)
    monkeypatch.setattr(relay_module, "DispatchReconciler", dispatch_reconciler)
    monkeypatch.setattr(relay_module, "DispatchCoordinator", dispatch_coordinator)
    settings = DispatchCoordinatorSettings(
        database_url=SecretStr("postgresql+psycopg://user:pass@db/gendertagger")
    )
    stop_event = Event()

    application = relay_module.compose_dispatch_coordinator(settings, stop_event=stop_event)

    assert application.coordinator is coordinator
    assert application.engine is engine
    assert application.celery_app is celery_app
    outbox_relay.assert_called_once()
    dispatch_reconciler.assert_called_once()
    dispatch_coordinator.assert_called_once_with(
        relay=relay,
        reconciler=reconciler,
        stop_event=stop_event,
        poll_interval_seconds=0.5,
        reconciliation_interval_seconds=60.0,
        relay_batch_size=100,
        reconciliation_batch_size=100,
    )


def test_application_close_releases_broker_and_database() -> None:
    engine = Mock()
    celery_app = Mock()
    application = relay_module.DispatchCoordinatorApplication(
        coordinator=Mock(),
        engine=engine,
        celery_app=celery_app,
    )

    application.close()

    celery_app.close.assert_called_once_with()
    engine.dispose.assert_called_once_with()


def test_shutdown_handlers_set_stop_event_and_log_signal(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    handlers: dict[int, object] = {}

    def capture_handler(signal_number: int, handler: object) -> None:
        handlers[signal_number] = handler

    monkeypatch.setattr(signal, "signal", capture_handler)
    stop_event = Event()
    relay_module._install_shutdown_handlers(stop_event)

    with caplog.at_level(logging.INFO, logger=relay_module.__name__):
        handler = cast(Callable[[int, FrameType | None], None], handlers[signal.SIGTERM])
        handler(signal.SIGTERM, None)

    assert stop_event.is_set()
    assert "received SIGTERM" in caplog.text
    assert set(handlers) == {signal.SIGINT, signal.SIGTERM}


def test_main_closes_application_when_coordinator_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = Mock()
    application.coordinator.run.side_effect = RuntimeError("relay stopped")
    monkeypatch.setattr(relay_module, "DispatchCoordinatorSettings", Mock(return_value=Mock()))
    monkeypatch.setattr(relay_module, "_install_shutdown_handlers", Mock())
    monkeypatch.setattr(
        relay_module,
        "compose_dispatch_coordinator",
        Mock(return_value=application),
    )

    with pytest.raises(RuntimeError, match="relay stopped"):
        relay_module.main()

    application.close.assert_called_once_with()
