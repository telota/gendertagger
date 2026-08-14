"""SQLAlchemy repository for durable task-batch dispatches."""

from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Table, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from gendertagger.db.dispatches import BatchDispatchRow
from gendertagger.db.executions import MethodExecutionRow, RunRow, TaskBatchRow
from gendertagger.models.common import normalize_utc_datetime
from gendertagger.models.dispatch import (
    BatchDispatch,
    BatchDispatchCreate,
    BatchDispatchStatus,
)
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus
from gendertagger.models.run import TaskBatchMessage
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

_ACTIVE_RUN_STATUSES = frozenset({RunStatus.queued, RunStatus.running})
_DISPATCHABLE_EXECUTION_STATUSES = frozenset(
    {MethodExecutionStatus.queued, MethodExecutionStatus.running}
)
_DISPATCHABLE_BATCH_STATUSES = frozenset({TaskBatchStatus.pending, TaskBatchStatus.queued})
_STALE_REARM_DIAGNOSTIC = "published dispatch was not claimed before reconciliation timeout"


class SqlAlchemyDispatchRepository:
    """Map dispatch contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_dispatch(self, command: BatchDispatchCreate) -> BatchDispatch:
        """Idempotently persist one exact dispatch without committing."""
        batch = self._session.get(TaskBatchRow, command.task_batch_id)
        if batch is None:
            msg = f"task batch {command.task_batch_id} does not exist"
            raise ResourceNotFoundError(msg)
        if batch.status not in _DISPATCHABLE_BATCH_STATUSES:
            msg = f"task batch {batch.id} is not dispatchable from {batch.status}"
            raise InvalidResourceStateError(msg)
        if batch.queue_name != command.queue_name:
            msg = "dispatch queue must match its task batch queue"
            raise InvalidResourceStateError(msg)
        if batch.method_execution_id != command.payload.method_execution_id:
            msg = "dispatch payload method_execution_id must own its task batch"
            raise InvalidResourceStateError(msg)

        dispatch_table = cast(Table, BatchDispatchRow.__table__)
        statement = (
            insert(dispatch_table)
            .values(
                id=uuid4(),
                task_batch_id=command.task_batch_id,
                queue_name=command.queue_name,
                payload=command.payload.model_dump(mode="json"),
                status=BatchDispatchStatus.pending,
                attempt_count=0,
                available_at=command.available_at,
                lease_owner=None,
                lease_until=None,
                published_at=None,
                last_error=None,
            )
            .on_conflict_do_nothing(constraint="task_batch_single_dispatch")
        )
        self._session.execute(statement)
        self._session.flush()
        row = self._session.scalar(
            select(BatchDispatchRow).where(BatchDispatchRow.task_batch_id == batch.id)
        )
        if row is None:  # pragma: no cover - guarded by insert/select in one transaction.
            msg = f"dispatch for task batch {batch.id} could not be persisted"
            raise RuntimeError(msg)
        self._require_matching_intent(row, command)
        return self._dispatch_from_row(row)

    def get_dispatch(self, dispatch_id: UUID) -> BatchDispatch | None:
        """Return a dispatch contract by ID without exposing its row."""
        row = self._session.get(BatchDispatchRow, dispatch_id)
        return None if row is None else self._dispatch_from_row(row)

    def get_dispatch_for_batch(self, task_batch_id: UUID) -> BatchDispatch | None:
        """Return the unique dispatch contract for one task batch."""
        row = self._session.scalar(
            select(BatchDispatchRow).where(BatchDispatchRow.task_batch_id == task_batch_id)
        )
        return None if row is None else self._dispatch_from_row(row)

    def claim_available(
        self,
        *,
        now: datetime,
        lease_owner: str,
        lease_until: datetime,
        limit: int,
    ) -> Sequence[BatchDispatch]:
        """Lease an ordered available slice without waiting on other relays."""
        claim_time = normalize_utc_datetime(now)
        lease_expiry = normalize_utc_datetime(lease_until)
        owner = self._validate_lease_owner(lease_owner)
        self._validate_limit(limit)
        if lease_expiry <= claim_time:
            msg = "dispatch lease_until must be later than now"
            raise ValueError(msg)

        rows = tuple(
            self._session.scalars(
                select(BatchDispatchRow)
                .where(
                    BatchDispatchRow.status == BatchDispatchStatus.pending,
                    BatchDispatchRow.available_at <= claim_time,
                    or_(
                        BatchDispatchRow.lease_until.is_(None),
                        BatchDispatchRow.lease_until <= claim_time,
                    ),
                )
                .order_by(BatchDispatchRow.available_at, BatchDispatchRow.id)
                .with_for_update(skip_locked=True, of=BatchDispatchRow)
                .limit(limit)
            )
        )
        for row in rows:
            row.lease_owner = owner
            row.lease_until = lease_expiry
            row.attempt_count += 1
        self._session.flush()
        return tuple(self._dispatch_from_row(row) for row in rows)

    def mark_published(
        self,
        dispatch_id: UUID,
        *,
        lease_owner: str,
        published_at: datetime,
    ) -> BatchDispatch:
        """Record broker acceptance when the caller still owns the lease."""
        owner = self._validate_lease_owner(lease_owner)
        publication_time = normalize_utc_datetime(published_at)
        row = self._require_claimed(dispatch_id, owner)
        row.status = BatchDispatchStatus.published
        row.published_at = publication_time
        row.lease_owner = None
        row.lease_until = None
        row.last_error = None
        self._session.flush()
        return self._dispatch_from_row(row)

    def release_after_failure(
        self,
        dispatch_id: UUID,
        *,
        lease_owner: str,
        available_at: datetime,
        last_error: str,
    ) -> BatchDispatch:
        """Release a failed publication attempt without committing."""
        owner = self._validate_lease_owner(lease_owner)
        retry_time = normalize_utc_datetime(available_at)
        if not last_error.strip():
            msg = "dispatch last_error must not be blank"
            raise ValueError(msg)
        row = self._require_claimed(dispatch_id, owner)
        row.available_at = retry_time
        row.lease_owner = None
        row.lease_until = None
        row.last_error = last_error
        self._session.flush()
        return self._dispatch_from_row(row)

    def ensure_missing(self, *, now: datetime, limit: int) -> int:
        """Persist missing intents for active batches using skip-locked repair."""
        available_at = normalize_utc_datetime(now)
        self._validate_limit(limit)
        rows = tuple(
            self._session.scalars(
                select(TaskBatchRow)
                .join(MethodExecutionRow, MethodExecutionRow.id == TaskBatchRow.method_execution_id)
                .join(RunRow, RunRow.id == MethodExecutionRow.run_id)
                .outerjoin(
                    BatchDispatchRow,
                    BatchDispatchRow.task_batch_id == TaskBatchRow.id,
                )
                .where(
                    BatchDispatchRow.id.is_(None),
                    TaskBatchRow.status.in_(_DISPATCHABLE_BATCH_STATUSES),
                    MethodExecutionRow.status.in_(_DISPATCHABLE_EXECUTION_STATUSES),
                    RunRow.status.in_(_ACTIVE_RUN_STATUSES),
                )
                .order_by(TaskBatchRow.created_at, TaskBatchRow.id)
                .with_for_update(skip_locked=True, of=TaskBatchRow)
                .limit(limit)
            )
        )
        for row in rows:
            self.ensure_dispatch(
                BatchDispatchCreate(
                    task_batch_id=row.id,
                    queue_name=row.queue_name,
                    payload=TaskBatchMessage(
                        method_execution_id=row.method_execution_id,
                        task_batch_id=row.id,
                    ),
                    available_at=available_at,
                )
            )
        return len(rows)

    def rearm_stale_published(
        self,
        *,
        now: datetime,
        published_before: datetime,
        limit: int,
    ) -> int:
        """Rearm stale publication records only while their batches are unclaimed."""
        rearm_time = normalize_utc_datetime(now)
        stale_before = normalize_utc_datetime(published_before)
        self._validate_limit(limit)
        if stale_before > rearm_time:
            msg = "published_before must not be later than now"
            raise ValueError(msg)

        rows = tuple(
            self._session.scalars(
                select(BatchDispatchRow)
                .join(TaskBatchRow, TaskBatchRow.id == BatchDispatchRow.task_batch_id)
                .join(MethodExecutionRow, MethodExecutionRow.id == TaskBatchRow.method_execution_id)
                .join(RunRow, RunRow.id == MethodExecutionRow.run_id)
                .where(
                    BatchDispatchRow.status == BatchDispatchStatus.published,
                    BatchDispatchRow.published_at <= stale_before,
                    TaskBatchRow.status.in_(_DISPATCHABLE_BATCH_STATUSES),
                    MethodExecutionRow.status.in_(_DISPATCHABLE_EXECUTION_STATUSES),
                    RunRow.status.in_(_ACTIVE_RUN_STATUSES),
                )
                .order_by(BatchDispatchRow.published_at, BatchDispatchRow.id)
                .with_for_update(
                    skip_locked=True,
                    of=(BatchDispatchRow, TaskBatchRow),
                )
                .limit(limit)
            )
        )
        for row in rows:
            row.status = BatchDispatchStatus.pending
            row.available_at = rearm_time
            row.published_at = None
            row.lease_owner = None
            row.lease_until = None
            row.last_error = _STALE_REARM_DIAGNOSTIC
        self._session.flush()
        return len(rows)

    def _require_claimed(self, dispatch_id: UUID, lease_owner: str) -> BatchDispatchRow:
        row = self._session.get(
            BatchDispatchRow,
            dispatch_id,
            populate_existing=True,
            with_for_update=True,
        )
        if row is None:
            msg = f"dispatch {dispatch_id} does not exist"
            raise ResourceNotFoundError(msg)
        if row.status is not BatchDispatchStatus.pending or row.lease_owner != lease_owner:
            msg = f"dispatch {dispatch_id} is not leased by {lease_owner}"
            raise InvalidResourceStateError(msg)
        return row

    @staticmethod
    def _require_matching_intent(
        row: BatchDispatchRow,
        command: BatchDispatchCreate,
    ) -> None:
        payload = TaskBatchMessage.model_validate(row.payload)
        if row.queue_name != command.queue_name or payload != command.payload:
            msg = f"task batch {command.task_batch_id} already has a different dispatch intent"
            raise InvalidResourceStateError(msg)

    @staticmethod
    def _validate_lease_owner(lease_owner: str) -> str:
        if not lease_owner.strip():
            msg = "dispatch lease_owner must not be blank"
            raise ValueError(msg)
        if len(lease_owner) > 255:
            msg = "dispatch lease_owner must not exceed 255 characters"
            raise ValueError(msg)
        return lease_owner

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if limit <= 0:
            msg = "dispatch claim limit must be positive"
            raise ValueError(msg)

    @staticmethod
    def _dispatch_from_row(row: BatchDispatchRow) -> BatchDispatch:
        return BatchDispatch(
            id=row.id,
            task_batch_id=row.task_batch_id,
            queue_name=row.queue_name,
            payload=TaskBatchMessage.model_validate(row.payload),
            status=row.status,
            attempt_count=row.attempt_count,
            available_at=row.available_at,
            lease_owner=row.lease_owner,
            lease_until=row.lease_until,
            published_at=row.published_at,
            last_error=row.last_error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
