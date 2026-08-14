from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self, cast
from unittest.mock import Mock, call
from uuid import UUID

import pytest

from gendertagger.models.dispatch import BatchDispatch, BatchDispatchStatus
from gendertagger.models.run import TaskBatchMessage
from gendertagger.services.dispatch import (
    DispatchReconciler,
    MessagePublisher,
    OutboxRelay,
    ReconciliationResult,
    RelayCycleResult,
    exponential_retry_delay,
)
from gendertagger.services.dispatch_repository import DispatchRepository
from gendertagger.services.persistence_errors import InvalidResourceStateError
from gendertagger.services.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)
DISPATCH_ID = UUID("10000000-0000-0000-0000-000000000001")
BATCH_ID = UUID("20000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("30000000-0000-0000-0000-000000000001")
OTHER_DISPATCH_ID = UUID("10000000-0000-0000-0000-000000000002")
OTHER_BATCH_ID = UUID("20000000-0000-0000-0000-000000000002")


class _TransactionTracker:
    def __init__(self) -> None:
        self.active_count = 0
        self.commit_count = 0


class _StubUnitOfWork:
    def __init__(self, repository: DispatchRepository, tracker: _TransactionTracker) -> None:
        self._repository = repository
        self._tracker = tracker

    def __enter__(self) -> Self:
        self._tracker.active_count += 1
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._tracker.active_count -= 1

    @property
    def dispatches(self) -> DispatchRepository:
        return self._repository

    def commit(self) -> None:
        self._tracker.commit_count += 1


class _UnitOfWorkFactory:
    def __init__(self, repository: DispatchRepository, tracker: _TransactionTracker) -> None:
        self._repository = repository
        self._tracker = tracker

    def __call__(self) -> UnitOfWork:
        return cast(UnitOfWork, _StubUnitOfWork(self._repository, self._tracker))


class _RecordingPublisher:
    def __init__(self, tracker: _TransactionTracker, *, error: Exception | None = None) -> None:
        self._tracker = tracker
        self._error = error
        self.calls: list[tuple[TaskBatchMessage, str, UUID]] = []

    def publish(
        self,
        message: TaskBatchMessage,
        *,
        queue_name: str,
        task_id: UUID,
    ) -> None:
        assert self._tracker.active_count == 0
        self.calls.append((message, queue_name, task_id))
        if self._error is not None:
            raise self._error


def _dispatch(
    *,
    dispatch_id: UUID = DISPATCH_ID,
    batch_id: UUID = BATCH_ID,
    attempt_count: int = 1,
) -> BatchDispatch:
    message = TaskBatchMessage(
        method_execution_id=EXECUTION_ID,
        task_batch_id=batch_id,
    )
    return BatchDispatch(
        id=dispatch_id,
        task_batch_id=batch_id,
        queue_name="cpu",
        payload=message,
        status=BatchDispatchStatus.pending,
        attempt_count=attempt_count,
        available_at=NOW,
        lease_owner="relay-1",
        lease_until=NOW + timedelta(seconds=30),
        created_at=NOW,
        updated_at=NOW,
    )


def test_relay_publishes_outside_transaction_then_records_success() -> None:
    repository = Mock(spec=DispatchRepository)
    repository.claim_available.return_value = [_dispatch()]
    tracker = _TransactionTracker()
    publisher = _RecordingPublisher(tracker)
    relay = OutboxRelay(
        unit_of_work_factory=_UnitOfWorkFactory(repository, tracker),
        publisher=cast(MessagePublisher, publisher),
        relay_id="relay-1",
        clock=lambda: NOW,
    )

    result = relay.run_once(limit=25)

    assert result == RelayCycleResult(claimed=1, published=1, failed=0)
    assert publisher.calls == [(_dispatch().payload, "cpu", BATCH_ID)]
    repository.claim_available.assert_called_once_with(
        now=NOW,
        lease_owner="relay-1",
        lease_until=NOW + timedelta(seconds=30),
        limit=25,
    )
    repository.mark_published.assert_called_once_with(
        DISPATCH_ID,
        lease_owner="relay-1",
        published_at=NOW,
    )
    repository.release_after_failure.assert_not_called()
    assert tracker.commit_count == 2
    assert tracker.active_count == 0


def test_relay_releases_failed_publish_with_bounded_retry() -> None:
    repository = Mock(spec=DispatchRepository)
    repository.claim_available.return_value = [_dispatch(attempt_count=3)]
    tracker = _TransactionTracker()
    publisher = _RecordingPublisher(
        tracker,
        error=ConnectionError("redis://relay:secret@broker:6379/0 unavailable"),
    )
    relay = OutboxRelay(
        unit_of_work_factory=_UnitOfWorkFactory(repository, tracker),
        publisher=cast(MessagePublisher, publisher),
        relay_id="relay-1",
        clock=lambda: NOW,
        retry_delay=lambda _attempt: timedelta(seconds=7),
    )

    result = relay.run_once()

    assert result == RelayCycleResult(claimed=1, published=0, failed=1)
    repository.release_after_failure.assert_called_once_with(
        DISPATCH_ID,
        lease_owner="relay-1",
        available_at=NOW + timedelta(seconds=7),
        last_error="ConnectionError: redis://<redacted>@broker:6379/0 unavailable",
    )
    repository.mark_published.assert_not_called()
    assert tracker.commit_count == 2
    assert tracker.active_count == 0


def test_relay_continues_after_losing_an_outcome_lease() -> None:
    first = _dispatch()
    second = _dispatch(dispatch_id=OTHER_DISPATCH_ID, batch_id=OTHER_BATCH_ID)
    repository = Mock(spec=DispatchRepository)
    repository.claim_available.return_value = [first, second]
    repository.mark_published.side_effect = [
        InvalidResourceStateError("lease was reclaimed"),
        second,
    ]
    tracker = _TransactionTracker()
    publisher = _RecordingPublisher(tracker)
    relay = OutboxRelay(
        unit_of_work_factory=_UnitOfWorkFactory(repository, tracker),
        publisher=cast(MessagePublisher, publisher),
        relay_id="relay-1",
        clock=lambda: NOW,
    )

    result = relay.run_once()

    assert result == RelayCycleResult(
        claimed=2,
        published=2,
        failed=0,
        lease_conflicts=1,
    )
    assert [published[2] for published in publisher.calls] == [BATCH_ID, OTHER_BATCH_ID]
    assert repository.mark_published.call_args_list == [
        call(DISPATCH_ID, lease_owner="relay-1", published_at=NOW),
        call(OTHER_DISPATCH_ID, lease_owner="relay-1", published_at=NOW),
    ]
    assert tracker.commit_count == 2  # Initial claim plus the second outcome.
    assert tracker.active_count == 0


def test_reconciler_repairs_only_persisted_dispatch_intent() -> None:
    repository = Mock(spec=DispatchRepository)
    repository.ensure_missing.return_value = 2
    repository.rearm_stale_published.return_value = 3
    tracker = _TransactionTracker()
    reconciler = DispatchReconciler(
        unit_of_work_factory=_UnitOfWorkFactory(repository, tracker),
        clock=lambda: NOW,
        published_stale_after=timedelta(minutes=15),
    )

    result = reconciler.run_once(limit=50)

    assert result == ReconciliationResult(missing_created=2, stale_rearmed=3)
    repository.ensure_missing.assert_called_once_with(now=NOW, limit=50)
    repository.rearm_stale_published.assert_called_once_with(
        now=NOW,
        published_before=NOW - timedelta(minutes=15),
        limit=50,
    )
    assert tracker.commit_count == 1
    assert tracker.active_count == 0


@pytest.mark.parametrize(
    ("attempt_count", "expected_seconds"),
    [(1, 1), (2, 2), (5, 16), (8, 60), (10_000, 60)],
)
def test_exponential_retry_delay_is_bounded(
    attempt_count: int,
    expected_seconds: int,
) -> None:
    assert exponential_retry_delay(attempt_count) == timedelta(seconds=expected_seconds)


def test_exponential_retry_delay_handles_timedelta_max_without_overflow() -> None:
    assert (
        exponential_retry_delay(
            10_000,
            base=timedelta(microseconds=1),
            maximum=timedelta.max,
        )
        == timedelta.max
    )


def test_relay_rejects_nonpositive_cycle_limit() -> None:
    repository = Mock(spec=DispatchRepository)
    tracker = _TransactionTracker()
    relay = OutboxRelay(
        unit_of_work_factory=_UnitOfWorkFactory(repository, tracker),
        publisher=cast(MessagePublisher, _RecordingPublisher(tracker)),
        relay_id="relay-1",
        clock=lambda: NOW,
    )

    with pytest.raises(ValueError, match="limit must be positive"):
        relay.run_once(limit=0)
