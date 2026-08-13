from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, func, select

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.executions import PredictionRow
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus
from gendertagger.models.person import PersonInput
from gendertagger.models.project import DatasetSnapshotCreate, ProjectCreate
from gendertagger.models.run import RunCreate
from gendertagger.services.execution import BatchExecutor, RunScheduler
from gendertagger.services.method_registry import default_method_registry
from gendertagger.services.persistence_errors import InvalidResourceStateError
from gendertagger.services.unit_of_work import UnitOfWorkFactory

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.e2e]

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 13, 12, 5, tzinfo=UTC)

# Deterministic parenthetical-qualifier outcomes: female, abstain, male, unknown.
PEOPLE = [
    PersonInput(tei_id="p01", surname="Frölich (Frau des Heinrich)"),
    PersonInput(tei_id="p02", surname="Schleiermacher", forenames=["Friedrich"]),
    PersonInput(tei_id="p03", surname="Müller (Sohn des Karl)"),
    PersonInput(tei_id="p04", surname="Mendelssohn (Familie des Abraham)"),
]


def _seed_created_run(factory: UnitOfWorkFactory) -> UUID:
    with factory() as unit_of_work:
        source = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="source_tei",
                storage_uri="file:///synthetic/source.xml",
                sha256="a" * 64,
                byte_size=1,
                media_type="application/xml",
            )
        )
        project = unit_of_work.projects.add_project(
            ProjectCreate(slug=f"exec-{uuid4().hex}", display_name="Execution project")
        )
        snapshot = unit_of_work.projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=source.id,
                source_sha256=source.sha256,
                parser_version="tei_parser_v1",
            )
        )
        unit_of_work.projects.begin_snapshot_import(snapshot.id)
        unit_of_work.projects.add_person_records(snapshot.id, PEOPLE)
        unit_of_work.projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
        run = unit_of_work.runs.add_run(
            RunCreate(
                dataset_snapshot_id=snapshot.id,
                resolved_config=RunConfig(
                    methods=[MethodRunConfig(name="parenthetical_qualifier")]
                ),
                code_git_commit="abc123",
                application_version="0.0.0",
                python_version="3.11.0",
                dependency_lock_sha256="b" * 64,
            )
        )
        unit_of_work.commit()
        return run.id


def test_run_executes_end_to_end_and_completes(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, connection = postgres_unit_of_work
    registry = default_method_registry()
    run_id = _seed_created_run(factory)

    scheduler = RunScheduler(
        unit_of_work_factory=factory, method_registry=registry, clock=lambda: NOW
    )
    scheduled = scheduler.schedule_run(run_id)
    assert len(scheduled) == 1  # four persons fit one CPU batch

    executor = BatchExecutor(
        unit_of_work_factory=factory, method_registry=registry, clock=lambda: LATER
    )
    batch = executor.execute(scheduled[0].message(), worker_task_id="worker-1", attempt_count=1)

    assert batch.status is TaskBatchStatus.completed
    assert batch.success_count == 3  # female, male, substantive unknown
    assert batch.abstain_count == 1  # no relational qualifier

    with factory() as unit_of_work:
        run = unit_of_work.runs.get_run(run_id)
        assert run is not None
        assert run.status is RunStatus.completed
        execution = unit_of_work.runs.get_method_execution(scheduled[0].method_execution_id)
        assert execution is not None
        assert execution.status is MethodExecutionStatus.completed
        assert execution.completed_count == 4
        assert execution.failed_count == 0

    persisted = connection.execute(
        select(func.count())
        .select_from(PredictionRow)
        .where(PredictionRow.method_execution_id == scheduled[0].method_execution_id)
    ).scalar_one()
    assert persisted == 4


def test_batch_execution_is_idempotent(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, connection = postgres_unit_of_work
    registry = default_method_registry()
    run_id = _seed_created_run(factory)
    scheduler = RunScheduler(
        unit_of_work_factory=factory, method_registry=registry, clock=lambda: NOW
    )
    scheduled = scheduler.schedule_run(run_id)
    executor = BatchExecutor(
        unit_of_work_factory=factory, method_registry=registry, clock=lambda: LATER
    )

    first = executor.execute(scheduled[0].message(), worker_task_id="w1", attempt_count=1)
    second = executor.execute(scheduled[0].message(), worker_task_id="w2", attempt_count=2)

    assert first.status is TaskBatchStatus.completed
    assert second.status is TaskBatchStatus.completed
    persisted = connection.execute(
        select(func.count())
        .select_from(PredictionRow)
        .where(PredictionRow.method_execution_id == scheduled[0].method_execution_id)
    ).scalar_one()
    assert persisted == 4  # re-execution created no duplicate predictions


def test_scheduling_rejects_a_non_created_run(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    scheduler = RunScheduler(
        unit_of_work_factory=factory,
        method_registry=default_method_registry(),
        clock=lambda: NOW,
    )
    run_id = _seed_created_run(factory)
    scheduler.schedule_run(run_id)

    with pytest.raises(InvalidResourceStateError):
        scheduler.schedule_run(run_id)
