"""SQLAlchemy repository for runs, method executions, batches, and predictions."""

from collections.abc import Collection, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Table, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from gendertagger.config.run import RunConfig
from gendertagger.db.executions import MethodExecutionRow, PredictionRow, RunRow, TaskBatchRow
from gendertagger.db.projects import DatasetSnapshotRow, PersonRecordRow
from gendertagger.models.lifecycle import (
    DatasetSnapshotStatus,
    MethodExecutionStatus,
    RunStatus,
    TaskBatchStatus,
)
from gendertagger.models.run import (
    MethodExecution,
    MethodExecutionCreate,
    Prediction,
    PredictionWrite,
    Progress,
    Run,
    RunCreate,
    TaskBatch,
    TaskBatchCreate,
    TaskBatchPlan,
)
from gendertagger.services.persistence_errors import (
    ImmutableResourceError,
    InvalidResourceStateError,
    ResourceNotFoundError,
)

_RUN_TERMINAL_STATUSES = frozenset(
    {RunStatus.completed, RunStatus.completed_with_errors, RunStatus.failed}
)
_EXECUTION_TERMINAL_STATUSES = frozenset(
    {
        MethodExecutionStatus.completed,
        MethodExecutionStatus.completed_with_errors,
        MethodExecutionStatus.failed,
    }
)
_BATCH_TERMINAL_STATUSES = frozenset({TaskBatchStatus.completed, TaskBatchStatus.failed})
_RUN_CHILD_CREATION_STATUSES = frozenset({RunStatus.created, RunStatus.queued, RunStatus.running})
_EXECUTION_CHILD_CREATION_STATUSES = frozenset(
    {
        MethodExecutionStatus.pending,
        MethodExecutionStatus.queued,
        MethodExecutionStatus.running,
    }
)


class SqlAlchemyRunRepository:
    """Map execution contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_run(self, command: RunCreate) -> Run:
        """Persist and flush a run only when its exact snapshot is ready."""
        snapshot = self._session.get(DatasetSnapshotRow, command.dataset_snapshot_id)
        if snapshot is None:
            msg = f"dataset snapshot {command.dataset_snapshot_id} does not exist"
            raise ResourceNotFoundError(msg)
        if snapshot.status is not DatasetSnapshotStatus.ready:
            msg = f"dataset snapshot {snapshot.id} is not ready"
            raise InvalidResourceStateError(msg)

        row = RunRow(
            dataset_snapshot_id=command.dataset_snapshot_id,
            status=RunStatus.created,
            resolved_config=command.resolved_config.model_dump(mode="json"),
            config_sha256=command.resolved_config.canonical_sha256(),
            code_git_commit=command.code_git_commit,
            application_version=command.application_version,
            container_image_digest=command.container_image_digest,
            python_version=command.python_version,
            dependency_lock_sha256=command.dependency_lock_sha256,
            dependency_lock_artifact_id=command.dependency_lock_artifact_id,
            started_at=None,
            finished_at=None,
            failure_diagnostic=None,
        )
        self._session.add(row)
        self._session.flush()
        return self._run_from_row(row)

    def get_run(self, run_id: UUID) -> Run | None:
        """Return a run contract by ID without exposing its row."""
        row = self._session.get(RunRow, run_id)
        return None if row is None else self._run_from_row(row)

    def add_method_execution(self, command: MethodExecutionCreate) -> MethodExecution:
        """Persist and flush one configured method execution without committing."""
        run = self._session.scalar(
            select(RunRow)
            .where(RunRow.id == command.run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None:
            msg = f"run {command.run_id} does not exist"
            raise ResourceNotFoundError(msg)
        if run.status not in _RUN_CHILD_CREATION_STATUSES:
            msg = f"run {command.run_id} cannot add method executions from {run.status.value}"
            raise InvalidResourceStateError(msg)
        run_config = RunConfig.model_validate(run.resolved_config)
        enabled_method_names = {method.name for method in run_config.methods if method.enabled}
        if command.descriptor.name not in enabled_method_names:
            msg = f"method {command.descriptor.name} is not enabled in run {command.run_id}"
            raise InvalidResourceStateError(msg)

        row = MethodExecutionRow(
            run_id=command.run_id,
            method_name=command.descriptor.name,
            implementation_version=command.descriptor.implementation_version,
            normalization_version=command.descriptor.normalization_version,
            resolved_config=command.resolved_config,
            config_sha256=command.config_sha256(),
            status=MethodExecutionStatus.pending,
            queue_name=command.queue_name,
            model_identifier=command.model_identifier,
            model_revision=command.model_revision,
            model_checksum=command.model_checksum,
            model_artifact_id=command.model_artifact_id,
            data_artifact_id=command.data_artifact_id,
            prompt_version=command.prompt_version,
            schema_version=command.schema_version,
            worker_metadata=command.worker_metadata,
            total_count=command.total_count,
            completed_count=0,
            failed_count=0,
            started_at=None,
            finished_at=None,
            failure_class=None,
            failure_diagnostic=None,
        )
        self._session.add(row)
        self._session.flush()
        return self._method_execution_from_row(row)

    def get_method_execution(self, method_execution_id: UUID) -> MethodExecution | None:
        """Return a method execution contract by ID without exposing its row."""
        row = self._session.get(MethodExecutionRow, method_execution_id)
        return None if row is None else self._method_execution_from_row(row)

    def list_method_executions(self, run_id: UUID) -> list[MethodExecution]:
        """Return a run's method executions in stable method-name order."""
        rows = self._session.scalars(
            select(MethodExecutionRow)
            .where(MethodExecutionRow.run_id == run_id)
            .order_by(MethodExecutionRow.method_name)
        )
        return [self._method_execution_from_row(row) for row in rows]

    def add_task_batch(self, command: TaskBatchCreate) -> TaskBatch:
        """Persist and flush one retryable task batch without committing."""
        execution = self._session.scalar(
            select(MethodExecutionRow)
            .where(MethodExecutionRow.id == command.method_execution_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if execution is None:
            msg = f"method execution {command.method_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if execution.status not in _EXECUTION_CHILD_CREATION_STATUSES:
            msg = (
                f"method execution {command.method_execution_id} cannot add task batches "
                f"from {execution.status.value}"
            )
            raise InvalidResourceStateError(msg)
        if execution.queue_name != command.queue_name:
            msg = "task batch queue must match its method execution queue"
            raise InvalidResourceStateError(msg)

        row = TaskBatchRow(
            method_execution_id=command.method_execution_id,
            batch_index=command.batch_index,
            status=TaskBatchStatus.pending,
            queue_name=command.queue_name,
            record_offset=command.record_offset,
            record_count=command.record_count,
            worker_task_id=None,
            attempt_count=0,
            success_count=0,
            abstain_count=0,
            error_count=0,
            started_at=None,
            finished_at=None,
            failure_class=None,
            failure_diagnostic=None,
        )
        self._session.add(row)
        self._session.flush()
        return self._task_batch_from_row(row)

    def get_task_batch(self, task_batch_id: UUID) -> TaskBatch | None:
        """Return a task batch contract by ID without exposing its row."""
        row = self._session.get(TaskBatchRow, task_batch_id)
        return None if row is None else self._task_batch_from_row(row)

    def create_task_batches(
        self,
        method_execution_id: UUID,
        plans: Sequence[TaskBatchPlan],
    ) -> list[TaskBatch]:
        """Idempotently persist a planned batch set and return it in index order.

        Re-planning with an identical batch size is a no-op: conflicting
        ``(method_execution_id, batch_index)`` rows are kept, not rewritten.
        """
        execution = self._session.scalar(
            select(MethodExecutionRow)
            .where(MethodExecutionRow.id == method_execution_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if execution is None:
            msg = f"method execution {method_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if execution.status not in _EXECUTION_CHILD_CREATION_STATUSES:
            msg = (
                f"method execution {method_execution_id} cannot plan task batches "
                f"from {execution.status.value}"
            )
            raise InvalidResourceStateError(msg)
        if plans:
            if len({plan.batch_index for plan in plans}) != len(plans):
                msg = "a batch plan must contain each batch index at most once"
                raise ValueError(msg)
            payloads: list[dict[str, object]] = [
                {
                    "id": uuid4(),
                    "method_execution_id": method_execution_id,
                    "batch_index": plan.batch_index,
                    "status": TaskBatchStatus.pending,
                    "queue_name": execution.queue_name,
                    "record_offset": plan.record_offset,
                    "record_count": plan.record_count,
                }
                for plan in plans
            ]
            task_batch_table = cast(Table, TaskBatchRow.__table__)
            statement = (
                insert(task_batch_table)
                .values(payloads)
                .on_conflict_do_nothing(constraint="execution_batch_index")
            )
            self._session.execute(statement)
            self._session.flush()
        rows = self._session.scalars(
            select(TaskBatchRow)
            .where(TaskBatchRow.method_execution_id == method_execution_id)
            .order_by(TaskBatchRow.batch_index)
        )
        return [self._task_batch_from_row(row) for row in rows]

    def mark_run_queued(self, run_id: UUID) -> Run:
        """Atomically claim a created run for one scheduling transaction."""
        statement = (
            update(RunRow)
            .where(RunRow.id == run_id, RunRow.status == RunStatus.created)
            .values(status=RunStatus.queued)
            .returning(RunRow)
            .execution_options(populate_existing=True)
        )
        row = self._session.scalar(statement)
        if row is not None:
            self._session.flush()
            return self._run_from_row(row)

        existing = self._session.scalar(
            select(RunRow).where(RunRow.id == run_id).execution_options(populate_existing=True)
        )
        if existing is None:
            msg = f"run {run_id} does not exist"
            raise ResourceNotFoundError(msg)
        self._require_source(
            "run",
            run_id,
            existing.status,
            {RunStatus.created},
            RunStatus.queued,
        )
        raise AssertionError("unreachable run scheduling transition")

    def mark_run_started(self, run_id: UUID, *, started_at: datetime) -> Run:
        """Transition a queued run to running and record its start time."""
        row = self._require_run(run_id)
        self._require_source("run", run_id, row.status, {RunStatus.queued}, RunStatus.running)
        row.status = RunStatus.running
        row.started_at = started_at
        self._session.flush()
        return self._run_from_row(row)

    def mark_run_finished(
        self,
        run_id: UUID,
        *,
        status: RunStatus,
        finished_at: datetime,
        failure_diagnostic: str | None = None,
    ) -> Run:
        """Transition a running run to a terminal outcome."""
        if status not in _RUN_TERMINAL_STATUSES:
            msg = f"{status} is not a terminal run status"
            raise ValueError(msg)
        row = self._require_run(run_id)
        self._require_source("run", run_id, row.status, {RunStatus.running}, status)
        if status is RunStatus.failed and not (failure_diagnostic and failure_diagnostic.strip()):
            msg = "a failed run requires a failure diagnostic"
            raise ValueError(msg)
        row.status = status
        row.finished_at = finished_at
        row.failure_diagnostic = failure_diagnostic if status is RunStatus.failed else None
        self._session.flush()
        return self._run_from_row(row)

    def mark_execution_queued(self, method_execution_id: UUID) -> MethodExecution:
        """Transition a pending method execution to queued."""
        row = self._require_execution(method_execution_id)
        self._require_source(
            "method execution",
            method_execution_id,
            row.status,
            {MethodExecutionStatus.pending},
            MethodExecutionStatus.queued,
        )
        row.status = MethodExecutionStatus.queued
        self._session.flush()
        return self._method_execution_from_row(row)

    def mark_execution_started(
        self, method_execution_id: UUID, *, started_at: datetime
    ) -> MethodExecution:
        """Transition a queued method execution to running."""
        row = self._require_execution(method_execution_id)
        self._require_source(
            "method execution",
            method_execution_id,
            row.status,
            {MethodExecutionStatus.queued},
            MethodExecutionStatus.running,
        )
        row.status = MethodExecutionStatus.running
        row.started_at = started_at
        self._session.flush()
        return self._method_execution_from_row(row)

    def mark_execution_finished(
        self,
        method_execution_id: UUID,
        *,
        status: MethodExecutionStatus,
        finished_at: datetime,
        failure_class: str | None = None,
        failure_diagnostic: str | None = None,
    ) -> MethodExecution:
        """Transition a running method execution to a terminal outcome."""
        if status not in _EXECUTION_TERMINAL_STATUSES:
            msg = f"{status} is not a terminal method-execution status"
            raise ValueError(msg)
        row = self._require_execution(method_execution_id)
        self._require_source(
            "method execution",
            method_execution_id,
            row.status,
            {MethodExecutionStatus.running},
            status,
        )
        failed = status is MethodExecutionStatus.failed
        if failed and not (failure_diagnostic and failure_diagnostic.strip()):
            msg = "a failed method execution requires a failure diagnostic"
            raise ValueError(msg)
        row.status = status
        row.finished_at = finished_at
        row.failure_class = failure_class if failed else None
        row.failure_diagnostic = failure_diagnostic if failed else None
        self._session.flush()
        return self._method_execution_from_row(row)

    def claim_batch(
        self,
        task_batch_id: UUID,
        *,
        method_execution_id: UUID,
        worker_task_id: str,
        started_at: datetime,
        attempt_count: int,
    ) -> TaskBatch | None:
        """Atomically claim a pending batch for its owning execution."""
        statement = (
            update(TaskBatchRow)
            .where(
                TaskBatchRow.id == task_batch_id,
                TaskBatchRow.method_execution_id == method_execution_id,
                TaskBatchRow.status.in_((TaskBatchStatus.pending, TaskBatchStatus.queued)),
            )
            .values(
                status=TaskBatchStatus.running,
                worker_task_id=worker_task_id,
                started_at=started_at,
                attempt_count=attempt_count,
            )
            .returning(TaskBatchRow)
            .execution_options(populate_existing=True)
        )
        row = self._session.scalar(statement)
        if row is not None:
            self._session.flush()
            return self._task_batch_from_row(row)

        existing = self._session.scalar(
            select(TaskBatchRow)
            .where(TaskBatchRow.id == task_batch_id)
            .execution_options(populate_existing=True)
        )
        if existing is None:
            msg = f"task batch {task_batch_id} does not exist"
            raise ResourceNotFoundError(msg)
        if existing.method_execution_id != method_execution_id:
            msg = (
                f"task batch {task_batch_id} does not belong to method execution "
                f"{method_execution_id}"
            )
            raise InvalidResourceStateError(msg)
        self._session.flush()
        return None

    def mark_batch_finished(
        self,
        task_batch_id: UUID,
        *,
        status: TaskBatchStatus,
        finished_at: datetime,
        success_count: int = 0,
        abstain_count: int = 0,
        error_count: int = 0,
        failure_class: str | None = None,
        failure_diagnostic: str | None = None,
    ) -> TaskBatch:
        """Transition a running batch to a terminal outcome with its tallies."""
        if status not in _BATCH_TERMINAL_STATUSES:
            msg = f"{status} is not a terminal task-batch status"
            raise ValueError(msg)
        row = self._require_batch(task_batch_id)
        self._require_source(
            "task batch", task_batch_id, row.status, {TaskBatchStatus.running}, status
        )
        failed = status is TaskBatchStatus.failed
        if failed and not (failure_diagnostic and failure_diagnostic.strip()):
            msg = "a failed task batch requires a failure diagnostic"
            raise ValueError(msg)
        tallies = (success_count, abstain_count, error_count)
        if any(count < 0 for count in tallies):
            msg = "task-batch tallies must be non-negative"
            raise ValueError(msg)
        if failed:
            if success_count or abstain_count or error_count != row.record_count:
                msg = "a failed task batch must count every record as an error"
                raise ValueError(msg)
        elif sum(tallies) != row.record_count:
            msg = "completed task-batch tallies must equal record_count"
            raise ValueError(msg)
        row.status = status
        row.finished_at = finished_at
        row.success_count = success_count
        row.abstain_count = abstain_count
        row.error_count = error_count
        row.failure_class = failure_class if failed else None
        row.failure_diagnostic = failure_diagnostic if failed else None
        self._session.flush()
        return self._task_batch_from_row(row)

    def finalize_execution_if_complete(
        self, method_execution_id: UUID, *, finished_at: datetime
    ) -> MethodExecution:
        """Finalize a running execution once all its batches are terminal.

        Locks the execution row so concurrent batch workers cannot both finalize
        it; a no-op while batches are outstanding or the execution is terminal.
        """
        row = self._session.get(MethodExecutionRow, method_execution_id, with_for_update=True)
        if row is None:
            msg = f"method execution {method_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if row.status is not MethodExecutionStatus.running:
            return self._method_execution_from_row(row)
        batches = tuple(
            self._session.scalars(
                select(TaskBatchRow).where(TaskBatchRow.method_execution_id == method_execution_id)
            )
        )
        if any(batch.status not in _BATCH_TERMINAL_STATUSES for batch in batches):
            return self._method_execution_from_row(row)
        row.completed_count = sum(batch.success_count + batch.abstain_count for batch in batches)
        row.failed_count = sum(batch.error_count for batch in batches)
        failed_batches = [batch for batch in batches if batch.status is TaskBatchStatus.failed]
        if batches and len(failed_batches) == len(batches):
            row.status = MethodExecutionStatus.failed
            row.failure_class = failed_batches[0].failure_class
            row.failure_diagnostic = (
                f"all {len(batches)} task batches failed: {failed_batches[0].failure_diagnostic}"
            )
        elif failed_batches or row.failed_count > 0:
            row.status = MethodExecutionStatus.completed_with_errors
        else:
            row.status = MethodExecutionStatus.completed
        row.finished_at = finished_at
        self._session.flush()
        return self._method_execution_from_row(row)

    def finalize_run_if_complete(self, run_id: UUID, *, finished_at: datetime) -> Run:
        """Finalize a running run once all its method executions are terminal.

        Locks the run row so concurrent workers cannot both finalize it; a no-op
        while any execution is outstanding or the run is terminal.
        """
        row = self._session.get(RunRow, run_id, with_for_update=True)
        if row is None:
            msg = f"run {run_id} does not exist"
            raise ResourceNotFoundError(msg)
        if row.status is not RunStatus.running:
            return self._run_from_row(row)
        executions = tuple(
            self._session.scalars(
                select(MethodExecutionRow).where(MethodExecutionRow.run_id == run_id)
            )
        )
        if any(item.status not in _EXECUTION_TERMINAL_STATUSES for item in executions):
            return self._run_from_row(row)
        failed_or_errored = [
            item
            for item in executions
            if item.status
            in {MethodExecutionStatus.completed_with_errors, MethodExecutionStatus.failed}
        ]
        if not failed_or_errored:
            row.status = RunStatus.completed
        elif RunConfig.model_validate(
            row.resolved_config
        ).execution.fail_run_on_optional_method_error and any(
            item.status is MethodExecutionStatus.failed for item in executions
        ):
            row.status = RunStatus.failed
            row.failure_diagnostic = (
                f"{len(failed_or_errored)} method execution(s) did not complete cleanly"
            )
        else:
            row.status = RunStatus.completed_with_errors
        row.finished_at = finished_at
        self._session.flush()
        return self._run_from_row(row)

    def _require_run(self, run_id: UUID) -> RunRow:
        row = self._session.get(RunRow, run_id)
        if row is None:
            msg = f"run {run_id} does not exist"
            raise ResourceNotFoundError(msg)
        return row

    def _require_execution(self, method_execution_id: UUID) -> MethodExecutionRow:
        row = self._session.get(MethodExecutionRow, method_execution_id)
        if row is None:
            msg = f"method execution {method_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        return row

    def _require_batch(self, task_batch_id: UUID) -> TaskBatchRow:
        row = self._session.get(TaskBatchRow, task_batch_id)
        if row is None:
            msg = f"task batch {task_batch_id} does not exist"
            raise ResourceNotFoundError(msg)
        return row

    @staticmethod
    def _require_source(
        resource: str,
        resource_id: UUID,
        current: object,
        allowed: Collection[object],
        target: object,
    ) -> None:
        if current not in allowed:
            msg = f"{resource} {resource_id} cannot transition from {current} to {target}"
            raise InvalidResourceStateError(msg)

    def add_predictions(
        self,
        method_execution_id: UUID,
        predictions: Sequence[PredictionWrite],
    ) -> int:
        """Persist one complete running-batch slice with exact conflict verification."""
        if not predictions:
            msg = "a prediction batch must not be empty"
            raise ValueError(msg)

        task_batch_ids = {prediction.task_batch_id for prediction in predictions}
        if len(task_batch_ids) != 1:
            msg = "a prediction batch must target exactly one task batch"
            raise ValueError(msg)
        task_batch_id = next(iter(task_batch_ids))

        batch = self._session.scalar(
            select(TaskBatchRow)
            .where(TaskBatchRow.id == task_batch_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if batch is None:
            msg = f"task batch {task_batch_id} does not exist"
            raise ResourceNotFoundError(msg)
        if batch.method_execution_id != method_execution_id:
            msg = (
                f"task batch {task_batch_id} does not belong to method execution "
                f"{method_execution_id}"
            )
            raise InvalidResourceStateError(msg)
        execution = self._session.scalar(
            select(MethodExecutionRow)
            .where(MethodExecutionRow.id == method_execution_id)
            .execution_options(populate_existing=True)
        )
        if execution is None:
            msg = f"method execution {method_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        run = self._session.scalar(
            select(RunRow)
            .where(RunRow.id == execution.run_id)
            .execution_options(populate_existing=True)
        )
        if run is None:
            msg = f"run {execution.run_id} does not exist"
            raise ResourceNotFoundError(msg)
        if run.status is not RunStatus.running:
            msg = f"run {run.id} must be running to add predictions"
            raise InvalidResourceStateError(msg)
        if execution.status is not MethodExecutionStatus.running:
            msg = f"method execution {execution.id} must be running to add predictions"
            raise InvalidResourceStateError(msg)
        if batch.status is not TaskBatchStatus.running:
            msg = f"task batch {batch.id} must be running to add predictions"
            raise InvalidResourceStateError(msg)

        person_ids = {prediction.person_record_id for prediction in predictions}
        if len(person_ids) != len(predictions):
            msg = "a prediction batch must contain each person at most once"
            raise ValueError(msg)
        expected_person_ids = tuple(
            self._session.scalars(
                select(PersonRecordRow.id)
                .where(PersonRecordRow.dataset_snapshot_id == run.dataset_snapshot_id)
                .order_by(PersonRecordRow.tei_id, PersonRecordRow.id)
                .offset(batch.record_offset)
                .limit(batch.record_count)
            )
        )
        if len(expected_person_ids) != batch.record_count:
            msg = (
                f"task batch {batch.id} declares {batch.record_count} records but its "
                f"run snapshot slice contains {len(expected_person_ids)} people"
            )
            raise InvalidResourceStateError(msg)
        if person_ids != set(expected_person_ids):
            msg = (
                f"prediction batch for task batch {batch.id} must exactly cover its "
                f"person slice: expected {len(expected_person_ids)}, received {len(person_ids)}"
            )
            raise InvalidResourceStateError(msg)

        payloads: list[dict[str, object]] = [
            {
                "id": uuid4(),
                "method_execution_id": method_execution_id,
                "person_record_id": prediction.person_record_id,
                "task_batch_id": prediction.task_batch_id,
                "label": prediction.result.label,
                "status": prediction.result.status,
                "method_confidence": prediction.result.method_confidence,
                "raw_label": prediction.result.raw_label,
                "raw_output": prediction.result.raw_output,
                "metadata": prediction.result.metadata,
                "input_fingerprint": prediction.input_fingerprint,
            }
            for prediction in predictions
        ]
        prediction_table = cast(Table, PredictionRow.__table__)
        statement = (
            insert(prediction_table)
            .values(payloads)
            .on_conflict_do_nothing(constraint="execution_person")
            .returning(prediction_table.c.person_record_id)
        )
        inserted_person_ids = set(self._session.scalars(statement))

        retried_person_ids = person_ids - inserted_person_ids
        if retried_person_ids:
            existing_rows = {
                row.person_record_id: row
                for row in self._session.scalars(
                    select(PredictionRow).where(
                        PredictionRow.method_execution_id == method_execution_id,
                        PredictionRow.person_record_id.in_(retried_person_ids),
                    )
                )
            }
            for prediction in predictions:
                if prediction.person_record_id not in retried_person_ids:
                    continue
                existing_row = existing_rows.get(prediction.person_record_id)
                if existing_row is None or not self._prediction_matches(existing_row, prediction):
                    msg = (
                        "an immutable prediction already exists with different output or provenance"
                    )
                    raise ImmutableResourceError(msg)
        return len(predictions)

    def get_prediction(self, prediction_id: UUID) -> Prediction | None:
        """Return a persisted prediction contract by ID without exposing its row."""
        row = self._session.get(PredictionRow, prediction_id)
        return None if row is None else self._prediction_from_row(row)

    @staticmethod
    def _prediction_matches(row: PredictionRow, prediction: PredictionWrite) -> bool:
        result = prediction.result
        return (
            row.task_batch_id == prediction.task_batch_id
            and row.label == result.label
            and row.status == result.status
            and row.method_confidence == result.method_confidence
            and row.raw_label == result.raw_label
            and row.raw_output == result.raw_output
            and row.prediction_metadata == result.metadata
            and row.input_fingerprint == prediction.input_fingerprint
        )

    def _run_progress(self, run_id: UUID) -> Progress:
        executions = self._session.scalars(
            select(MethodExecutionRow).where(MethodExecutionRow.run_id == run_id)
        ).all()
        if not executions:
            return Progress(total=None, completed=0, failed=0, percentage=None)
        totals = [execution.total_count for execution in executions]
        present = [value for value in totals if value is not None]
        total = sum(present) if len(present) == len(totals) else None
        completed = sum(execution.completed_count for execution in executions)
        failed = sum(execution.failed_count for execution in executions)
        return Progress.of(total=total, completed=completed, failed=failed)

    def _run_from_row(self, row: RunRow) -> Run:
        return Run(
            id=row.id,
            dataset_snapshot_id=row.dataset_snapshot_id,
            resolved_config=RunConfig.model_validate(row.resolved_config),
            config_sha256=row.config_sha256,
            status=row.status,
            code_git_commit=row.code_git_commit,
            application_version=row.application_version,
            container_image_digest=row.container_image_digest,
            python_version=row.python_version,
            dependency_lock_sha256=row.dependency_lock_sha256,
            dependency_lock_artifact_id=row.dependency_lock_artifact_id,
            started_at=row.started_at,
            finished_at=row.finished_at,
            failure_diagnostic=row.failure_diagnostic,
            created_at=row.created_at,
            progress=self._run_progress(row.id),
        )

    @staticmethod
    def _method_execution_from_row(row: MethodExecutionRow) -> MethodExecution:
        return MethodExecution(
            id=row.id,
            run_id=row.run_id,
            method_name=row.method_name,
            implementation_version=row.implementation_version,
            normalization_version=row.normalization_version,
            resolved_config=row.resolved_config,
            config_sha256=row.config_sha256,
            status=row.status,
            queue_name=row.queue_name,
            model_identifier=row.model_identifier,
            model_revision=row.model_revision,
            model_checksum=row.model_checksum,
            model_artifact_id=row.model_artifact_id,
            data_artifact_id=row.data_artifact_id,
            prompt_version=row.prompt_version,
            schema_version=row.schema_version,
            worker_metadata=row.worker_metadata,
            total_count=row.total_count,
            completed_count=row.completed_count,
            failed_count=row.failed_count,
            started_at=row.started_at,
            finished_at=row.finished_at,
            failure_class=row.failure_class,
            failure_diagnostic=row.failure_diagnostic,
            created_at=row.created_at,
            progress=Progress.of(
                total=row.total_count,
                completed=row.completed_count,
                failed=row.failed_count,
            ),
        )

    @staticmethod
    def _task_batch_from_row(row: TaskBatchRow) -> TaskBatch:
        return TaskBatch(
            id=row.id,
            method_execution_id=row.method_execution_id,
            batch_index=row.batch_index,
            status=row.status,
            queue_name=row.queue_name,
            record_offset=row.record_offset,
            record_count=row.record_count,
            worker_task_id=row.worker_task_id,
            attempt_count=row.attempt_count,
            success_count=row.success_count,
            abstain_count=row.abstain_count,
            error_count=row.error_count,
            started_at=row.started_at,
            finished_at=row.finished_at,
            failure_class=row.failure_class,
            failure_diagnostic=row.failure_diagnostic,
            created_at=row.created_at,
        )

    @staticmethod
    def _prediction_from_row(row: PredictionRow) -> Prediction:
        return Prediction(
            id=row.id,
            method_execution_id=row.method_execution_id,
            person_record_id=row.person_record_id,
            task_batch_id=row.task_batch_id,
            input_fingerprint=row.input_fingerprint,
            label=row.label,
            status=row.status,
            method_confidence=row.method_confidence,
            raw_label=row.raw_label,
            raw_output=row.raw_output,
            metadata=row.prediction_metadata,
            created_at=row.created_at,
        )
