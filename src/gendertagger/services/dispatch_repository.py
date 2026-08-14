"""Application repository contract for durable task-batch dispatches."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.dispatch import BatchDispatch, BatchDispatchCreate


class DispatchRepository(Protocol):
    """Persist outbox delivery state without owning the transaction."""

    def ensure_dispatch(self, command: BatchDispatchCreate) -> BatchDispatch:
        """Idempotently persist the unique dispatch intent for one task batch."""
        ...

    def get_dispatch(self, dispatch_id: UUID) -> BatchDispatch | None:
        """Return a dispatch by ID, or ``None`` when absent."""
        ...

    def get_dispatch_for_batch(self, task_batch_id: UUID) -> BatchDispatch | None:
        """Return the unique dispatch for a task batch, or ``None`` when absent."""
        ...

    def claim_available(
        self,
        *,
        now: datetime,
        lease_owner: str,
        lease_until: datetime,
        limit: int,
    ) -> Sequence[BatchDispatch]:
        """Lease an ordered available slice using nonblocking row locks."""
        ...

    def mark_published(
        self,
        dispatch_id: UUID,
        *,
        lease_owner: str,
        published_at: datetime,
    ) -> BatchDispatch:
        """Record successful broker publication by the current lease owner."""
        ...

    def release_after_failure(
        self,
        dispatch_id: UUID,
        *,
        lease_owner: str,
        available_at: datetime,
        last_error: str,
    ) -> BatchDispatch:
        """Release a failed attempt for a caller-selected retry instant."""
        ...

    def ensure_missing(self, *, now: datetime, limit: int) -> int:
        """Create missing dispatch intents for active, dispatchable batches."""
        ...

    def rearm_stale_published(
        self,
        *,
        now: datetime,
        published_before: datetime,
        limit: int,
    ) -> int:
        """Rearm old published messages whose batches remain unclaimed."""
        ...
