"""SQLAlchemy repository for durable application-work dispatches."""

from collections.abc import Sequence
from datetime import datetime
from typing import cast, overload
from uuid import UUID, uuid4

from sqlalchemy import Table, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from gendertagger.db.rows.aggregations import AggregationExecutionRow
from gendertagger.db.rows.dispatches import DispatchOutboxRow
from gendertagger.db.rows.evaluations import EvaluationExecutionRow
from gendertagger.db.rows.executions import MethodExecutionRow, RunRow, TaskBatchRow
from gendertagger.db.rows.exports import ExportExecutionRow
from gendertagger.db.rows.projects import DatasetSnapshotRow
from gendertagger.db.rows.public_classification import PublicClassificationJobRow
from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.models.common import normalize_utc_datetime
from gendertagger.models.dispatch import (
    AggregationDispatch,
    AggregationDispatchCreate,
    BatchDispatch,
    BatchDispatchCreate,
    Dispatch,
    DispatchCreate,
    DispatchStatus,
    DispatchTarget,
    EvaluationDispatch,
    EvaluationDispatchCreate,
    ExportDispatch,
    ExportDispatchCreate,
    PublicClassificationDispatch,
    PublicClassificationDispatchCreate,
    SnapshotDispatch,
    SnapshotDispatchCreate,
)
from gendertagger.models.evaluation import EvaluationTaskMessage
from gendertagger.models.export import ExportTaskMessage
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    DatasetSnapshotStatus,
    EvaluationExecutionStatus,
    ExportExecutionStatus,
    MethodExecutionStatus,
    RunStatus,
    TaskBatchStatus,
)
from gendertagger.models.project import SnapshotImportTaskMessage
from gendertagger.models.public_classification import (
    PublicClassificationStatus,
    PublicClassificationTaskMessage,
)
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.models.run import TaskBatchMessage
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

_ACTIVE_RUN_STATUSES = frozenset({RunStatus.queued, RunStatus.running})
_DISPATCHABLE_EXECUTION_STATUSES = frozenset(
    {MethodExecutionStatus.queued, MethodExecutionStatus.running}
)
_DISPATCHABLE_BATCH_STATUSES = frozenset({TaskBatchStatus.pending, TaskBatchStatus.queued})
_DISPATCHABLE_AGGREGATION_STATUSES = frozenset(
    {AggregationExecutionStatus.pending, AggregationExecutionStatus.queued}
)
_DISPATCHABLE_SNAPSHOT_STATUSES = frozenset({DatasetSnapshotStatus.pending})
_DISPATCHABLE_EVALUATION_STATUSES = frozenset(
    {EvaluationExecutionStatus.pending, EvaluationExecutionStatus.queued}
)
_DISPATCHABLE_EXPORT_STATUSES = frozenset(
    {ExportExecutionStatus.pending, ExportExecutionStatus.queued}
)
# Matches the ``String(255)`` width of ``dispatches.lease_owner``.
_LEASE_OWNER_MAX_LENGTH = 255
_STALE_REARM_DIAGNOSTIC = "published dispatch was not claimed before reconciliation timeout"


class SqlAlchemyDispatchRepository:
    """Map dispatch contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @overload
    def ensure_dispatch(self, command: BatchDispatchCreate) -> BatchDispatch: ...

    @overload
    def ensure_dispatch(
        self,
        command: AggregationDispatchCreate,
    ) -> AggregationDispatch: ...

    @overload
    def ensure_dispatch(self, command: SnapshotDispatchCreate) -> SnapshotDispatch: ...

    @overload
    def ensure_dispatch(self, command: EvaluationDispatchCreate) -> EvaluationDispatch: ...

    @overload
    def ensure_dispatch(self, command: ExportDispatchCreate) -> ExportDispatch: ...

    @overload
    def ensure_dispatch(
        self,
        command: PublicClassificationDispatchCreate,
    ) -> PublicClassificationDispatch: ...

    def ensure_dispatch(self, command: DispatchCreate) -> Dispatch:
        """Idempotently persist one exact target-aware dispatch without committing."""
        if isinstance(command, BatchDispatchCreate):
            return self._ensure_batch_dispatch(command)
        if isinstance(command, AggregationDispatchCreate):
            return self._ensure_aggregation_dispatch(command)
        if isinstance(command, SnapshotDispatchCreate):
            return self._ensure_snapshot_dispatch(command)
        if isinstance(command, EvaluationDispatchCreate):
            return self._ensure_evaluation_dispatch(command)
        if isinstance(command, PublicClassificationDispatchCreate):
            return self._ensure_public_classification_dispatch(command)
        return self._ensure_export_dispatch(command)

    def _ensure_public_classification_dispatch(
        self,
        command: PublicClassificationDispatchCreate,
    ) -> PublicClassificationDispatch:
        job = self._session.get(PublicClassificationJobRow, command.classification_job_id)
        if job is None:
            msg = f"classification job {command.classification_job_id} does not exist"
            raise ResourceNotFoundError(msg)
        if job.status not in {
            PublicClassificationStatus.queued,
            PublicClassificationStatus.running,
        }:
            msg = f"classification job {job.id} is not dispatchable from {job.status}"
            raise InvalidResourceStateError(msg)
        if command.queue_name != job.queue_name:
            msg = "public classification dispatch queue must match its persisted job queue"
            raise InvalidResourceStateError(msg)
        dispatch_table = cast(Table, DispatchOutboxRow.__table__)
        self._session.execute(
            insert(dispatch_table)
            .values(
                id=uuid4(),
                classification_job_id=command.classification_job_id,
                queue_name=command.queue_name,
                payload=command.payload.model_dump(mode="json"),
                status=DispatchStatus.pending,
                attempt_count=0,
                available_at=command.available_at,
            )
            .on_conflict_do_nothing(constraint="classification_job_single_dispatch")
        )
        self._session.flush()
        row = self._session.scalar(
            select(DispatchOutboxRow).where(DispatchOutboxRow.classification_job_id == job.id)
        )
        if row is None:  # pragma: no cover - insert/select in one transaction.
            msg = f"dispatch for classification job {job.id} could not be persisted"
            raise RuntimeError(msg)
        self._require_matching_intent(row, command)
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, PublicClassificationDispatch):  # pragma: no cover - invariant.
            msg = f"dispatch for classification job {job.id} has the wrong target type"
            raise RuntimeError(msg)
        return dispatch

    def _ensure_batch_dispatch(self, command: BatchDispatchCreate) -> BatchDispatch:
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

        dispatch_table = cast(Table, DispatchOutboxRow.__table__)
        statement = (
            insert(dispatch_table)
            .values(
                id=uuid4(),
                task_batch_id=command.task_batch_id,
                aggregation_execution_id=None,
                dataset_snapshot_id=None,
                evaluation_execution_id=None,
                export_execution_id=None,
                queue_name=command.queue_name,
                payload=command.payload.model_dump(mode="json"),
                status=DispatchStatus.pending,
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
            select(DispatchOutboxRow).where(DispatchOutboxRow.task_batch_id == batch.id)
        )
        if row is None:  # pragma: no cover - guarded by insert/select in one transaction.
            msg = f"dispatch for task batch {batch.id} could not be persisted"
            raise RuntimeError(msg)
        self._require_matching_intent(row, command)
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, BatchDispatch):  # pragma: no cover - database invariant.
            msg = f"dispatch for task batch {batch.id} has the wrong target type"
            raise RuntimeError(msg)
        return dispatch

    def _ensure_aggregation_dispatch(
        self,
        command: AggregationDispatchCreate,
    ) -> AggregationDispatch:
        aggregation = self._session.get(
            AggregationExecutionRow,
            command.aggregation_execution_id,
        )
        if aggregation is None:
            msg = f"aggregation execution {command.aggregation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if aggregation.status not in _DISPATCHABLE_AGGREGATION_STATUSES:
            msg = (
                f"aggregation execution {aggregation.id} is not dispatchable "
                f"from {aggregation.status}"
            )
            raise InvalidResourceStateError(msg)
        if command.queue_name != CPU_QUEUE:
            msg = f"aggregation dispatches must use the {CPU_QUEUE} queue"
            raise InvalidResourceStateError(msg)

        dispatch_table = cast(Table, DispatchOutboxRow.__table__)
        statement = (
            insert(dispatch_table)
            .values(
                id=uuid4(),
                task_batch_id=None,
                aggregation_execution_id=command.aggregation_execution_id,
                dataset_snapshot_id=None,
                evaluation_execution_id=None,
                export_execution_id=None,
                queue_name=command.queue_name,
                payload=command.payload.model_dump(mode="json"),
                status=DispatchStatus.pending,
                attempt_count=0,
                available_at=command.available_at,
                lease_owner=None,
                lease_until=None,
                published_at=None,
                last_error=None,
            )
            .on_conflict_do_nothing(constraint="aggregation_execution_single_dispatch")
        )
        self._session.execute(statement)
        self._session.flush()
        row = self._session.scalar(
            select(DispatchOutboxRow).where(
                DispatchOutboxRow.aggregation_execution_id == aggregation.id
            )
        )
        if row is None:  # pragma: no cover - guarded by insert/select in one transaction.
            msg = f"dispatch for aggregation execution {aggregation.id} could not be persisted"
            raise RuntimeError(msg)
        self._require_matching_intent(row, command)
        dispatch = self._dispatch_from_row(row)
        if not isinstance(
            dispatch,
            AggregationDispatch,
        ):  # pragma: no cover - database invariant.
            msg = f"dispatch for aggregation execution {aggregation.id} has the wrong target type"
            raise RuntimeError(msg)
        return dispatch

    def _ensure_snapshot_dispatch(
        self,
        command: SnapshotDispatchCreate,
    ) -> SnapshotDispatch:
        snapshot = self._session.get(DatasetSnapshotRow, command.dataset_snapshot_id)
        if snapshot is None:
            msg = f"dataset snapshot {command.dataset_snapshot_id} does not exist"
            raise ResourceNotFoundError(msg)
        if snapshot.status not in _DISPATCHABLE_SNAPSHOT_STATUSES:
            msg = f"dataset snapshot {snapshot.id} is not dispatchable from {snapshot.status}"
            raise InvalidResourceStateError(msg)
        if command.queue_name != CPU_QUEUE:
            msg = f"snapshot import dispatches must use the {CPU_QUEUE} queue"
            raise InvalidResourceStateError(msg)

        dispatch_table = cast(Table, DispatchOutboxRow.__table__)
        statement = (
            insert(dispatch_table)
            .values(
                id=uuid4(),
                task_batch_id=None,
                aggregation_execution_id=None,
                dataset_snapshot_id=command.dataset_snapshot_id,
                evaluation_execution_id=None,
                export_execution_id=None,
                queue_name=command.queue_name,
                payload=command.payload.model_dump(mode="json"),
                status=DispatchStatus.pending,
                attempt_count=0,
                available_at=command.available_at,
                lease_owner=None,
                lease_until=None,
                published_at=None,
                last_error=None,
            )
            .on_conflict_do_nothing(constraint="dataset_snapshot_single_dispatch")
        )
        self._session.execute(statement)
        self._session.flush()
        row = self._session.scalar(
            select(DispatchOutboxRow).where(DispatchOutboxRow.dataset_snapshot_id == snapshot.id)
        )
        if row is None:  # pragma: no cover - guarded by insert/select in one transaction.
            msg = f"dispatch for dataset snapshot {snapshot.id} could not be persisted"
            raise RuntimeError(msg)
        self._require_matching_intent(row, command)
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, SnapshotDispatch):  # pragma: no cover - database invariant.
            msg = f"dispatch for dataset snapshot {snapshot.id} has the wrong target type"
            raise RuntimeError(msg)
        return dispatch

    def _ensure_evaluation_dispatch(
        self,
        command: EvaluationDispatchCreate,
    ) -> EvaluationDispatch:
        evaluation = self._session.get(
            EvaluationExecutionRow,
            command.evaluation_execution_id,
        )
        if evaluation is None:
            msg = f"evaluation execution {command.evaluation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if evaluation.status not in _DISPATCHABLE_EVALUATION_STATUSES:
            msg = (
                f"evaluation execution {evaluation.id} is not dispatchable from {evaluation.status}"
            )
            raise InvalidResourceStateError(msg)
        if command.queue_name != CPU_QUEUE:
            msg = f"evaluation dispatches must use the {CPU_QUEUE} queue"
            raise InvalidResourceStateError(msg)

        dispatch_table = cast(Table, DispatchOutboxRow.__table__)
        statement = (
            insert(dispatch_table)
            .values(
                id=uuid4(),
                task_batch_id=None,
                aggregation_execution_id=None,
                dataset_snapshot_id=None,
                evaluation_execution_id=command.evaluation_execution_id,
                export_execution_id=None,
                queue_name=command.queue_name,
                payload=command.payload.model_dump(mode="json"),
                status=DispatchStatus.pending,
                attempt_count=0,
                available_at=command.available_at,
                lease_owner=None,
                lease_until=None,
                published_at=None,
                last_error=None,
            )
            .on_conflict_do_nothing(constraint="evaluation_execution_single_dispatch")
        )
        self._session.execute(statement)
        self._session.flush()
        row = self._session.scalar(
            select(DispatchOutboxRow).where(
                DispatchOutboxRow.evaluation_execution_id == evaluation.id
            )
        )
        if row is None:  # pragma: no cover - guarded by insert/select in one transaction.
            msg = f"dispatch for evaluation execution {evaluation.id} could not be persisted"
            raise RuntimeError(msg)
        self._require_matching_intent(row, command)
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, EvaluationDispatch):  # pragma: no cover - database invariant.
            msg = f"dispatch for evaluation execution {evaluation.id} has the wrong target type"
            raise RuntimeError(msg)
        return dispatch

    def _ensure_export_dispatch(
        self,
        command: ExportDispatchCreate,
    ) -> ExportDispatch:
        export = self._session.get(ExportExecutionRow, command.export_execution_id)
        if export is None:
            msg = f"export execution {command.export_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if export.status not in _DISPATCHABLE_EXPORT_STATUSES:
            msg = f"export execution {export.id} is not dispatchable from {export.status}"
            raise InvalidResourceStateError(msg)
        if command.queue_name != CPU_QUEUE:
            msg = f"export dispatches must use the {CPU_QUEUE} queue"
            raise InvalidResourceStateError(msg)

        dispatch_table = cast(Table, DispatchOutboxRow.__table__)
        statement = (
            insert(dispatch_table)
            .values(
                id=uuid4(),
                task_batch_id=None,
                aggregation_execution_id=None,
                dataset_snapshot_id=None,
                evaluation_execution_id=None,
                export_execution_id=command.export_execution_id,
                queue_name=command.queue_name,
                payload=command.payload.model_dump(mode="json"),
                status=DispatchStatus.pending,
                attempt_count=0,
                available_at=command.available_at,
                lease_owner=None,
                lease_until=None,
                published_at=None,
                last_error=None,
            )
            .on_conflict_do_nothing(constraint="export_execution_single_dispatch")
        )
        self._session.execute(statement)
        self._session.flush()
        row = self._session.scalar(
            select(DispatchOutboxRow).where(DispatchOutboxRow.export_execution_id == export.id)
        )
        if row is None:  # pragma: no cover - guarded by insert/select in one transaction.
            msg = f"dispatch for export {export.id} could not be persisted"
            raise RuntimeError(msg)
        self._require_matching_intent(row, command)
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, ExportDispatch):  # pragma: no cover - database invariant.
            msg = f"dispatch for export {export.id} has the wrong target type"
            raise RuntimeError(msg)
        return dispatch

    def get_dispatch(self, dispatch_id: UUID) -> Dispatch | None:
        """Return a dispatch contract by ID without exposing its row."""
        row = self._session.get(DispatchOutboxRow, dispatch_id)
        return None if row is None else self._dispatch_from_row(row)

    def get_dispatch_for_batch(self, task_batch_id: UUID) -> BatchDispatch | None:
        """Return the unique dispatch contract for one task batch."""
        row = self._session.scalar(
            select(DispatchOutboxRow).where(DispatchOutboxRow.task_batch_id == task_batch_id)
        )
        if row is None:
            return None
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, BatchDispatch):  # pragma: no cover - query invariant.
            msg = f"dispatch for task batch {task_batch_id} has the wrong target type"
            raise RuntimeError(msg)
        return dispatch

    def get_dispatch_for_aggregation(
        self,
        aggregation_execution_id: UUID,
    ) -> AggregationDispatch | None:
        """Return the unique dispatch contract for one aggregation execution."""
        row = self._session.scalar(
            select(DispatchOutboxRow).where(
                DispatchOutboxRow.aggregation_execution_id == aggregation_execution_id
            )
        )
        if row is None:
            return None
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, AggregationDispatch):  # pragma: no cover - query invariant.
            msg = (
                f"dispatch for aggregation execution {aggregation_execution_id} "
                "has the wrong target type"
            )
            raise RuntimeError(msg)
        return dispatch

    def get_dispatch_for_snapshot(self, dataset_snapshot_id: UUID) -> SnapshotDispatch | None:
        """Return the unique dispatch contract for one dataset-snapshot import."""
        row = self._session.scalar(
            select(DispatchOutboxRow).where(
                DispatchOutboxRow.dataset_snapshot_id == dataset_snapshot_id
            )
        )
        if row is None:
            return None
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, SnapshotDispatch):  # pragma: no cover - query invariant.
            msg = f"dispatch for dataset snapshot {dataset_snapshot_id} has the wrong target type"
            raise RuntimeError(msg)
        return dispatch

    def get_dispatch_for_evaluation(
        self,
        evaluation_execution_id: UUID,
    ) -> EvaluationDispatch | None:
        """Return the unique dispatch contract for one evaluation execution."""
        row = self._session.scalar(
            select(DispatchOutboxRow).where(
                DispatchOutboxRow.evaluation_execution_id == evaluation_execution_id
            )
        )
        if row is None:
            return None
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, EvaluationDispatch):  # pragma: no cover - query invariant.
            msg = (
                f"dispatch for evaluation execution {evaluation_execution_id} "
                "has the wrong target type"
            )
            raise RuntimeError(msg)
        return dispatch

    def get_dispatch_for_export(self, export_execution_id: UUID) -> ExportDispatch | None:
        """Return the unique dispatch contract for one export execution."""
        row = self._session.scalar(
            select(DispatchOutboxRow).where(
                DispatchOutboxRow.export_execution_id == export_execution_id
            )
        )
        if row is None:
            return None
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, ExportDispatch):  # pragma: no cover - query invariant.
            msg = f"dispatch for export {export_execution_id} has the wrong target type"
            raise RuntimeError(msg)
        return dispatch

    def get_dispatch_for_classification(
        self,
        classification_job_id: UUID,
    ) -> PublicClassificationDispatch | None:
        """Return the unique durable dispatch for an anonymous classification job."""
        row = self._session.scalar(
            select(DispatchOutboxRow).where(
                DispatchOutboxRow.classification_job_id == classification_job_id
            )
        )
        if row is None:
            return None
        dispatch = self._dispatch_from_row(row)
        if not isinstance(dispatch, PublicClassificationDispatch):  # pragma: no cover - invariant.
            msg = (
                f"dispatch for classification job {classification_job_id} has the wrong target type"
            )
            raise RuntimeError(msg)
        return dispatch

    def claim_available(
        self,
        *,
        now: datetime,
        lease_owner: str,
        lease_until: datetime,
        limit: int,
    ) -> Sequence[Dispatch]:
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
                select(DispatchOutboxRow)
                .where(
                    DispatchOutboxRow.status == DispatchStatus.pending,
                    DispatchOutboxRow.available_at <= claim_time,
                    or_(
                        DispatchOutboxRow.lease_until.is_(None),
                        DispatchOutboxRow.lease_until <= claim_time,
                    ),
                )
                .order_by(DispatchOutboxRow.available_at, DispatchOutboxRow.id)
                .with_for_update(skip_locked=True, of=DispatchOutboxRow)
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
    ) -> Dispatch:
        """Record broker acceptance when the caller still owns the lease."""
        owner = self._validate_lease_owner(lease_owner)
        publication_time = normalize_utc_datetime(published_at)
        row = self._require_claimed(dispatch_id, owner)
        row.status = DispatchStatus.published
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
    ) -> Dispatch:
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
        """Persist missing intents for dispatchable work using target row locks."""
        available_at = normalize_utc_datetime(now)
        self._validate_limit(limit)
        batch_candidates = (
            select(
                literal(DispatchTarget.task_batch.value).label("target"),
                TaskBatchRow.id.label("target_id"),
                TaskBatchRow.created_at.label("created_at"),
            )
            .join(MethodExecutionRow, MethodExecutionRow.id == TaskBatchRow.method_execution_id)
            .join(RunRow, RunRow.id == MethodExecutionRow.run_id)
            .outerjoin(
                DispatchOutboxRow,
                DispatchOutboxRow.task_batch_id == TaskBatchRow.id,
            )
            .where(
                DispatchOutboxRow.id.is_(None),
                TaskBatchRow.status.in_(_DISPATCHABLE_BATCH_STATUSES),
                MethodExecutionRow.status.in_(_DISPATCHABLE_EXECUTION_STATUSES),
                RunRow.status.in_(_ACTIVE_RUN_STATUSES),
            )
        )
        aggregation_candidates = (
            select(
                literal(DispatchTarget.aggregation_execution.value).label("target"),
                AggregationExecutionRow.id.label("target_id"),
                AggregationExecutionRow.created_at.label("created_at"),
            )
            .outerjoin(
                DispatchOutboxRow,
                DispatchOutboxRow.aggregation_execution_id == AggregationExecutionRow.id,
            )
            .where(
                DispatchOutboxRow.id.is_(None),
                AggregationExecutionRow.status.in_(_DISPATCHABLE_AGGREGATION_STATUSES),
            )
        )
        snapshot_candidates = (
            select(
                literal(DispatchTarget.dataset_snapshot.value).label("target"),
                DatasetSnapshotRow.id.label("target_id"),
                DatasetSnapshotRow.created_at.label("created_at"),
            )
            .outerjoin(
                DispatchOutboxRow,
                DispatchOutboxRow.dataset_snapshot_id == DatasetSnapshotRow.id,
            )
            .where(
                DispatchOutboxRow.id.is_(None),
                DatasetSnapshotRow.status.in_(_DISPATCHABLE_SNAPSHOT_STATUSES),
            )
        )
        evaluation_candidates = (
            select(
                literal(DispatchTarget.evaluation_execution.value).label("target"),
                EvaluationExecutionRow.id.label("target_id"),
                EvaluationExecutionRow.created_at.label("created_at"),
            )
            .outerjoin(
                DispatchOutboxRow,
                DispatchOutboxRow.evaluation_execution_id == EvaluationExecutionRow.id,
            )
            .where(
                DispatchOutboxRow.id.is_(None),
                EvaluationExecutionRow.status.in_(_DISPATCHABLE_EVALUATION_STATUSES),
            )
        )
        export_candidates = (
            select(
                literal(DispatchTarget.export.value).label("target"),
                ExportExecutionRow.id.label("target_id"),
                ExportExecutionRow.created_at.label("created_at"),
            )
            .outerjoin(
                DispatchOutboxRow,
                DispatchOutboxRow.export_execution_id == ExportExecutionRow.id,
            )
            .where(
                DispatchOutboxRow.id.is_(None),
                ExportExecutionRow.status.in_(_DISPATCHABLE_EXPORT_STATUSES),
            )
        )
        classification_candidates = (
            select(
                literal(DispatchTarget.public_classification_job.value).label("target"),
                PublicClassificationJobRow.id.label("target_id"),
                PublicClassificationJobRow.created_at.label("created_at"),
            )
            .outerjoin(
                DispatchOutboxRow,
                DispatchOutboxRow.classification_job_id == PublicClassificationJobRow.id,
            )
            .where(
                DispatchOutboxRow.id.is_(None),
                or_(
                    PublicClassificationJobRow.status == PublicClassificationStatus.queued,
                    (
                        (PublicClassificationJobRow.status == PublicClassificationStatus.running)
                        & (PublicClassificationJobRow.lease_until <= available_at)
                    ),
                ),
            )
        )
        candidates = union_all(
            batch_candidates,
            aggregation_candidates,
            snapshot_candidates,
            evaluation_candidates,
            export_candidates,
            classification_candidates,
        ).subquery()
        rows = tuple(
            self._session.execute(
                select(candidates.c.target, candidates.c.target_id)
                .order_by(candidates.c.created_at, candidates.c.target, candidates.c.target_id)
                .limit(limit)
            )
        )

        created_count = 0
        for target, target_id in rows:
            if target == DispatchTarget.task_batch.value:
                batch = self._lock_dispatchable_batch(target_id)
                if batch is None or self.get_dispatch_for_batch(batch.id) is not None:
                    continue
                self.ensure_dispatch(
                    BatchDispatchCreate(
                        task_batch_id=batch.id,
                        queue_name=batch.queue_name,
                        payload=TaskBatchMessage(
                            method_execution_id=batch.method_execution_id,
                            task_batch_id=batch.id,
                        ),
                        available_at=available_at,
                    )
                )
            elif target == DispatchTarget.aggregation_execution.value:
                aggregation = self._lock_dispatchable_aggregation(target_id)
                if (
                    aggregation is None
                    or self.get_dispatch_for_aggregation(aggregation.id) is not None
                ):
                    continue
                self.ensure_dispatch(
                    AggregationDispatchCreate(
                        aggregation_execution_id=aggregation.id,
                        queue_name=CPU_QUEUE,
                        payload=AggregationTaskMessage(aggregation_execution_id=aggregation.id),
                        available_at=available_at,
                    )
                )
            elif target == DispatchTarget.dataset_snapshot.value:
                snapshot = self._lock_dispatchable_snapshot(target_id)
                if snapshot is None or self.get_dispatch_for_snapshot(snapshot.id) is not None:
                    continue
                self.ensure_dispatch(
                    SnapshotDispatchCreate(
                        dataset_snapshot_id=snapshot.id,
                        queue_name=CPU_QUEUE,
                        payload=SnapshotImportTaskMessage(dataset_snapshot_id=snapshot.id),
                        available_at=available_at,
                    )
                )
            elif target == DispatchTarget.evaluation_execution.value:
                evaluation = self._lock_dispatchable_evaluation(target_id)
                if (
                    evaluation is None
                    or self.get_dispatch_for_evaluation(evaluation.id) is not None
                ):
                    continue
                self.ensure_dispatch(
                    EvaluationDispatchCreate(
                        evaluation_execution_id=evaluation.id,
                        queue_name=CPU_QUEUE,
                        payload=EvaluationTaskMessage(evaluation_execution_id=evaluation.id),
                        available_at=available_at,
                    )
                )
            elif target == DispatchTarget.public_classification_job.value:
                job = self._lock_dispatchable_classification(target_id, now=available_at)
                if job is None or self.get_dispatch_for_classification(job.id) is not None:
                    continue
                self.ensure_dispatch(
                    PublicClassificationDispatchCreate(
                        classification_job_id=job.id,
                        queue_name=job.queue_name,
                        payload=PublicClassificationTaskMessage(classification_job_id=job.id),
                        available_at=available_at,
                    )
                )
            else:
                export = self._lock_dispatchable_export(target_id)
                if export is None or self.get_dispatch_for_export(export.id) is not None:
                    continue
                self.ensure_dispatch(
                    ExportDispatchCreate(
                        export_execution_id=export.id,
                        queue_name=CPU_QUEUE,
                        payload=ExportTaskMessage(export_execution_id=export.id),
                        available_at=available_at,
                    )
                )
            created_count += 1
        return created_count

    def rearm_stale_published(
        self,
        *,
        now: datetime,
        published_before: datetime,
        limit: int,
    ) -> int:
        """Rearm stale publications only while their target work remains unclaimed."""
        rearm_time = normalize_utc_datetime(now)
        stale_before = normalize_utc_datetime(published_before)
        self._validate_limit(limit)
        if stale_before > rearm_time:
            msg = "published_before must not be later than now"
            raise ValueError(msg)

        batch_candidates = (
            select(
                DispatchOutboxRow.id.label("dispatch_id"),
                literal(DispatchTarget.task_batch.value).label("target"),
                TaskBatchRow.id.label("target_id"),
                DispatchOutboxRow.published_at.label("published_at"),
            )
            .join(TaskBatchRow, TaskBatchRow.id == DispatchOutboxRow.task_batch_id)
            .join(MethodExecutionRow, MethodExecutionRow.id == TaskBatchRow.method_execution_id)
            .join(RunRow, RunRow.id == MethodExecutionRow.run_id)
            .where(
                DispatchOutboxRow.status == DispatchStatus.published,
                DispatchOutboxRow.published_at <= stale_before,
                TaskBatchRow.status.in_(_DISPATCHABLE_BATCH_STATUSES),
                MethodExecutionRow.status.in_(_DISPATCHABLE_EXECUTION_STATUSES),
                RunRow.status.in_(_ACTIVE_RUN_STATUSES),
            )
        )
        aggregation_candidates = (
            select(
                DispatchOutboxRow.id.label("dispatch_id"),
                literal(DispatchTarget.aggregation_execution.value).label("target"),
                AggregationExecutionRow.id.label("target_id"),
                DispatchOutboxRow.published_at.label("published_at"),
            )
            .join(
                AggregationExecutionRow,
                AggregationExecutionRow.id == DispatchOutboxRow.aggregation_execution_id,
            )
            .where(
                DispatchOutboxRow.status == DispatchStatus.published,
                DispatchOutboxRow.published_at <= stale_before,
                AggregationExecutionRow.status.in_(_DISPATCHABLE_AGGREGATION_STATUSES),
            )
        )
        snapshot_candidates = (
            select(
                DispatchOutboxRow.id.label("dispatch_id"),
                literal(DispatchTarget.dataset_snapshot.value).label("target"),
                DatasetSnapshotRow.id.label("target_id"),
                DispatchOutboxRow.published_at.label("published_at"),
            )
            .join(
                DatasetSnapshotRow,
                DatasetSnapshotRow.id == DispatchOutboxRow.dataset_snapshot_id,
            )
            .where(
                DispatchOutboxRow.status == DispatchStatus.published,
                DispatchOutboxRow.published_at <= stale_before,
                DatasetSnapshotRow.status.in_(_DISPATCHABLE_SNAPSHOT_STATUSES),
            )
        )
        evaluation_candidates = (
            select(
                DispatchOutboxRow.id.label("dispatch_id"),
                literal(DispatchTarget.evaluation_execution.value).label("target"),
                EvaluationExecutionRow.id.label("target_id"),
                DispatchOutboxRow.published_at.label("published_at"),
            )
            .join(
                EvaluationExecutionRow,
                EvaluationExecutionRow.id == DispatchOutboxRow.evaluation_execution_id,
            )
            .where(
                DispatchOutboxRow.status == DispatchStatus.published,
                DispatchOutboxRow.published_at <= stale_before,
                EvaluationExecutionRow.status.in_(_DISPATCHABLE_EVALUATION_STATUSES),
            )
        )
        export_candidates = (
            select(
                DispatchOutboxRow.id.label("dispatch_id"),
                literal(DispatchTarget.export.value).label("target"),
                ExportExecutionRow.id.label("target_id"),
                DispatchOutboxRow.published_at.label("published_at"),
            )
            .join(
                ExportExecutionRow,
                ExportExecutionRow.id == DispatchOutboxRow.export_execution_id,
            )
            .where(
                DispatchOutboxRow.status == DispatchStatus.published,
                DispatchOutboxRow.published_at <= stale_before,
                ExportExecutionRow.status.in_(_DISPATCHABLE_EXPORT_STATUSES),
            )
        )
        classification_candidates = (
            select(
                DispatchOutboxRow.id.label("dispatch_id"),
                literal(DispatchTarget.public_classification_job.value).label("target"),
                PublicClassificationJobRow.id.label("target_id"),
                DispatchOutboxRow.published_at.label("published_at"),
            )
            .join(
                PublicClassificationJobRow,
                PublicClassificationJobRow.id == DispatchOutboxRow.classification_job_id,
            )
            .where(
                DispatchOutboxRow.status == DispatchStatus.published,
                DispatchOutboxRow.published_at <= stale_before,
                or_(
                    PublicClassificationJobRow.status == PublicClassificationStatus.queued,
                    (
                        (PublicClassificationJobRow.status == PublicClassificationStatus.running)
                        & (PublicClassificationJobRow.lease_until <= rearm_time)
                    ),
                ),
            )
        )
        candidates = union_all(
            batch_candidates,
            aggregation_candidates,
            snapshot_candidates,
            evaluation_candidates,
            export_candidates,
            classification_candidates,
        ).subquery()
        rows = tuple(
            self._session.execute(
                select(
                    candidates.c.dispatch_id,
                    candidates.c.target,
                    candidates.c.target_id,
                )
                .order_by(candidates.c.published_at, candidates.c.dispatch_id)
                .limit(limit)
            )
        )

        rearmed_count = 0
        for dispatch_id, target, target_id in rows:
            if target == DispatchTarget.task_batch.value:
                if self._lock_dispatchable_batch(target_id) is None:
                    continue
            elif target == DispatchTarget.aggregation_execution.value:
                if self._lock_dispatchable_aggregation(target_id) is None:
                    continue
            elif target == DispatchTarget.dataset_snapshot.value:
                if self._lock_dispatchable_snapshot(target_id) is None:
                    continue
            elif target == DispatchTarget.evaluation_execution.value:
                if self._lock_dispatchable_evaluation(target_id) is None:
                    continue
            elif target == DispatchTarget.public_classification_job.value:
                if self._lock_dispatchable_classification(target_id, now=rearm_time) is None:
                    continue
            else:
                if self._lock_dispatchable_export(target_id) is None:
                    continue
            row = self._session.scalar(
                select(DispatchOutboxRow)
                .where(
                    DispatchOutboxRow.id == dispatch_id,
                    DispatchOutboxRow.status == DispatchStatus.published,
                    DispatchOutboxRow.published_at <= stale_before,
                )
                .with_for_update(skip_locked=True, of=DispatchOutboxRow)
            )
            if row is None:
                continue
            row.status = DispatchStatus.pending
            row.available_at = rearm_time
            row.published_at = None
            row.lease_owner = None
            row.lease_until = None
            row.last_error = _STALE_REARM_DIAGNOSTIC
            rearmed_count += 1
        self._session.flush()
        return rearmed_count

    def _lock_dispatchable_batch(self, task_batch_id: UUID) -> TaskBatchRow | None:
        """Lock one still-dispatchable batch without waiting on an active worker."""
        return self._session.scalar(
            select(TaskBatchRow)
            .join(MethodExecutionRow, MethodExecutionRow.id == TaskBatchRow.method_execution_id)
            .join(RunRow, RunRow.id == MethodExecutionRow.run_id)
            .where(
                TaskBatchRow.id == task_batch_id,
                TaskBatchRow.status.in_(_DISPATCHABLE_BATCH_STATUSES),
                MethodExecutionRow.status.in_(_DISPATCHABLE_EXECUTION_STATUSES),
                RunRow.status.in_(_ACTIVE_RUN_STATUSES),
            )
            .with_for_update(skip_locked=True, of=TaskBatchRow)
        )

    def _lock_dispatchable_aggregation(
        self,
        aggregation_execution_id: UUID,
    ) -> AggregationExecutionRow | None:
        """Lock one pending aggregation without waiting on an active worker."""
        return self._session.scalar(
            select(AggregationExecutionRow)
            .where(
                AggregationExecutionRow.id == aggregation_execution_id,
                AggregationExecutionRow.status.in_(_DISPATCHABLE_AGGREGATION_STATUSES),
            )
            .with_for_update(skip_locked=True, of=AggregationExecutionRow)
        )

    def _lock_dispatchable_snapshot(
        self,
        dataset_snapshot_id: UUID,
    ) -> DatasetSnapshotRow | None:
        """Lock one pending snapshot without waiting on an active import worker."""
        return self._session.scalar(
            select(DatasetSnapshotRow)
            .where(
                DatasetSnapshotRow.id == dataset_snapshot_id,
                DatasetSnapshotRow.status.in_(_DISPATCHABLE_SNAPSHOT_STATUSES),
            )
            .with_for_update(skip_locked=True, of=DatasetSnapshotRow)
        )

    def _lock_dispatchable_evaluation(
        self,
        evaluation_execution_id: UUID,
    ) -> EvaluationExecutionRow | None:
        """Lock one pending evaluation without waiting on an active worker."""
        return self._session.scalar(
            select(EvaluationExecutionRow)
            .where(
                EvaluationExecutionRow.id == evaluation_execution_id,
                EvaluationExecutionRow.status.in_(_DISPATCHABLE_EVALUATION_STATUSES),
            )
            .with_for_update(skip_locked=True, of=EvaluationExecutionRow)
        )

    def _lock_dispatchable_export(
        self,
        export_execution_id: UUID,
    ) -> ExportExecutionRow | None:
        """Lock one pending export without waiting on an active worker."""
        return self._session.scalar(
            select(ExportExecutionRow)
            .where(
                ExportExecutionRow.id == export_execution_id,
                ExportExecutionRow.status.in_(_DISPATCHABLE_EXPORT_STATUSES),
            )
            .with_for_update(skip_locked=True, of=ExportExecutionRow)
        )

    def _lock_dispatchable_classification(
        self,
        classification_job_id: UUID,
        *,
        now: datetime,
    ) -> PublicClassificationJobRow | None:
        """Lock queued or expired classification work without waiting on active workers."""
        return self._session.scalar(
            select(PublicClassificationJobRow)
            .where(
                PublicClassificationJobRow.id == classification_job_id,
                or_(
                    PublicClassificationJobRow.status == PublicClassificationStatus.queued,
                    (
                        (PublicClassificationJobRow.status == PublicClassificationStatus.running)
                        & (PublicClassificationJobRow.lease_until <= now)
                    ),
                ),
            )
            .with_for_update(skip_locked=True, of=PublicClassificationJobRow)
        )

    def _require_claimed(self, dispatch_id: UUID, lease_owner: str) -> DispatchOutboxRow:
        row = self._session.get(
            DispatchOutboxRow,
            dispatch_id,
            populate_existing=True,
            with_for_update=True,
        )
        if row is None:
            msg = f"dispatch {dispatch_id} does not exist"
            raise ResourceNotFoundError(msg)
        if row.status is not DispatchStatus.pending or row.lease_owner != lease_owner:
            msg = f"dispatch {dispatch_id} is not leased by {lease_owner}"
            raise InvalidResourceStateError(msg)
        return row

    @staticmethod
    def _require_matching_intent(
        row: DispatchOutboxRow,
        command: DispatchCreate,
    ) -> None:
        persisted = SqlAlchemyDispatchRepository._dispatch_from_row(row)
        if (
            persisted.target != command.target
            or persisted.target_id != command.target_id
            or persisted.queue_name != command.queue_name
            or persisted.payload != command.payload
        ):
            msg = f"{command.target.value} {command.target_id} has a different dispatch intent"
            raise InvalidResourceStateError(msg)

    @staticmethod
    def _validate_lease_owner(lease_owner: str) -> str:
        if not lease_owner.strip():
            msg = "dispatch lease_owner must not be blank"
            raise ValueError(msg)
        if len(lease_owner) > _LEASE_OWNER_MAX_LENGTH:
            msg = f"dispatch lease_owner must not exceed {_LEASE_OWNER_MAX_LENGTH} characters"
            raise ValueError(msg)
        return lease_owner

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if limit <= 0:
            msg = "dispatch claim limit must be positive"
            raise ValueError(msg)

    @staticmethod
    def _dispatch_from_row(row: DispatchOutboxRow) -> Dispatch:
        if (
            row.task_batch_id is not None
            and row.aggregation_execution_id is None
            and row.dataset_snapshot_id is None
            and row.evaluation_execution_id is None
            and row.export_execution_id is None
            and row.classification_job_id is None
        ):
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
        if (
            row.aggregation_execution_id is not None
            and row.task_batch_id is None
            and row.dataset_snapshot_id is None
            and row.evaluation_execution_id is None
            and row.export_execution_id is None
            and row.classification_job_id is None
        ):
            return AggregationDispatch(
                id=row.id,
                aggregation_execution_id=row.aggregation_execution_id,
                queue_name=row.queue_name,
                payload=AggregationTaskMessage.model_validate(row.payload),
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
        if (
            row.dataset_snapshot_id is not None
            and row.task_batch_id is None
            and row.aggregation_execution_id is None
            and row.evaluation_execution_id is None
            and row.export_execution_id is None
            and row.classification_job_id is None
        ):
            return SnapshotDispatch(
                id=row.id,
                dataset_snapshot_id=row.dataset_snapshot_id,
                queue_name=row.queue_name,
                payload=SnapshotImportTaskMessage.model_validate(row.payload),
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
        if (
            row.evaluation_execution_id is not None
            and row.task_batch_id is None
            and row.aggregation_execution_id is None
            and row.dataset_snapshot_id is None
            and row.export_execution_id is None
            and row.classification_job_id is None
        ):
            return EvaluationDispatch(
                id=row.id,
                evaluation_execution_id=row.evaluation_execution_id,
                queue_name=row.queue_name,
                payload=EvaluationTaskMessage.model_validate(row.payload),
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
        if (
            row.export_execution_id is not None
            and row.task_batch_id is None
            and row.aggregation_execution_id is None
            and row.dataset_snapshot_id is None
            and row.evaluation_execution_id is None
            and row.classification_job_id is None
        ):
            return ExportDispatch(
                id=row.id,
                export_execution_id=row.export_execution_id,
                queue_name=row.queue_name,
                payload=ExportTaskMessage.model_validate(row.payload),
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
        if (
            row.classification_job_id is not None
            and row.task_batch_id is None
            and row.aggregation_execution_id is None
            and row.dataset_snapshot_id is None
            and row.evaluation_execution_id is None
            and row.export_execution_id is None
        ):
            return PublicClassificationDispatch(
                id=row.id,
                classification_job_id=row.classification_job_id,
                queue_name=row.queue_name,
                payload=PublicClassificationTaskMessage.model_validate(row.payload),
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
        msg = f"dispatch {row.id} does not reference exactly one work target"
        raise RuntimeError(msg)
