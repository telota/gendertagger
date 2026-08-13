"""SQLAlchemy repository for runs, method executions, batches, and predictions."""

from collections.abc import Sequence
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Table, select
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
    Run,
    RunCreate,
    TaskBatch,
    TaskBatchCreate,
)
from gendertagger.services.persistence_errors import (
    ImmutableResourceError,
    InvalidResourceStateError,
    ResourceNotFoundError,
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
        run = self._session.get(RunRow, command.run_id)
        if run is None:
            msg = f"run {command.run_id} does not exist"
            raise ResourceNotFoundError(msg)
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

    def add_task_batch(self, command: TaskBatchCreate) -> TaskBatch:
        """Persist and flush one retryable task batch without committing."""
        execution = self._session.get(MethodExecutionRow, command.method_execution_id)
        if execution is None:
            msg = f"method execution {command.method_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if execution.queue_name != command.queue_name:
            msg = "task batch queue must match its method execution queue"
            raise InvalidResourceStateError(msg)

        row = TaskBatchRow(
            method_execution_id=command.method_execution_id,
            batch_index=command.batch_index,
            status=TaskBatchStatus.pending,
            queue_name=command.queue_name,
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

    def add_predictions(
        self,
        method_execution_id: UUID,
        predictions: Sequence[PredictionWrite],
    ) -> int:
        """Validate ownership and persist one bounded immutable prediction batch."""
        execution = self._session.get(MethodExecutionRow, method_execution_id)
        if execution is None:
            msg = f"method execution {method_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if not predictions:
            return 0

        person_ids = {prediction.person_record_id for prediction in predictions}
        if len(person_ids) != len(predictions):
            msg = "a prediction batch must contain each person at most once"
            raise ValueError(msg)
        run_snapshot_id = self._session.scalar(
            select(RunRow.dataset_snapshot_id).where(RunRow.id == execution.run_id)
        )
        matching_person_ids = set(
            self._session.scalars(
                select(PersonRecordRow.id).where(
                    PersonRecordRow.id.in_(person_ids),
                    PersonRecordRow.dataset_snapshot_id == run_snapshot_id,
                )
            )
        )
        if matching_person_ids != person_ids:
            msg = "every prediction person must belong to the run snapshot"
            raise InvalidResourceStateError(msg)

        task_batch_ids = {
            prediction.task_batch_id
            for prediction in predictions
            if prediction.task_batch_id is not None
        }
        matching_task_batch_ids = set(
            self._session.scalars(
                select(TaskBatchRow.id).where(
                    TaskBatchRow.id.in_(task_batch_ids),
                    TaskBatchRow.method_execution_id == method_execution_id,
                )
            )
        )
        if matching_task_batch_ids != task_batch_ids:
            msg = "every prediction task batch must belong to the method execution"
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

    @staticmethod
    def _run_from_row(row: RunRow) -> Run:
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
        )

    @staticmethod
    def _task_batch_from_row(row: TaskBatchRow) -> TaskBatch:
        return TaskBatch(
            id=row.id,
            method_execution_id=row.method_execution_id,
            batch_index=row.batch_index,
            status=row.status,
            queue_name=row.queue_name,
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
