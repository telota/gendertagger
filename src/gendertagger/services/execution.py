"""Application orchestration for scheduling and executing classification batches."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import JsonValue

from gendertagger.methods.base import validate_prediction_batch
from gendertagger.models.classification import PredictionStatus
from gendertagger.models.common import canonical_json_sha256
from gendertagger.models.lifecycle import RunStatus, TaskBatchStatus
from gendertagger.models.person import PersonInput, PersonRecord
from gendertagger.models.run import (
    MethodExecutionCreate,
    PredictionWrite,
    TaskBatch,
    TaskBatchMessage,
)
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.task_batches import plan_task_batches
from gendertagger.services.unit_of_work import UnitOfWorkFactory

Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class ScheduledBatch:
    """One persisted batch ready to enqueue onto its routing-class queue."""

    method_execution_id: UUID
    task_batch_id: UUID
    queue_name: str

    def message(self) -> TaskBatchMessage:
        """Return the small validated envelope carried by the Celery task."""
        return TaskBatchMessage(
            method_execution_id=self.method_execution_id,
            task_batch_id=self.task_batch_id,
        )


class BatchDispatcher(Protocol):
    """Enqueue persisted batches for asynchronous execution."""

    def dispatch(self, batches: Sequence[ScheduledBatch]) -> None:
        """Enqueue each batch onto its queue; persisted state stays authoritative."""
        ...


def _person_input_fingerprint(person: PersonRecord) -> str:
    payload: dict[str, JsonValue] = {
        field: getattr(person, field) for field in PersonInput.model_fields
    }
    return canonical_json_sha256(payload)


class RunScheduler:
    """Persist executions and batches for a created run and return them to dispatch."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        method_registry: MethodRegistry,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._method_registry = method_registry
        self._clock = clock

    def schedule_run(self, run_id: UUID) -> list[ScheduledBatch]:
        """Move a created run to running and persist every method execution's batches."""
        with self._unit_of_work_factory() as unit_of_work:
            run = unit_of_work.runs.get_run(run_id)
            if run is None:
                msg = f"run {run_id} does not exist"
                raise ResourceNotFoundError(msg)
            if run.status is not RunStatus.created:
                msg = f"run {run_id} is not schedulable from status {run.status.value}"
                raise InvalidResourceStateError(msg)
            snapshot = unit_of_work.projects.get_snapshot(run.dataset_snapshot_id)
            if snapshot is None or snapshot.record_count is None:
                msg = f"run {run_id} references a snapshot that is not ready"
                raise InvalidResourceStateError(msg)

            total_count = snapshot.record_count
            now = self._clock()
            unit_of_work.runs.mark_run_queued(run_id)
            unit_of_work.runs.mark_run_started(run_id, started_at=now)

            scheduled: list[ScheduledBatch] = []
            for method in run.resolved_config.methods:
                if not method.enabled:
                    continue
                registration = self._method_registry.registration_for(method.name)
                if registration is None:
                    msg = f"method {method.name!r} is not registered"
                    raise InvalidResourceStateError(msg)
                execution = unit_of_work.runs.add_method_execution(
                    MethodExecutionCreate(
                        run_id=run_id,
                        descriptor=registration.descriptor,
                        resolved_config=method.config,
                        queue_name=registration.queue_name,
                        total_count=total_count,
                    )
                )
                unit_of_work.runs.mark_execution_queued(execution.id)
                unit_of_work.runs.mark_execution_started(execution.id, started_at=now)
                plans = plan_task_batches(total_count, batch_size=registration.batch_size)
                batches = unit_of_work.runs.create_task_batches(execution.id, plans)
                scheduled.extend(
                    ScheduledBatch(execution.id, batch.id, batch.queue_name) for batch in batches
                )
                unit_of_work.runs.finalize_execution_if_complete(execution.id, finished_at=now)
            unit_of_work.runs.finalize_run_if_complete(run_id, finished_at=now)
            unit_of_work.commit()
        return scheduled


class BatchExecutor:
    """Run one method adapter over one batch and persist its immutable results."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        method_registry: MethodRegistry,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._method_registry = method_registry
        self._clock = clock

    def execute(
        self,
        message: TaskBatchMessage,
        *,
        worker_task_id: str,
        attempt_count: int,
    ) -> TaskBatch:
        """Idempotently classify one batch and advance run/execution completion."""
        with self._unit_of_work_factory() as unit_of_work:
            batch = unit_of_work.runs.get_task_batch(message.task_batch_id)
            if batch is None:
                msg = f"task batch {message.task_batch_id} does not exist"
                raise ResourceNotFoundError(msg)
            if batch.status is TaskBatchStatus.completed:
                return batch  # Redelivery of a finished batch is a safe no-op.

            execution = unit_of_work.runs.get_method_execution(message.method_execution_id)
            if execution is None:
                msg = f"method execution {message.method_execution_id} does not exist"
                raise ResourceNotFoundError(msg)
            run = unit_of_work.runs.get_run(execution.run_id)
            if run is None:
                msg = f"run {execution.run_id} does not exist"
                raise ResourceNotFoundError(msg)
            registration = self._method_registry.registration_for(execution.method_name)
            if registration is None:
                msg = f"method {execution.method_name!r} is not registered"
                raise InvalidResourceStateError(msg)

            config: Any = registration.config_model.model_validate(execution.resolved_config)
            records = unit_of_work.projects.list_person_records_slice(
                run.dataset_snapshot_id,
                offset=batch.record_offset,
                limit=batch.record_count,
            )
            started_at = self._clock()
            unit_of_work.runs.mark_batch_started(
                message.task_batch_id,
                worker_task_id=worker_task_id,
                started_at=started_at,
                attempt_count=attempt_count,
            )
            results = registration.adapter.predict_batch(records, config)
            validate_prediction_batch(registration.descriptor, records, results)
            writes = [
                PredictionWrite(
                    person_record_id=record.id,
                    task_batch_id=batch.id,
                    input_fingerprint=_person_input_fingerprint(record),
                    result=result,
                )
                for record, result in zip(records, results, strict=True)
            ]
            unit_of_work.runs.add_predictions(execution.id, writes)

            finished_at = self._clock()
            completed_batch = unit_of_work.runs.mark_batch_finished(
                message.task_batch_id,
                status=TaskBatchStatus.completed,
                finished_at=finished_at,
                success_count=sum(1 for r in results if r.status is PredictionStatus.success),
                abstain_count=sum(1 for r in results if r.status is PredictionStatus.abstain),
                error_count=sum(1 for r in results if r.status is PredictionStatus.error),
            )
            unit_of_work.runs.finalize_execution_if_complete(execution.id, finished_at=finished_at)
            unit_of_work.runs.finalize_run_if_complete(run.id, finished_at=finished_at)
            unit_of_work.commit()
        return completed_batch
