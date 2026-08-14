"""Application repository contract for durable task dispatches."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, overload
from uuid import UUID

from gendertagger.models.dispatch import (
    AggregationDispatch,
    AggregationDispatchCreate,
    BatchDispatch,
    BatchDispatchCreate,
    Dispatch,
    DispatchCreate,
)


class DispatchRepository(Protocol):
    """Persist outbox delivery state without owning the transaction."""

    @overload
    def ensure_dispatch(self, command: BatchDispatchCreate) -> BatchDispatch: ...

    @overload
    def ensure_dispatch(
        self,
        command: AggregationDispatchCreate,
    ) -> AggregationDispatch: ...

    def ensure_dispatch(self, command: DispatchCreate) -> Dispatch:
        """Idempotently persist one exact target-aware dispatch intent."""
        ...

    def get_dispatch(self, dispatch_id: UUID) -> Dispatch | None:
        """Return a dispatch by ID, or ``None`` when absent."""
        ...

    def get_dispatch_for_batch(self, task_batch_id: UUID) -> BatchDispatch | None:
        """Return the unique dispatch for a task batch, or ``None`` when absent."""
        ...

    def get_dispatch_for_aggregation(
        self,
        aggregation_execution_id: UUID,
    ) -> AggregationDispatch | None:
        """Return the unique dispatch for an aggregation, or ``None`` when absent."""
        ...

    def claim_available(
        self,
        *,
        now: datetime,
        lease_owner: str,
        lease_until: datetime,
        limit: int,
    ) -> Sequence[Dispatch]:
        """Lease an ordered available slice using nonblocking row locks."""
        ...

    def mark_published(
        self,
        dispatch_id: UUID,
        *,
        lease_owner: str,
        published_at: datetime,
    ) -> Dispatch:
        """Record successful broker publication by the current lease owner."""
        ...

    def release_after_failure(
        self,
        dispatch_id: UUID,
        *,
        lease_owner: str,
        available_at: datetime,
        last_error: str,
    ) -> Dispatch:
        """Release a failed attempt for a caller-selected retry instant."""
        ...

    def ensure_missing(self, *, now: datetime, limit: int) -> int:
        """Create missing dispatch intents for active, dispatchable work."""
        ...

    def rearm_stale_published(
        self,
        *,
        now: datetime,
        published_before: datetime,
        limit: int,
    ) -> int:
        """Rearm old published messages whose target work remains unclaimed."""
        ...
