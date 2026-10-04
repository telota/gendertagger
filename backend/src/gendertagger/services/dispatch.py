"""Reliable publication and reconciliation of persisted task dispatches."""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from gendertagger.models.common import UtcDatetime
from gendertagger.models.dispatch import DispatchMessage
from gendertagger.services.diagnostics import sanitized_diagnostic
from gendertagger.services.ports.persistence_errors import InvalidResourceStateError
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

Clock = Callable[[], UtcDatetime]
RetryDelay = Callable[[int], timedelta]


class MessagePublisher(Protocol):
    """Publish one validated task envelope to the configured message broker."""

    def publish(
        self,
        message: DispatchMessage,
        *,
        queue_name: str,
        task_id: UUID,
    ) -> None:
        """Publish one task message using its stable work identifier."""
        ...


@dataclass(frozen=True, slots=True)
class RelayCycleResult:
    """Counts produced by one bounded outbox relay cycle."""

    claimed: int
    published: int
    failed: int
    lease_conflicts: int = 0


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Counts produced by one bounded dispatch reconciliation cycle."""

    missing_created: int
    stale_rearmed: int


def exponential_retry_delay(
    attempt_count: int,
    *,
    base: timedelta = timedelta(seconds=1),
    maximum: timedelta = timedelta(seconds=60),
) -> timedelta:
    """Return a bounded exponential delay for a one-based dispatch attempt."""
    if attempt_count < 1:
        msg = "attempt_count must be positive"
        raise ValueError(msg)
    if base <= timedelta(0):
        msg = "base retry delay must be positive"
        raise ValueError(msg)
    if maximum < base:
        msg = "maximum retry delay must not be less than the base delay"
        raise ValueError(msg)
    delay = base
    remaining_doublings = attempt_count - 1
    while remaining_doublings and delay < maximum:
        if delay >= maximum - delay:
            return maximum
        delay += delay
        remaining_doublings -= 1
    return delay


def jittered_exponential_retry_delay(
    attempt_count: int,
    *,
    base: timedelta = timedelta(seconds=1),
    maximum: timedelta = timedelta(seconds=60),
) -> timedelta:
    """Return full jitter within the bounded exponential retry window."""
    ceiling = exponential_retry_delay(attempt_count, base=base, maximum=maximum)
    seconds = random.uniform(  # noqa: S311 - retry jitter is not security-sensitive
        0.0,
        ceiling.total_seconds(),
    )
    return timedelta(seconds=seconds)


class OutboxRelay:
    """Lease pending outbox rows, publish them, and persist each outcome.

    Claiming and outcome recording use separate unit-of-work scopes. Broker I/O
    deliberately occurs between those scopes, so a slow or unavailable broker
    never holds a PostgreSQL transaction or row lock open.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        publisher: MessagePublisher,
        relay_id: str,
        clock: Clock,
        lease_duration: timedelta = timedelta(seconds=30),
        retry_delay: RetryDelay = exponential_retry_delay,
    ) -> None:
        if not relay_id.strip():
            msg = "relay_id must not be blank"
            raise ValueError(msg)
        if lease_duration <= timedelta(0):
            msg = "lease_duration must be positive"
            raise ValueError(msg)
        self._unit_of_work_factory = unit_of_work_factory
        self._publisher = publisher
        self._relay_id = relay_id
        self._clock = clock
        self._lease_duration = lease_duration
        self._retry_delay = retry_delay

    def run_once(self, *, limit: int = 100) -> RelayCycleResult:
        """Publish at most ``limit`` available dispatches and persist outcomes."""
        if limit < 1:
            msg = "relay cycle limit must be positive"
            raise ValueError(msg)

        claimed_at = self._clock()
        with self._unit_of_work_factory() as unit_of_work:
            claimed = tuple(
                unit_of_work.dispatches.claim_available(
                    now=claimed_at,
                    lease_owner=self._relay_id,
                    lease_until=claimed_at + self._lease_duration,
                    limit=limit,
                )
            )
            unit_of_work.commit()

        published_count = 0
        failed_count = 0
        lease_conflict_count = 0
        for dispatch in claimed:
            try:
                self._publisher.publish(
                    dispatch.payload,
                    queue_name=dispatch.queue_name,
                    task_id=dispatch.target_id,
                )
            # Broker failures are unbounded; each is recorded on the dispatch for a later retry.
            except Exception as error:  # noqa: BLE001
                failed_count += 1
                failed_at = self._clock()
                try:
                    with self._unit_of_work_factory() as unit_of_work:
                        unit_of_work.dispatches.release_after_failure(
                            dispatch.id,
                            lease_owner=self._relay_id,
                            available_at=failed_at + self._retry_delay(dispatch.attempt_count),
                            last_error=sanitized_diagnostic(error),
                        )
                        unit_of_work.commit()
                except InvalidResourceStateError:
                    lease_conflict_count += 1
            else:
                published_count += 1
                try:
                    with self._unit_of_work_factory() as unit_of_work:
                        unit_of_work.dispatches.mark_published(
                            dispatch.id,
                            lease_owner=self._relay_id,
                            published_at=self._clock(),
                        )
                        unit_of_work.commit()
                except InvalidResourceStateError:
                    lease_conflict_count += 1

        return RelayCycleResult(
            claimed=len(claimed),
            published=published_count,
            failed=failed_count,
            lease_conflicts=lease_conflict_count,
        )


class DispatchReconciler:
    """Repair missing dispatch intent and rearm stale published messages."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        published_stale_after: timedelta = timedelta(minutes=10),
    ) -> None:
        if published_stale_after <= timedelta(0):
            msg = "published_stale_after must be positive"
            raise ValueError(msg)
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._published_stale_after = published_stale_after

    def run_once(self, *, limit: int = 100) -> ReconciliationResult:
        """Repair at most ``limit`` missing and stale dispatch rows each."""
        if limit < 1:
            msg = "reconciliation cycle limit must be positive"
            raise ValueError(msg)

        now = self._clock()
        with self._unit_of_work_factory() as unit_of_work:
            missing_created = unit_of_work.dispatches.ensure_missing(now=now, limit=limit)
            stale_rearmed = unit_of_work.dispatches.rearm_stale_published(
                now=now,
                published_before=now - self._published_stale_after,
                limit=limit,
            )
            unit_of_work.commit()
        return ReconciliationResult(
            missing_created=missing_created,
            stale_rearmed=stale_rearmed,
        )
