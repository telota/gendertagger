"""Application orchestration for scheduling and executing classification batches."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import file_digest
from os import fstat
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from gendertagger.methods.base import (
    MethodContractError,
    MethodDependencyError,
    validate_prediction_batch,
)
from gendertagger.methods.model_manifest import ModelDirectoryResolver
from gendertagger.methods.sqlite_lookup import LookupAssetResolver
from gendertagger.models.artifact import ModelManifestMetadata
from gendertagger.models.classification import PredictionResult, PredictionStatus
from gendertagger.models.common import canonical_json_sha256
from gendertagger.models.dispatch import BatchDispatchCreate
from gendertagger.models.lifecycle import RunStatus, TaskBatchStatus
from gendertagger.models.person import PersonInput, PersonRecord
from gendertagger.models.run import (
    MethodExecution,
    MethodExecutionCreate,
    PredictionWrite,
    Run,
    TaskBatch,
    TaskBatchMessage,
    WorkerProvenance,
)
from gendertagger.services.diagnostics import sanitized_diagnostic
from gendertagger.services.method_registry import MethodRegistration, MethodRegistry
from gendertagger.services.ports.artifact_repository import AmbiguousArtifactError
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from gendertagger.services.task_batches import plan_task_batches

Clock = Callable[[], datetime]

DEFAULT_MAX_BATCH_ATTEMPTS = 3


class TransientBatchError(RuntimeError):
    """Raised when a batch fails for a retryable infrastructure reason."""


class PermanentBatchError(RuntimeError):
    """Raised when a batch fails for a non-retryable scientific or config reason."""


class IncompatibleWorkerError(PermanentBatchError):
    """Reject computation that cannot reproduce the accepted execution identity."""


def _assert_file_identity(path: Path, *, sha256: str, byte_size: int) -> None:
    """Verify the actual consumed file without exposing storage paths in diagnostics."""
    try:
        with path.open("rb") as source:
            actual_byte_size = fstat(source.fileno()).st_size
            actual_sha256 = file_digest(source, "sha256").hexdigest()
    except OSError as error:
        msg = "accepted method artifact is unavailable"
        raise MethodDependencyError(msg) from error
    if actual_sha256 != sha256 or actual_byte_size != byte_size:
        msg = "method artifact bytes differ from the accepted checksum or size"
        raise IncompatibleWorkerError(msg)


@dataclass(frozen=True, slots=True)
class ScheduledBatch:
    """One persisted batch with a durable routing-class dispatch intent."""

    method_execution_id: UUID
    task_batch_id: UUID
    queue_name: str

    def message(self) -> TaskBatchMessage:
        """Return the small validated envelope carried by the Celery task."""
        return TaskBatchMessage(
            method_execution_id=self.method_execution_id,
            task_batch_id=self.task_batch_id,
        )


def _person_input_fingerprint(person: PersonRecord) -> str:
    payload = person.model_dump(
        mode="json",
        include=set(PersonInput.model_fields),
    )
    return canonical_json_sha256(payload)


class RunScheduler:
    """Atomically persist executions, batches, and their durable dispatch intent."""

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
        """Persist a created run's executions, batches, and outbox intents atomically."""
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
                data_artifact_id: UUID | None = None
                if registration.data_artifact_logical_type is not None:
                    lookup_sha256 = method.config.get("lookup_sha256")
                    if not isinstance(lookup_sha256, str):
                        msg = f"method {method.name!r} lacks a resolved lookup_sha256"
                        raise InvalidResourceStateError(msg)
                    try:
                        artifact = unit_of_work.artifacts.get_artifact_by_sha256(
                            registration.data_artifact_logical_type,
                            lookup_sha256,
                        )
                    except AmbiguousArtifactError as error:
                        raise InvalidResourceStateError(str(error)) from error
                    if artifact is None:
                        msg = (
                            f"lookup artifact for method {method.name!r} "
                            f"and digest {lookup_sha256!r} is not registered"
                        )
                        raise InvalidResourceStateError(msg)
                    data_artifact_id = artifact.id
                execution = unit_of_work.runs.add_method_execution(
                    MethodExecutionCreate(
                        run_id=run_id,
                        descriptor=registration.descriptor,
                        resolved_config=method.config,
                        queue_name=registration.queue_name,
                        total_count=total_count,
                        data_artifact_id=data_artifact_id,
                    )
                )
                unit_of_work.runs.mark_execution_queued(execution.id)
                unit_of_work.runs.mark_execution_started(execution.id, started_at=now)
                plans = plan_task_batches(total_count, batch_size=registration.batch_size)
                batches = unit_of_work.runs.create_task_batches(execution.id, plans)
                for batch in batches:
                    scheduled_batch = ScheduledBatch(
                        execution.id,
                        batch.id,
                        batch.queue_name,
                    )
                    unit_of_work.dispatches.ensure_dispatch(
                        BatchDispatchCreate(
                            task_batch_id=batch.id,
                            queue_name=batch.queue_name,
                            payload=scheduled_batch.message(),
                            available_at=now,
                        )
                    )
                    scheduled.append(scheduled_batch)
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
        worker_provenance: WorkerProvenance,
        lookup_asset_resolver: LookupAssetResolver | None = None,
        model_directory_resolver: ModelDirectoryResolver | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._method_registry = method_registry
        self._clock = clock
        self._worker_provenance = worker_provenance
        self._lookup_asset_resolver = lookup_asset_resolver
        self._model_directory_resolver = model_directory_resolver

    def execute(
        self,
        message: TaskBatchMessage,
        *,
        worker_task_id: str,
        attempt_count: int,
        max_attempts: int = DEFAULT_MAX_BATCH_ATTEMPTS,
    ) -> TaskBatch:
        """Idempotently classify one batch, applying retry and failure policy.

        Permanent scientific or configuration failures fail the batch at once.
        A transient infrastructure failure raises :class:`TransientBatchError`
        for the caller to retry until ``attempt_count`` reaches ``max_attempts``,
        after which the batch is failed so the run can still complete.
        """
        with self._unit_of_work_factory() as unit_of_work:
            batch = unit_of_work.runs.claim_batch(
                message.task_batch_id,
                method_execution_id=message.method_execution_id,
                worker_task_id=worker_task_id,
                worker_provenance=self._worker_provenance,
                started_at=self._clock(),
                attempt_count=attempt_count,
            )
            if batch is None:
                existing = unit_of_work.runs.get_task_batch(message.task_batch_id)
                if existing is None:  # Defensive: claim_batch owns the not-found check.
                    msg = f"task batch {message.task_batch_id} does not exist"
                    raise ResourceNotFoundError(msg)
                return existing  # Duplicate delivery is a safe no-op.

            execution = unit_of_work.runs.get_method_execution(message.method_execution_id)
            if execution is None:
                msg = f"method execution {message.method_execution_id} does not exist"
                raise ResourceNotFoundError(msg)
            run = unit_of_work.runs.get_run(execution.run_id)
            if run is None:
                msg = f"run {execution.run_id} does not exist"
                raise ResourceNotFoundError(msg)

            try:
                results = self._classify(unit_of_work, execution=execution, run=run, batch=batch)
            except (
                PermanentBatchError,
                MethodContractError,
                MethodDependencyError,
                ValidationError,
            ) as error:
                return self._fail_batch(unit_of_work, batch, execution.id, run.id, error)
            except Exception as error:
                # Unclassified failures are treated as transient: retry, then fail.
                if attempt_count >= max_attempts:
                    return self._fail_batch(unit_of_work, batch, execution.id, run.id, error)
                msg = f"task batch {message.task_batch_id} failed on attempt {attempt_count}"
                raise TransientBatchError(msg) from error

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

    def _classify(
        self,
        unit_of_work: UnitOfWork,
        *,
        execution: MethodExecution,
        run: Run,
        batch: TaskBatch,
    ) -> list[PredictionResult]:
        registration = self._method_registry.registration_for(execution.method_name)
        if registration is None:
            msg = f"method {execution.method_name!r} is not registered"
            raise PermanentBatchError(msg)
        self._verify_execution_identity(execution, run, registration)
        config: Any = registration.config_model.model_validate(execution.resolved_config)
        if (
            canonical_json_sha256(execution.resolved_config) != execution.config_sha256
            or config.model_dump(mode="json") != execution.resolved_config
        ):
            msg = "method configuration differs from the accepted execution"
            raise IncompatibleWorkerError(msg)
        self._verify_pinned_assets(unit_of_work, execution, registration)
        records = unit_of_work.projects.list_person_records_slice(
            run.dataset_snapshot_id,
            offset=batch.record_offset,
            limit=batch.record_count,
        )
        if len(records) != batch.record_count:
            msg = (
                f"task batch {batch.id} expected {batch.record_count} records "
                f"but loaded {len(records)}"
            )
            raise PermanentBatchError(msg)
        persisted_inputs = [(record.id, _person_input_fingerprint(record)) for record in records]
        results = registration.adapter.predict_batch(records, config)
        validate_prediction_batch(registration.descriptor, records, results)
        writes = [
            PredictionWrite(
                person_record_id=person_record_id,
                task_batch_id=batch.id,
                input_fingerprint=input_fingerprint,
                result=result,
            )
            for (person_record_id, input_fingerprint), result in zip(
                persisted_inputs,
                results,
                strict=True,
            )
        ]
        unit_of_work.runs.add_predictions(execution.id, writes)
        return results

    def _verify_execution_identity(
        self, execution: MethodExecution, run: Run, registration: MethodRegistration
    ) -> None:
        for field in ("implementation_version", "normalization_version"):
            if getattr(execution, field) != getattr(registration.descriptor, field):
                msg = f"method {field} differs from the accepted execution"
                raise IncompatibleWorkerError(msg)
        if not run.dependency_versions:
            msg = "accepted run lacks exact dependency_versions evidence"
            raise IncompatibleWorkerError(msg)
        for field in (
            "code_git_commit",
            "application_version",
            "python_version",
            "dependency_lock_sha256",
            "dependency_versions",
            "container_image_digest",
        ):
            if getattr(run, field) != getattr(self._worker_provenance, field):
                msg = f"worker {field} differs from the accepted run"
                raise IncompatibleWorkerError(msg)

    def _verify_pinned_assets(
        self,
        unit_of_work: UnitOfWork,
        execution: MethodExecution,
        registration: MethodRegistration,
    ) -> None:
        logical_type = registration.data_artifact_logical_type
        if logical_type is None:
            return
        sha256 = execution.resolved_config.get("lookup_sha256")
        artifact = (
            unit_of_work.artifacts.get_artifact(execution.data_artifact_id)
            if execution.data_artifact_id is not None
            else None
        )
        if (
            not isinstance(sha256, str)
            or artifact is None
            or artifact.logical_type != logical_type
            or artifact.sha256 != sha256
        ):
            msg = "method artifact reference differs from the accepted configuration"
            raise IncompatibleWorkerError(msg)
        resolver = self._lookup_asset_resolver
        if resolver is None:
            msg = "worker method artifact resolver is not configured"
            raise MethodDependencyError(msg)
        path = resolver.materialize(logical_type, sha256)
        _assert_file_identity(path, sha256=sha256, byte_size=artifact.byte_size)
        if logical_type.endswith("_model_manifest"):
            manifest = ModelManifestMetadata.model_validate_json(path.read_bytes())
            self._verify_model_manifest(execution, logical_type, sha256, manifest)

    def _verify_model_manifest(
        self,
        execution: MethodExecution,
        logical_type: str,
        sha256: str,
        manifest: ModelManifestMetadata,
    ) -> None:
        if manifest.method_name != execution.method_name:
            msg = "model manifest method differs from the accepted execution"
            raise IncompatibleWorkerError(msg)
        for field, actual in (
            ("model_identifier", manifest.source_identifier),
            ("model_revision", manifest.source_revision),
            ("schema_version", manifest.model_schema_version),
            ("model_checksum", sha256),
        ):
            expected = getattr(execution, field)
            if expected is not None and expected != actual:
                msg = f"model {field} differs from the accepted execution"
                raise IncompatibleWorkerError(msg)
        resolver = self._lookup_asset_resolver
        directory_resolver = self._model_directory_resolver
        if resolver is None or directory_resolver is None:
            msg = "worker model resolvers are not configured"
            raise MethodDependencyError(msg)
        member_type = logical_type.removesuffix("_manifest") + "_file"
        for member in manifest.members:
            _assert_file_identity(
                resolver.materialize(member_type, member.sha256),
                sha256=member.sha256,
                byte_size=member.byte_size,
            )
        directory = directory_resolver.materialize_directory(
            manifest_logical_type=logical_type,
            member_logical_type=member_type,
            manifest_sha256=sha256,
            expected_method_name=execution.method_name,
        )
        for member in manifest.members:
            _assert_file_identity(
                directory / member.relative_path,
                sha256=member.sha256,
                byte_size=member.byte_size,
            )

    def _fail_batch(
        self,
        unit_of_work: UnitOfWork,
        batch: TaskBatch,
        method_execution_id: UUID,
        run_id: UUID,
        error: BaseException,
    ) -> TaskBatch:
        finished_at = self._clock()
        failed_batch = unit_of_work.runs.mark_batch_finished(
            batch.id,
            status=TaskBatchStatus.failed,
            finished_at=finished_at,
            error_count=batch.record_count,
            failure_class=type(error).__name__,
            failure_diagnostic=sanitized_diagnostic(error),
        )
        unit_of_work.runs.finalize_execution_if_complete(
            method_execution_id, finished_at=finished_at
        )
        unit_of_work.runs.finalize_run_if_complete(run_id, finished_at=finished_at)
        unit_of_work.commit()
        return failed_batch
