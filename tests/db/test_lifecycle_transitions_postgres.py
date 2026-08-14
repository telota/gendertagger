from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.models.project import DatasetSnapshotCreate, ProjectCreate
from gendertagger.models.run import MethodExecution, MethodExecutionCreate, RunCreate, TaskBatch
from gendertagger.services.persistence_errors import InvalidResourceStateError
from gendertagger.services.task_batches import plan_task_batches

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 13, 12, 5, tzinfo=UTC)


def _setup(db_session: Session) -> tuple[SqlAlchemyRunRepository, MethodExecution, TaskBatch]:
    artifacts = SqlAlchemyArtifactRepository(db_session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/source.xml",
            sha256="a" * 64,
            byte_size=1,
            media_type="application/xml",
        )
    )
    projects = SqlAlchemyProjectRepository(db_session)
    project = projects.add_project(
        ProjectCreate(slug=f"life-{uuid4().hex}", display_name="Lifecycle project")
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source.id,
            source_sha256=source.sha256,
            parser_version="tei_parser_v1",
            import_config={"profile": "tei_p5_person_register_v1"},
        )
    )
    projects.begin_snapshot_import(snapshot.id)
    projects.add_person_records(snapshot.id, [PersonInput(tei_id="p0001")])
    projects.complete_snapshot_import(snapshot.id, ready_at=NOW)

    runs = SqlAlchemyRunRepository(db_session)
    run = runs.add_run(
        RunCreate(
            dataset_snapshot_id=snapshot.id,
            resolved_config=RunConfig(methods=[MethodRunConfig(name="demo_method")]),
            code_git_commit="abc123",
            application_version="0.0.0",
            python_version="3.11.0",
            dependency_lock_sha256="b" * 64,
        )
    )
    execution = runs.add_method_execution(
        MethodExecutionCreate(
            run_id=run.id,
            descriptor=MethodDescriptor(
                name="demo_method",
                implementation_version="1.0.0",
                normalization_version="demo_v1",
            ),
            queue_name="cpu",
            total_count=1,
        )
    )
    (batch,) = runs.create_task_batches(execution.id, plan_task_batches(1, batch_size=100))
    return runs, execution, batch


def test_run_advances_through_its_happy_path(db_session: Session) -> None:
    runs, execution, _ = _setup(db_session)
    run_id = execution.run_id

    assert runs.mark_run_queued(run_id).status is RunStatus.queued
    started = runs.mark_run_started(run_id, started_at=NOW)
    assert started.status is RunStatus.running
    assert started.started_at == NOW
    finished = runs.mark_run_finished(run_id, status=RunStatus.completed, finished_at=LATER)
    assert finished.status is RunStatus.completed
    assert finished.finished_at == LATER


def test_run_rejects_illegal_and_non_terminal_transitions(db_session: Session) -> None:
    runs, execution, _ = _setup(db_session)
    run_id = execution.run_id

    with pytest.raises(InvalidResourceStateError):
        runs.mark_run_started(run_id, started_at=NOW)  # still created, not queued
    runs.mark_run_queued(run_id)
    with pytest.raises(ValueError, match="not a terminal run status"):
        runs.mark_run_finished(run_id, status=RunStatus.running, finished_at=LATER)
    runs.mark_run_started(run_id, started_at=NOW)
    with pytest.raises(ValueError, match="failed run requires a failure diagnostic"):
        runs.mark_run_finished(run_id, status=RunStatus.failed, finished_at=LATER)


def test_execution_advances_and_records_failure(db_session: Session) -> None:
    runs, execution, _ = _setup(db_session)

    runs.mark_execution_queued(execution.id)
    runs.mark_execution_started(execution.id, started_at=NOW)
    finished = runs.mark_execution_finished(
        execution.id,
        status=MethodExecutionStatus.failed,
        finished_at=LATER,
        failure_class="RuntimeError",
        failure_diagnostic="adapter crashed",
    )
    assert finished.status is MethodExecutionStatus.failed
    assert finished.failure_class == "RuntimeError"
    assert finished.failure_diagnostic == "adapter crashed"


def test_batch_claimed_then_completed_records_tallies(db_session: Session) -> None:
    runs, execution, batch = _setup(db_session)

    running = runs.claim_batch(
        batch.id,
        method_execution_id=execution.id,
        worker_task_id="task-1",
        started_at=NOW,
        attempt_count=1,
    )
    assert running is not None
    assert running.status is TaskBatchStatus.running
    assert running.worker_task_id == "task-1"
    completed = runs.mark_batch_finished(
        batch.id,
        status=TaskBatchStatus.completed,
        finished_at=LATER,
        success_count=1,
        abstain_count=0,
        error_count=0,
    )
    assert completed.status is TaskBatchStatus.completed
    assert completed.success_count == 1


def test_batch_cannot_finish_before_it_starts(db_session: Session) -> None:
    runs, _, batch = _setup(db_session)

    with pytest.raises(InvalidResourceStateError):
        runs.mark_batch_finished(batch.id, status=TaskBatchStatus.completed, finished_at=LATER)


def test_completed_batch_tallies_must_cover_its_record_slice(db_session: Session) -> None:
    runs, execution, batch = _setup(db_session)
    runs.claim_batch(
        batch.id,
        method_execution_id=execution.id,
        worker_task_id="task-1",
        started_at=NOW,
        attempt_count=1,
    )

    with pytest.raises(ValueError, match="tallies must equal record_count"):
        runs.mark_batch_finished(
            batch.id,
            status=TaskBatchStatus.completed,
            finished_at=LATER,
        )


def test_failed_batch_counts_every_record_as_error(db_session: Session) -> None:
    runs, execution, batch = _setup(db_session)
    runs.claim_batch(
        batch.id,
        method_execution_id=execution.id,
        worker_task_id="task-1",
        started_at=NOW,
        attempt_count=1,
    )

    with pytest.raises(ValueError, match="count every record as an error"):
        runs.mark_batch_finished(
            batch.id,
            status=TaskBatchStatus.failed,
            finished_at=LATER,
            failure_diagnostic="adapter failed",
        )

    failed = runs.mark_batch_finished(
        batch.id,
        status=TaskBatchStatus.failed,
        finished_at=LATER,
        error_count=batch.record_count,
        failure_class="RuntimeError",
        failure_diagnostic="adapter failed",
    )
    assert failed.status is TaskBatchStatus.failed
    assert failed.error_count == batch.record_count


def test_transitions_reject_unknown_resources(db_session: Session) -> None:
    _setup(db_session)
    runs = SqlAlchemyRunRepository(db_session)

    with pytest.raises(LookupError):
        runs.mark_run_queued(uuid4())
