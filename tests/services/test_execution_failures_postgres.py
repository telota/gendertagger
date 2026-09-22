from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, func, select

from gendertagger.config.run import ExecutionConfig, MethodRunConfig, RunConfig
from gendertagger.db.executions import PredictionRow
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.methods.base import MethodConfig, MethodContractError
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import PredictionResult
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import ImportedPerson, PersonInput
from gendertagger.models.project import (
    DatasetSnapshotCreate,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotSourceMemberCreate,
    TeiImportProfile,
)
from gendertagger.models.run import RunCreate
from gendertagger.services.execution import (
    BatchExecutor,
    RunScheduler,
    ScheduledBatch,
    TransientBatchError,
)
from gendertagger.services.method_registry import (
    MethodRegistration,
    MethodRegistry,
    default_method_registry,
)
from gendertagger.services.unit_of_work import UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


class _EmptyConfig(MethodConfig):
    pass


class _TransientAdapter:
    descriptor = MethodDescriptor(
        name="flaky_method", implementation_version="v1", normalization_version="v1"
    )
    config_model = _EmptyConfig

    def predict_batch(
        self, people: Sequence[PersonInput], config: _EmptyConfig
    ) -> list[PredictionResult]:
        del people, config
        raise RuntimeError("transient broker outage")


class _PermanentAdapter:
    descriptor = MethodDescriptor(
        name="broken_method", implementation_version="v1", normalization_version="v1"
    )
    config_model = _EmptyConfig

    def __init__(self) -> None:
        self.call_count = 0

    def predict_batch(
        self, people: Sequence[PersonInput], config: _EmptyConfig
    ) -> list[PredictionResult]:
        self.call_count += 1
        del people, config
        raise MethodContractError("adapter returned the wrong shape")


def _registration(adapter: object) -> MethodRegistration:
    return MethodRegistration(
        descriptor=adapter.descriptor,  # type: ignore[attr-defined]
        config_model=adapter.config_model,  # type: ignore[attr-defined]
        adapter=adapter,  # type: ignore[arg-type]
        queue_name="cpu",
        batch_size=100,
    )


def _seed_run(
    factory: UnitOfWorkFactory,
    *,
    methods: list[MethodRunConfig],
    execution_config: ExecutionConfig | None = None,
) -> UUID:
    config = RunConfig(methods=methods, execution=execution_config or ExecutionConfig())
    with factory() as unit_of_work:
        project = unit_of_work.projects.add_project(
            ProjectCreate(slug=f"fail-{uuid4().hex}", display_name="Failure policy project")
        )
        source = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="source_tei",
                storage_uri="file:///synthetic/source.xml",
                sha256="a" * 64,
                byte_size=1,
                media_type="application/xml",
                project_id=project.id,
            )
        )
        # The legacy profile captures no structured name forms, which this fixture does not model.
        import_config = SnapshotImportConfig(
            profile=TeiImportProfile.tei_p5_person_register_v1,
            limits=SnapshotImportLimits(),
        )
        snapshot = unit_of_work.projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=source.id,
                source_sha256=source.sha256,
                parser_version=version_for_snapshot_import(import_config),
                import_config=import_config.model_dump(mode="json"),
            )
        )
        unit_of_work.projects.add_snapshot_source_members(
            snapshot.id,
            [
                SnapshotSourceMemberCreate(
                    artifact_id=source.id,
                    ordinal=0,
                    logical_name="source.xml",
                    sha256=source.sha256,
                    byte_size=source.byte_size,
                    media_type=source.media_type,
                )
            ],
        )
        unit_of_work.projects.begin_snapshot_import(snapshot.id)
        unit_of_work.projects.add_imported_person_records(
            snapshot.id,
            [
                ImportedPerson(
                    person=PersonInput(tei_id="p01", surname="Frölich (Frau des Heinrich)"),
                    source_member_name="source.xml",
                    source_record_locator="1",
                )
            ],
        )
        unit_of_work.projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
        run = unit_of_work.runs.add_run(
            RunCreate(
                dataset_snapshot_id=snapshot.id,
                resolved_config=config,
                code_git_commit="abc123",
                application_version="0.0.0",
                python_version="3.11.0",
                dependency_lock_sha256="b" * 64,
            )
        )
        unit_of_work.commit()
        return run.id


def _executor(factory: UnitOfWorkFactory, registry: MethodRegistry) -> BatchExecutor:
    return BatchExecutor(unit_of_work_factory=factory, method_registry=registry, clock=lambda: NOW)


def _scheduled(
    factory: UnitOfWorkFactory, registry: MethodRegistry, run_id: UUID
) -> list[ScheduledBatch]:
    scheduler = RunScheduler(
        unit_of_work_factory=factory, method_registry=registry, clock=lambda: NOW
    )
    return scheduler.schedule_run(run_id)


def test_transient_failure_below_max_attempts_raises_for_retry(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    registry = MethodRegistry([_registration(_TransientAdapter())])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="flaky_method")])
    scheduled = _scheduled(factory, registry, run_id)

    with pytest.raises(TransientBatchError):
        _executor(factory, registry).execute(
            scheduled[0].message(), worker_task_id="w", attempt_count=1, max_attempts=3
        )

    with factory() as unit_of_work:
        batch = unit_of_work.runs.get_task_batch(scheduled[0].task_batch_id)
    assert batch is not None
    assert batch.status is TaskBatchStatus.pending  # rolled back for retry


def test_transient_failure_at_max_attempts_fails_the_batch(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    registry = MethodRegistry([_registration(_TransientAdapter())])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="flaky_method")])
    scheduled = _scheduled(factory, registry, run_id)

    failed = _executor(factory, registry).execute(
        scheduled[0].message(), worker_task_id="w", attempt_count=3, max_attempts=3
    )

    assert failed.status is TaskBatchStatus.failed
    assert failed.failure_class == "RuntimeError"
    assert failed.error_count == 1
    with factory() as unit_of_work:
        execution = unit_of_work.runs.get_method_execution(scheduled[0].method_execution_id)
        run = unit_of_work.runs.get_run(run_id)
    assert execution is not None
    assert execution.status is MethodExecutionStatus.failed
    assert execution.failed_count == 1
    assert execution.progress.total == 1
    assert execution.progress.completed == 0
    assert execution.progress.failed == 1
    assert execution.progress.percentage == 100
    assert run is not None
    assert run.status is RunStatus.completed_with_errors
    assert run.progress.total == 1
    assert run.progress.completed == 0
    assert run.progress.failed == 1
    assert run.progress.percentage == 100


def test_permanent_failure_fails_the_batch_without_retry(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    registry = MethodRegistry([_registration(_PermanentAdapter())])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="broken_method")])
    scheduled = _scheduled(factory, registry, run_id)

    failed = _executor(factory, registry).execute(
        scheduled[0].message(), worker_task_id="w", attempt_count=1, max_attempts=3
    )

    assert failed.status is TaskBatchStatus.failed
    assert failed.failure_class == "MethodContractError"
    assert failed.error_count == 1


def test_redelivery_does_not_reopen_a_failed_batch(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    adapter = _PermanentAdapter()
    registry = MethodRegistry([_registration(adapter)])
    run_id = _seed_run(factory, methods=[MethodRunConfig(name="broken_method")])
    scheduled = _scheduled(factory, registry, run_id)
    executor = _executor(factory, registry)

    first = executor.execute(
        scheduled[0].message(), worker_task_id="w1", attempt_count=1, max_attempts=3
    )
    redelivery = executor.execute(
        scheduled[0].message(), worker_task_id="w2", attempt_count=2, max_attempts=3
    )

    assert first.status is TaskBatchStatus.failed
    assert redelivery.status is TaskBatchStatus.failed
    assert redelivery.error_count == 1
    assert redelivery.worker_task_id == "w1"
    assert adapter.call_count == 1


def test_partial_failure_preserves_the_successful_method(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, connection = postgres_unit_of_work
    registry = MethodRegistry(
        [*default_method_registry().registrations, _registration(_PermanentAdapter())]
    )
    run_id = _seed_run(
        factory,
        methods=[
            MethodRunConfig(name="parenthetical_qualifier"),
            MethodRunConfig(name="broken_method"),
        ],
    )
    scheduled = _scheduled(factory, registry, run_id)
    assert len(scheduled) == 2

    executor = _executor(factory, registry)
    for batch in scheduled:
        executor.execute(batch.message(), worker_task_id="w", attempt_count=3, max_attempts=3)

    with factory() as unit_of_work:
        run = unit_of_work.runs.get_run(run_id)
        executions = {}
        for batch in scheduled:
            execution = unit_of_work.runs.get_method_execution(batch.method_execution_id)
            assert execution is not None
            executions[execution.method_name] = execution
    assert run is not None
    assert run.status is RunStatus.completed_with_errors
    assert executions["parenthetical_qualifier"].status is MethodExecutionStatus.completed
    assert executions["broken_method"].status is MethodExecutionStatus.failed

    preserved = connection.execute(
        select(func.count())
        .select_from(PredictionRow)
        .where(PredictionRow.method_execution_id == executions["parenthetical_qualifier"].id)
    ).scalar_one()
    assert preserved == 1  # the successful method's evidence survives


def test_fail_run_flag_fails_the_run_on_method_failure(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    registry = MethodRegistry([_registration(_PermanentAdapter())])
    run_id = _seed_run(
        factory,
        methods=[MethodRunConfig(name="broken_method")],
        execution_config=ExecutionConfig(fail_run_on_optional_method_error=True),
    )
    scheduled = _scheduled(factory, registry, run_id)

    _executor(factory, registry).execute(
        scheduled[0].message(), worker_task_id="w", attempt_count=3, max_attempts=3
    )

    with factory() as unit_of_work:
        run = unit_of_work.runs.get_run(run_id)
    assert run is not None
    assert run.status is RunStatus.failed
    assert run.failure_diagnostic is not None
