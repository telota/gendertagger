from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.aggregations import AggregationExecutionRow
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.executions import MethodExecutionRow, PredictionRow, RunRow, TaskBatchRow
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    MethodExecutionStatus,
    RunStatus,
    TaskBatchStatus,
)
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import ImportedPerson, PersonInput
from gendertagger.models.project import (
    DatasetSnapshotCreate,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotSourceMemberCreate,
)
from gendertagger.models.run import (
    MethodExecution,
    MethodExecutionCreate,
    PredictionWrite,
    RunCreate,
    TaskBatch,
)
from gendertagger.services.persistence_errors import InvalidResourceStateError
from gendertagger.services.task_batches import plan_task_batches

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 13, 12, 5, tzinfo=UTC)


def _setup(
    db_session: Session,
) -> tuple[SqlAlchemyRunRepository, MethodExecution, TaskBatch, UUID]:
    projects = SqlAlchemyProjectRepository(db_session)
    project = projects.add_project(
        ProjectCreate(slug=f"life-{uuid4().hex}", display_name="Lifecycle project")
    )
    artifacts = SqlAlchemyArtifactRepository(db_session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/source.xml",
            sha256="a" * 64,
            byte_size=1,
            media_type="application/xml",
            project_id=project.id,
        )
    )
    import_config = SnapshotImportConfig(limits=SnapshotImportLimits())
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source.id,
            source_sha256=source.sha256,
            parser_version=version_for_snapshot_import(import_config),
            import_config=import_config.model_dump(mode="json"),
        )
    )
    projects.add_snapshot_source_members(
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
    projects.begin_snapshot_import(snapshot.id)
    projects.add_imported_person_records(
        snapshot.id,
        [
            ImportedPerson(
                person=PersonInput(tei_id="p0001"),
                source_member_name="source.xml",
                source_record_locator="1",
            )
        ],
    )
    projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
    person = projects.get_person_record_by_tei_id(snapshot.id, "p0001")
    assert person is not None

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
    return runs, execution, batch, person.id


def _start_execution(runs: SqlAlchemyRunRepository, execution: MethodExecution) -> None:
    runs.mark_run_queued(execution.run_id)
    runs.mark_run_started(execution.run_id, started_at=NOW)
    runs.mark_execution_queued(execution.id)
    runs.mark_execution_started(execution.id, started_at=NOW)


def _claim_batch(
    runs: SqlAlchemyRunRepository,
    execution: MethodExecution,
    batch: TaskBatch,
) -> None:
    claimed = runs.claim_batch(
        batch.id,
        method_execution_id=execution.id,
        worker_task_id="task-1",
        started_at=NOW,
        attempt_count=1,
    )
    assert claimed is not None


def _fail_execution(
    runs: SqlAlchemyRunRepository,
    execution: MethodExecution,
    batch: TaskBatch,
) -> None:
    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)
    runs.mark_batch_finished(
        batch.id,
        status=TaskBatchStatus.failed,
        finished_at=LATER,
        error_count=batch.record_count,
        failure_class="RuntimeError",
        failure_diagnostic="adapter crashed",
    )
    runs.mark_execution_finished(
        execution.id,
        status=MethodExecutionStatus.failed,
        finished_at=LATER,
        failure_class="RuntimeError",
        failure_diagnostic="adapter crashed",
    )


def _fail_run(
    runs: SqlAlchemyRunRepository,
    execution: MethodExecution,
    batch: TaskBatch,
) -> None:
    _fail_execution(runs, execution, batch)
    runs.mark_run_finished(
        execution.run_id,
        status=RunStatus.failed,
        finished_at=LATER,
        failure_diagnostic="method execution failed",
    )


def _prediction(person_id: UUID, batch_id: UUID) -> PredictionWrite:
    return PredictionWrite(
        person_record_id=person_id,
        task_batch_id=batch_id,
        input_fingerprint="c" * 64,
        result=PredictionResult(
            label=CanonicalLabel.unknown,
            status=PredictionStatus.success,
        ),
    )


def _mutate_and_flush(session: Session, mutation: Callable[[], object]) -> None:
    mutation()
    session.flush()


def _assert_database_rejects(
    session: Session,
    mutation: Callable[[], object],
    *,
    sqlstate: str,
    message: str,
) -> None:
    with pytest.raises(DBAPIError, match=message) as error, session.begin_nested():
        _mutate_and_flush(session, mutation)
    assert getattr(error.value.orig, "sqlstate", None) == sqlstate
    session.expire_all()


def _assert_deferred_constraints_reject(session: Session, *, message: str) -> None:
    with pytest.raises(DBAPIError, match=message) as error, session.begin_nested():
        session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert getattr(error.value.orig, "sqlstate", None) == "23514"
    session.expire_all()


def test_run_advances_through_its_happy_path(db_session: Session) -> None:
    runs, execution, batch, person_id = _setup(db_session)
    run_id = execution.run_id

    assert runs.mark_run_queued(run_id).status is RunStatus.queued
    started = runs.mark_run_started(run_id, started_at=NOW)
    assert started.status is RunStatus.running
    assert started.started_at == NOW
    runs.mark_execution_queued(execution.id)
    runs.mark_execution_started(execution.id, started_at=NOW)
    _claim_batch(runs, execution, batch)
    runs.add_predictions(execution.id, [_prediction(person_id, batch.id)])
    runs.mark_batch_finished(
        batch.id,
        status=TaskBatchStatus.completed,
        finished_at=LATER,
        success_count=1,
    )
    runs.finalize_execution_if_complete(execution.id, finished_at=LATER)
    finished = runs.mark_run_finished(run_id, status=RunStatus.completed, finished_at=LATER)
    assert finished.status is RunStatus.completed
    assert finished.finished_at == LATER


def test_run_rejects_illegal_and_non_terminal_transitions(db_session: Session) -> None:
    runs, execution, _, _ = _setup(db_session)
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
    runs, execution, batch, _ = _setup(db_session)

    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)
    runs.mark_batch_finished(
        batch.id,
        status=TaskBatchStatus.failed,
        finished_at=LATER,
        error_count=1,
        failure_class="RuntimeError",
        failure_diagnostic="adapter crashed",
    )
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


def test_execution_cannot_finish_with_a_nonterminal_batch(db_session: Session) -> None:
    runs, execution, _batch, _person_id = _setup(db_session)
    _start_execution(runs, execution)

    _assert_database_rejects(
        db_session,
        lambda: runs.mark_execution_finished(
            execution.id,
            status=MethodExecutionStatus.completed,
            finished_at=LATER,
        ),
        sqlstate="23514",
        message="cannot finish before all task batches are terminal",
    )


def test_run_cannot_finish_with_a_nonterminal_execution(db_session: Session) -> None:
    runs, execution, _batch, _person_id = _setup(db_session)
    runs.mark_run_queued(execution.run_id)
    runs.mark_run_started(execution.run_id, started_at=NOW)

    _assert_database_rejects(
        db_session,
        lambda: runs.mark_run_finished(
            execution.run_id,
            status=RunStatus.completed,
            finished_at=LATER,
        ),
        sqlstate="23514",
        message="cannot finish before all method executions are terminal",
    )


def test_batch_claimed_then_completed_records_tallies(db_session: Session) -> None:
    runs, execution, batch, person_id = _setup(db_session)

    _start_execution(runs, execution)
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
    runs.add_predictions(execution.id, [_prediction(person_id, batch.id)])
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
    runs, execution, batch, _ = _setup(db_session)
    _start_execution(runs, execution)

    with pytest.raises(InvalidResourceStateError):
        runs.mark_batch_finished(batch.id, status=TaskBatchStatus.completed, finished_at=LATER)


def test_completed_batch_tallies_must_cover_its_record_slice(db_session: Session) -> None:
    runs, execution, batch, _ = _setup(db_session)
    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)

    with pytest.raises(ValueError, match="tallies must equal record_count"):
        runs.mark_batch_finished(
            batch.id,
            status=TaskBatchStatus.completed,
            finished_at=LATER,
        )


def test_failed_batch_counts_every_record_as_error(db_session: Session) -> None:
    runs, execution, batch, _ = _setup(db_session)
    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)

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


def test_prediction_writes_require_the_running_lifecycle(db_session: Session) -> None:
    runs, execution, batch, person_id = _setup(db_session)
    prediction = _prediction(person_id, batch.id)

    with pytest.raises(InvalidResourceStateError, match=r"run .* must be running"):
        runs.add_predictions(execution.id, [prediction])

    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)
    assert runs.add_predictions(execution.id, [prediction]) == 1
    runs.mark_batch_finished(
        batch.id,
        status=TaskBatchStatus.completed,
        finished_at=LATER,
        success_count=1,
    )

    with pytest.raises(InvalidResourceStateError, match=r"task batch .* must be running"):
        runs.add_predictions(execution.id, [prediction])


def test_prediction_writes_require_one_exact_batch_slice(db_session: Session) -> None:
    runs, execution, batch, person_id = _setup(db_session)
    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)

    with pytest.raises(ValueError, match="must not be empty"):
        runs.add_predictions(execution.id, [])
    with pytest.raises(ValueError, match="exactly one task batch"):
        runs.add_predictions(
            execution.id,
            [
                _prediction(person_id, batch.id),
                _prediction(person_id, uuid4()),
            ],
        )
    with pytest.raises(InvalidResourceStateError, match="must exactly cover its person slice"):
        runs.add_predictions(execution.id, [_prediction(uuid4(), batch.id)])


@pytest.mark.parametrize(
    ("resource", "attribute", "replacement"),
    [
        ("run", "resolved_config", {"methods": []}),
        ("execution", "implementation_version", "rewritten_v2"),
        ("batch", "record_offset", 1),
    ],
)
def test_database_rejects_execution_provenance_mutation(
    db_session: Session,
    resource: str,
    attribute: str,
    replacement: object,
) -> None:
    _runs, execution, batch, _person_id = _setup(db_session)
    row = {
        "run": db_session.get(RunRow, execution.run_id),
        "execution": db_session.get(MethodExecutionRow, execution.id),
        "batch": db_session.get(TaskBatchRow, batch.id),
    }[resource]
    assert row is not None
    _assert_database_rejects(
        db_session,
        lambda: setattr(row, attribute, replacement),
        sqlstate="55000",
        message="provenance is immutable",
    )


def test_database_rejects_skipping_run_lifecycle_states(db_session: Session) -> None:
    _runs, execution, _batch, _person_id = _setup(db_session)
    row = db_session.get(RunRow, execution.run_id)
    assert row is not None

    def skip_states() -> None:
        row.status = RunStatus.completed
        row.started_at = NOW
        row.finished_at = LATER

    _assert_database_rejects(
        db_session,
        skip_states,
        sqlstate="23514",
        message="illegal runs lifecycle transition",
    )


def test_database_seals_terminal_execution_rows(db_session: Session) -> None:
    runs, execution, batch, _person_id = _setup(db_session)
    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)
    runs.mark_batch_finished(
        batch.id,
        status=TaskBatchStatus.failed,
        finished_at=LATER,
        error_count=1,
        failure_class="RuntimeError",
        failure_diagnostic="adapter crashed",
    )
    row = db_session.get(TaskBatchRow, batch.id)
    assert row is not None

    _assert_database_rejects(
        db_session,
        lambda: setattr(row, "worker_task_id", "rewritten-task"),
        sqlstate="55000",
        message="terminal task_batches rows are immutable",
    )


def test_deferred_guard_rejects_predictions_without_batch_completion(
    db_session: Session,
) -> None:
    runs, execution, batch, person_id = _setup(db_session)
    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)
    runs.add_predictions(execution.id, [_prediction(person_id, batch.id)])

    _assert_deferred_constraints_reject(
        db_session,
        message="committed predictions require a completed task batch",
    )


def test_deferred_guard_rejects_completed_batch_without_predictions(
    db_session: Session,
) -> None:
    runs, execution, batch, _person_id = _setup(db_session)
    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)
    runs.mark_batch_finished(
        batch.id,
        status=TaskBatchStatus.completed,
        finished_at=LATER,
        success_count=1,
    )

    _assert_deferred_constraints_reject(
        db_session,
        message="completed task batch requires exact prediction coverage and tallies",
    )


@pytest.mark.parametrize(
    "child_resource",
    ["method execution", "task batch"],
)
def test_database_rejects_child_inserts_after_parent_is_terminal(
    db_session: Session,
    child_resource: str,
) -> None:
    runs, execution, batch, _person_id = _setup(db_session)
    child: MethodExecutionRow | TaskBatchRow | AggregationExecutionRow
    if child_resource == "task batch":
        _fail_execution(runs, execution, batch)
        child = TaskBatchRow(
            method_execution_id=execution.id,
            batch_index=1,
            record_offset=1,
            record_count=1,
            status=TaskBatchStatus.pending,
            queue_name="cpu",
        )
    else:
        _fail_run(runs, execution, batch)
        child = MethodExecutionRow(
            run_id=execution.run_id,
            method_name="late_method",
            implementation_version="test_v1",
            normalization_version="test_v1",
            resolved_config={},
            config_sha256="d" * 64,
            status=MethodExecutionStatus.pending,
            queue_name="cpu",
        )

    _assert_database_rejects(
        db_session,
        lambda: db_session.add(child),
        sqlstate="23514",
        message="terminal",
    )


@pytest.mark.parametrize("resource", ["run", "method execution", "task batch", "aggregation"])
def test_database_rejects_deleting_lifecycle_rows(
    db_session: Session,
    resource: str,
) -> None:
    _runs, execution, batch, _person_id = _setup(db_session)
    aggregation = AggregationExecutionRow(
        run_id=execution.run_id,
        strategy="reference_v1",
        resolved_config={},
        config_sha256="d" * 64,
        status=AggregationExecutionStatus.pending,
    )
    db_session.add(aggregation)
    db_session.flush()
    rows: dict[
        str,
        RunRow | MethodExecutionRow | TaskBatchRow | AggregationExecutionRow | None,
    ] = {
        "run": db_session.get(RunRow, execution.run_id),
        "method execution": db_session.get(MethodExecutionRow, execution.id),
        "task batch": db_session.get(TaskBatchRow, batch.id),
        "aggregation": aggregation,
    }
    row = rows[resource]
    assert row is not None

    _assert_database_rejects(
        db_session,
        lambda: db_session.delete(row),
        sqlstate="55000",
        message="cannot be deleted",
    )


def test_database_rejects_running_lifecycle_without_start_timestamp(
    db_session: Session,
) -> None:
    runs, execution, _batch, _person_id = _setup(db_session)
    runs.mark_run_queued(execution.run_id)
    row = db_session.get(RunRow, execution.run_id)
    assert row is not None

    _assert_database_rejects(
        db_session,
        lambda: setattr(row, "status", RunStatus.running),
        sqlstate="23514",
        message="started_at",
    )


def test_database_rejects_failed_lifecycle_without_failure_details(
    db_session: Session,
) -> None:
    runs, execution, batch, _person_id = _setup(db_session)
    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)
    row = db_session.get(TaskBatchRow, batch.id)
    assert row is not None

    def fail_without_diagnostic() -> None:
        row.status = TaskBatchStatus.failed
        row.finished_at = LATER
        row.error_count = batch.record_count

    _assert_database_rejects(
        db_session,
        fail_without_diagnostic,
        sqlstate="23514",
        message="failure",
    )


def test_database_rejects_raw_prediction_insert_outside_running_lifecycle(
    db_session: Session,
) -> None:
    _runs, execution, batch, person_id = _setup(db_session)
    row = PredictionRow(
        method_execution_id=execution.id,
        person_record_id=person_id,
        task_batch_id=batch.id,
        label=CanonicalLabel.unknown,
        status=PredictionStatus.success,
        raw_output={},
        prediction_metadata={},
        input_fingerprint="e" * 64,
    )

    _assert_database_rejects(
        db_session,
        lambda: db_session.add(row),
        sqlstate="23514",
        message="running owning run, execution, and batch",
    )


def test_database_rejects_raw_prediction_outside_the_batch_slice(
    db_session: Session,
) -> None:
    runs, execution, batch, _person_id = _setup(db_session)
    _start_execution(runs, execution)
    _claim_batch(runs, execution, batch)
    row = PredictionRow(
        method_execution_id=execution.id,
        person_record_id=uuid4(),
        task_batch_id=batch.id,
        label=CanonicalLabel.unknown,
        status=PredictionStatus.success,
        raw_output={},
        prediction_metadata={},
        input_fingerprint="e" * 64,
    )

    _assert_database_rejects(
        db_session,
        lambda: db_session.add(row),
        sqlstate="23514",
        message="prediction person must belong to the owning batch slice",
    )
