from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from queue import Queue
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from tests.factories import tei_person_input
from tests.seeding import (
    always_abstain,
    legacy_snapshot_statistics,
    seed_completed_aggregation,
    seed_completed_run,
    seed_project,
    seed_ready_snapshot,
    seed_worker_provenance,
    session_repositories,
)

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.repositories.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.repositories.dispatch_repository import SqlAlchemyDispatchRepository
from gendertagger.db.repositories.evaluation_repository import SqlAlchemyEvaluationRepository
from gendertagger.db.repositories.export_repository import SqlAlchemyExportRepository
from gendertagger.db.repositories.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.repositories.public_classification_repository import (
    SqlAlchemyPublicClassificationRepository,
)
from gendertagger.db.repositories.run_repository import SqlAlchemyRunRepository
from gendertagger.db.rows.aggregations import AggregationExecutionRow, AggregationMethodExecutionRow
from gendertagger.db.rows.dispatches import DispatchOutboxRow
from gendertagger.db.rows.evaluations import EvaluationExecutionRow
from gendertagger.db.rows.executions import TaskBatchRow
from gendertagger.db.rows.exports import ExportExecutionRow
from gendertagger.db.rows.projects import DatasetSnapshotRow
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.models.artifact import ArtifactCreate
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
from gendertagger.models.evaluation import (
    EvaluationDefinition,
    EvaluationExecutionCreate,
    EvaluationTaskMessage,
)
from gendertagger.models.export import ExportExecutionCreate, ExportFormat, ExportTaskMessage
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import ImportedPerson
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotImportTaskMessage,
    SnapshotSourceMemberCreate,
    SourceFormat,
    SourcePackaging,
    TeiImportProfile,
)
from gendertagger.models.public_classification import (
    PublicClassificationJobRecord,
    PublicClassificationProvenance,
    PublicClassificationStatus,
    PublicClassificationTaskMessage,
)
from gendertagger.models.run import (
    MethodExecution,
    MethodExecutionCreate,
    Run,
    RunCreate,
    TaskBatch,
    TaskBatchMessage,
    TaskBatchPlan,
)
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

_DISPATCH_KINDS = (
    (DispatchTarget.task_batch, BatchDispatch),
    (DispatchTarget.aggregation_execution, AggregationDispatch),
    (DispatchTarget.dataset_snapshot, SnapshotDispatch),
    (DispatchTarget.evaluation_execution, EvaluationDispatch),
    (DispatchTarget.export, ExportDispatch),
    (DispatchTarget.public_classification_job, PublicClassificationDispatch),
)


def _execution_context(
    session: Session,
    *,
    scheduled: bool = False,
) -> tuple[SqlAlchemyRunRepository, Run, MethodExecution, TaskBatch]:
    now = datetime.now(UTC)
    repositories = session_repositories(session)
    projects = repositories.projects
    project = seed_project(
        repositories,
        slug_prefix="dispatch",
        display_name="Dispatch repository project",
    )
    artifacts = SqlAlchemyArtifactRepository(session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri=f"local-sha256:{uuid4().hex}",
            sha256=uuid4().hex * 2,
            byte_size=1,
            media_type="application/xml",
            project_id=project.id,
        )
    )
    import_config = SnapshotImportConfig(
        source_format=SourceFormat.tei,
        packaging=SourcePackaging.single,
        profile=TeiImportProfile.tei_p5_person_register,
        limits=SnapshotImportLimits(),
    )
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
    assert projects.claim_snapshot_import(snapshot.id) is not None
    projects.add_imported_person_records(
        snapshot.id,
        [
            ImportedPerson(
                person=tei_person_input(tei_id="p1"),
                source_member_name="source.xml",
                source_record_locator="1",
            ),
            ImportedPerson(
                person=tei_person_input(tei_id="p2"),
                source_member_name="source.xml",
                source_record_locator="2",
            ),
        ],
    )
    projects.complete_snapshot_import(
        snapshot.id,
        statistics=legacy_snapshot_statistics(
            snapshot.id,
            [
                tei_person_input(tei_id="p1"),
                tei_person_input(tei_id="p2"),
            ],
        ),
        ready_at=now,
    )

    runs = SqlAlchemyRunRepository(session)
    run = runs.add_run(
        RunCreate(
            dataset_snapshot_id=snapshot.id,
            resolved_config=RunConfig(
                methods=[
                    MethodRunConfig(name="demo_method"),
                    MethodRunConfig(name="aggregation_fixture"),
                ]
            ),
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
            total_count=2,
        )
    )
    (batch,) = runs.create_task_batches(
        execution.id, [TaskBatchPlan(batch_index=0, record_offset=0, record_count=1)]
    )
    if scheduled:
        run = runs.mark_run_queued(run.id)
        execution = runs.mark_execution_queued(execution.id)
    return runs, run, execution, batch


def _dispatch_command(
    batch: TaskBatch,
    execution_id: UUID,
    *,
    available_at: datetime,
) -> BatchDispatchCreate:
    return BatchDispatchCreate(
        task_batch_id=batch.id,
        queue_name=batch.queue_name,
        payload=TaskBatchMessage(
            method_execution_id=execution_id,
            task_batch_id=batch.id,
        ),
        available_at=available_at,
    )


def _aggregation_context(
    session: Session,
    *,
    status: AggregationExecutionStatus = AggregationExecutionStatus.pending,
) -> AggregationExecutionRow:
    runs, run, _, _ = _execution_context(session)
    member = runs.add_method_execution(
        MethodExecutionCreate(
            run_id=run.id,
            descriptor=MethodDescriptor(
                name="aggregation_fixture",
                implementation_version="1.0.0",
                normalization_version="aggregation_fixture_v1",
            ),
            queue_name="cpu",
            total_count=0,
        )
    )
    runs.mark_run_queued(run.id)
    runs.mark_run_started(run.id, started_at=datetime.now(UTC))
    runs.mark_execution_queued(member.id)
    runs.mark_execution_started(member.id, started_at=datetime.now(UTC))
    runs.finalize_execution_if_complete(member.id, finished_at=datetime.now(UTC))
    row = AggregationExecutionRow(
        run_id=run.id,
        strategy="reference_v1",
        resolved_config={},
        config_sha256="a" * 64,
        status=AggregationExecutionStatus.pending,
    )
    session.add(row)
    session.flush()
    session.add(
        AggregationMethodExecutionRow(
            aggregation_execution_id=row.id,
            method_execution_id=member.id,
            position=0,
        )
    )
    session.flush()
    if status is not AggregationExecutionStatus.pending:
        row.status = status
        if status is AggregationExecutionStatus.running:
            row.started_at = datetime.now(UTC)
        session.flush()
    return row


def _aggregation_dispatch_command(
    aggregation: AggregationExecutionRow,
    *,
    available_at: datetime,
) -> AggregationDispatchCreate:
    return AggregationDispatchCreate(
        aggregation_execution_id=aggregation.id,
        queue_name="cpu",
        payload=AggregationTaskMessage(aggregation_execution_id=aggregation.id),
        available_at=available_at,
    )


def _pending_snapshot_context(
    session: Session,
) -> tuple[SqlAlchemyProjectRepository, DatasetSnapshot]:
    repositories = session_repositories(session)
    projects = repositories.projects
    project = seed_project(
        repositories,
        slug_prefix="snapshot-dispatch",
        display_name="Snapshot dispatch repository project",
    )
    artifacts = SqlAlchemyArtifactRepository(session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri=f"file:///synthetic/snapshot-dispatch-{uuid4().hex}.xml",
            sha256=uuid4().hex * 2,
            byte_size=1,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    import_config = SnapshotImportConfig(
        source_format=SourceFormat.tei,
        packaging=SourcePackaging.single,
        profile=TeiImportProfile.tei_p5_person_register,
        limits=SnapshotImportLimits(),
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source.id,
            source_sha256=source.sha256,
            parser_version=version_for_snapshot_import(import_config),
            import_config=import_config.model_dump(mode="json"),
        )
    )
    return projects, snapshot


def _snapshot_dispatch_command(
    snapshot: DatasetSnapshot,
    *,
    available_at: datetime,
    queue_name: str = "cpu",
) -> SnapshotDispatchCreate:
    return SnapshotDispatchCreate(
        dataset_snapshot_id=snapshot.id,
        queue_name=queue_name,
        payload=SnapshotImportTaskMessage(dataset_snapshot_id=snapshot.id),
        available_at=available_at,
    )


def _classification_context(
    session: Session,
    *,
    created_at: datetime,
) -> PublicClassificationJobRecord:
    job = PublicClassificationJobRecord(
        id=uuid4(),
        queue_name="llm",
        retrieval_token_sha256="a" * 64,
        names=["Ada"],
        methods=["dispatch_fixture"],
        resolved_method_configs={"dispatch_fixture": {}},
        provenance=PublicClassificationProvenance(
            methods=[
                MethodDescriptor(
                    name="dispatch_fixture",
                    implementation_version="1",
                    normalization_version="1",
                )
            ],
            method_configs={"dispatch_fixture": {}},
            resolved_config_sha256="b" * 64,
            code_git_commit="dispatch-test-revision",
            application_version="0.0.0",
            python_version="3.11.0",
            dependency_lock_sha256="c" * 64,
            dependency_versions={"gendertagger": "0.0.0"},
        ),
        created_at=created_at,
    )
    return SqlAlchemyPublicClassificationRepository(session).add_job(job)


def _dispatch_context(
    session: Session,
    target: DispatchTarget,
    *,
    available_at: datetime,
) -> DispatchCreate:
    if target is DispatchTarget.task_batch:
        _, _, execution, batch = _execution_context(session)
        return _dispatch_command(batch, execution.id, available_at=available_at)
    if target is DispatchTarget.aggregation_execution:
        aggregation = _aggregation_context(session)
        return _aggregation_dispatch_command(aggregation, available_at=available_at)
    if target is DispatchTarget.dataset_snapshot:
        _, snapshot = _pending_snapshot_context(session)
        return _snapshot_dispatch_command(snapshot, available_at=available_at)
    if target is DispatchTarget.public_classification_job:
        job = _classification_context(session, created_at=available_at)
        return PublicClassificationDispatchCreate(
            classification_job_id=job.id,
            queue_name=job.queue_name,
            payload=PublicClassificationTaskMessage(classification_job_id=job.id),
            available_at=available_at,
        )

    repositories = session_repositories(session)
    project = seed_project(repositories, slug_prefix="terminal-dispatch")
    snapshot = seed_ready_snapshot(repositories, project.id, [])
    definition = EvaluationDefinition()
    method_names = (
        definition.required_methods
        if target is DispatchTarget.evaluation_execution
        else REFERENCE_REQUIRED_METHODS
    )
    completed = seed_completed_run(repositories, snapshot, method_names, always_abstain)
    if target is DispatchTarget.evaluation_execution:
        evaluation = SqlAlchemyEvaluationRepository(session).add_evaluation(
            EvaluationExecutionCreate(
                run_id=completed.run.id,
                method_execution_ids=completed.execution_ids,
                resolved_config=definition.model_dump(mode="json"),
            )
        )
        return EvaluationDispatchCreate(
            evaluation_execution_id=evaluation.id,
            queue_name="cpu",
            payload=EvaluationTaskMessage(evaluation_execution_id=evaluation.id),
            available_at=available_at,
        )

    aggregation_execution = seed_completed_aggregation(
        repositories, completed.run.id, completed.execution_ids
    )
    export = SqlAlchemyExportRepository(session).add_export(
        ExportExecutionCreate(
            run_id=completed.run.id,
            aggregation_execution_id=aggregation_execution.id,
            format=ExportFormat.json,
        )
    )
    return ExportDispatchCreate(
        export_execution_id=export.id,
        queue_name="cpu",
        payload=ExportTaskMessage(export_execution_id=export.id),
        available_at=available_at,
    )


@pytest.mark.parametrize(("target", "dispatch_type"), _DISPATCH_KINDS)
def test_concurrent_ensure_dispatch_persists_one_exact_intent_for_each_target(
    postgres_engine: Engine,
    target: DispatchTarget,
    dispatch_type: type[Dispatch],
) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as seed_session:
        command = _dispatch_context(seed_session, target, available_at=now)
        seed_session.commit()
    competing_command = command.model_copy(update={"available_at": now + timedelta(hours=1)})
    competing_pid: Queue[int] = Queue()

    def ensure_competing_dispatch() -> Dispatch:
        with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
            competing_pid.put(session.execute(text("SELECT pg_backend_pid()")).scalar_one())
            dispatch = SqlAlchemyDispatchRepository(session).ensure_dispatch(competing_command)
            session.commit()
            return dispatch

    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as first_session:
        first_pid = first_session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        first = SqlAlchemyDispatchRepository(first_session).ensure_dispatch(command)
        observed_conflict_wait = False
        with ThreadPoolExecutor(max_workers=1) as pool:
            competing = pool.submit(ensure_competing_dispatch)
            try:
                second_pid = competing_pid.get(timeout=5)
                deadline = monotonic() + 5
                with postgres_engine.connect() as observer:
                    while monotonic() < deadline and not competing.done():
                        if observer.execute(
                            text("SELECT :owner = ANY(pg_blocking_pids(:contender))"),
                            {"owner": first_pid, "contender": second_pid},
                        ).scalar_one():
                            observed_conflict_wait = True
                            break
                        sleep(0.01)
            finally:
                first_session.commit()
            second = competing.result(timeout=5)

    assert observed_conflict_wait, "the contender must race the uncommitted unique target"
    assert type(first) is dispatch_type
    assert type(second) is dispatch_type
    assert second == first
    assert first.target is target
    assert first.target_id == command.target_id
    assert first.queue_name == command.queue_name
    assert first.payload == command.payload
    assert first.available_at == now
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
        assert tuple(session.scalars(select(DispatchOutboxRow.id))) == (first.id,)
        assert SqlAlchemyDispatchRepository(session).get_dispatch(first.id) == first


@pytest.mark.parametrize(("target", "dispatch_type"), _DISPATCH_KINDS)
def test_exact_dispatch_replay_preserves_retry_lease_and_publication_for_each_target(
    db_session: Session,
    target: DispatchTarget,
    dispatch_type: type[Dispatch],
) -> None:
    now = datetime.now(UTC)
    command = _dispatch_context(db_session, target, available_at=now)
    repository = SqlAlchemyDispatchRepository(db_session)
    first = repository.ensure_dispatch(command)
    assert type(first) is dispatch_type
    assert (
        repository.ensure_dispatch(
            command.model_copy(update={"available_at": now + timedelta(hours=1)})
        )
        == first
    )
    with pytest.raises(InvalidResourceStateError):
        repository.ensure_dispatch(
            command.model_copy(
                update={"queue_name": "cpu" if command.queue_name == "llm" else "llm"}
            )
        )
    assert repository.get_dispatch(first.id) == first

    (claimed,) = repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )
    assert repository.ensure_dispatch(command) == claimed
    retry_at = now + timedelta(minutes=1)
    released = repository.release_after_failure(
        first.id,
        lease_owner="relay-1",
        available_at=retry_at,
        last_error="broker unavailable",
    )
    assert repository.ensure_dispatch(command) == released
    assert released.available_at == retry_at
    assert released.last_error == "broker unavailable"
    assert (
        repository.claim_available(
            now=retry_at - timedelta(microseconds=1),
            lease_owner="relay-2",
            lease_until=retry_at + timedelta(seconds=30),
            limit=1,
        )
        == ()
    )
    (reclaimed,) = repository.claim_available(
        now=retry_at,
        lease_owner="relay-2",
        lease_until=retry_at + timedelta(seconds=30),
        limit=1,
    )
    assert repository.ensure_dispatch(command) == reclaimed
    expiry = retry_at + timedelta(seconds=30)
    (replacement,) = repository.claim_available(
        now=expiry,
        lease_owner="relay-3",
        lease_until=expiry + timedelta(seconds=30),
        limit=1,
    )
    assert replacement.attempt_count == 3
    assert repository.ensure_dispatch(command) == replacement
    with pytest.raises(InvalidResourceStateError, match="not leased"):
        repository.mark_published(first.id, lease_owner="relay-2", published_at=expiry)
    published = repository.mark_published(
        first.id,
        lease_owner="relay-3",
        published_at=expiry,
    )
    assert published.status is DispatchStatus.published
    assert published.published_at == expiry
    assert published.lease_owner is None
    assert published.lease_until is None
    assert published.last_error is None
    assert (
        repository.ensure_dispatch(
            command.model_copy(update={"available_at": expiry + timedelta(hours=1)})
        )
        == published
    )


@pytest.mark.parametrize("conflicting_field", ["queue", "payload"])
def test_ensure_dispatch_rejects_a_preexisting_conflicting_batch_intent(
    db_session: Session,
    conflicting_field: str,
) -> None:
    _, _, execution, batch = _execution_context(db_session)
    command = _dispatch_command(batch, execution.id, available_at=datetime.now(UTC))
    stored_queue = "llm" if conflicting_field == "queue" else command.queue_name
    stored_payload = TaskBatchMessage(
        task_batch_id=batch.id,
        method_execution_id=uuid4() if conflicting_field == "payload" else execution.id,
    )
    row = DispatchOutboxRow(
        task_batch_id=batch.id,
        queue_name=stored_queue,
        payload=stored_payload.model_dump(mode="json"),
        available_at=command.available_at,
    )
    db_session.add(row)
    db_session.flush()
    repository = SqlAlchemyDispatchRepository(db_session)
    original = repository.get_dispatch(row.id)

    with pytest.raises(InvalidResourceStateError, match="has a different dispatch intent"):
        repository.ensure_dispatch(command)

    assert repository.get_dispatch(row.id) == original
    assert tuple(db_session.scalars(select(DispatchOutboxRow.id))) == (row.id,)


def test_ensure_dispatch_is_idempotent_per_task_batch(db_session: Session) -> None:
    _, _, execution, batch = _execution_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    command = _dispatch_command(batch, execution.id, available_at=datetime.now(UTC))

    first = repository.ensure_dispatch(command)
    second = repository.ensure_dispatch(command)

    assert first.id == second.id
    assert first.payload == command.payload
    assert first.status is DispatchStatus.pending
    assert repository.get_dispatch(first.id) == first
    assert repository.get_dispatch_for_batch(batch.id) == first


def test_ensure_dispatch_is_exact_and_idempotent_per_aggregation(
    db_session: Session,
) -> None:
    aggregation = _aggregation_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)
    command = _aggregation_dispatch_command(aggregation, available_at=now)

    first = repository.ensure_dispatch(command)
    second = repository.ensure_dispatch(command)

    assert first.id == second.id
    assert first.payload == command.payload
    assert repository.get_dispatch(first.id) == first
    assert repository.get_dispatch_for_aggregation(aggregation.id) == first

    rescheduled = repository.ensure_dispatch(
        _aggregation_dispatch_command(
            aggregation,
            available_at=now + timedelta(seconds=1),
        )
    )

    assert rescheduled.id == first.id
    assert rescheduled.available_at == now


def test_ensure_dispatch_is_exact_and_idempotent_per_snapshot(
    db_session: Session,
) -> None:
    _, snapshot = _pending_snapshot_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)
    command = _snapshot_dispatch_command(snapshot, available_at=now)

    first = repository.ensure_dispatch(command)
    second = repository.ensure_dispatch(command)

    assert first.id == second.id
    assert first.payload == command.payload
    assert first.status is DispatchStatus.pending
    assert repository.get_dispatch(first.id) == first
    assert repository.get_dispatch_for_snapshot(snapshot.id) == first

    rescheduled = repository.ensure_dispatch(
        _snapshot_dispatch_command(
            snapshot,
            available_at=now + timedelta(seconds=1),
        )
    )

    assert rescheduled.id == first.id
    assert rescheduled.available_at == now


@pytest.mark.parametrize(
    ("has_batch", "has_aggregation", "has_snapshot"),
    [
        pytest.param(False, False, False, id="no-owner"),
        pytest.param(True, True, False, id="batch-and-aggregation"),
        pytest.param(True, False, True, id="batch-and-snapshot"),
        pytest.param(False, True, True, id="aggregation-and-snapshot"),
        pytest.param(True, True, True, id="all-owners"),
    ],
)
def test_dispatch_schema_rejects_zero_or_multiple_owners(
    db_session: Session,
    *,
    has_batch: bool,
    has_aggregation: bool,
    has_snapshot: bool,
) -> None:
    _, run, _, batch = _execution_context(db_session)
    aggregation = AggregationExecutionRow(
        run_id=run.id,
        strategy="reference_v1",
        resolved_config={},
        config_sha256="a" * 64,
        status=AggregationExecutionStatus.pending,
    )
    db_session.add(aggregation)
    db_session.flush()
    _, snapshot = _pending_snapshot_context(db_session)

    with pytest.raises(DBAPIError) as error, db_session.begin_nested():
        db_session.execute(
            insert(DispatchOutboxRow).values(
                id=uuid4(),
                task_batch_id=batch.id if has_batch else None,
                aggregation_execution_id=aggregation.id if has_aggregation else None,
                dataset_snapshot_id=snapshot.id if has_snapshot else None,
                queue_name="cpu",
                payload={},
                available_at=datetime.now(UTC),
            )
        )

    assert getattr(error.value.orig, "sqlstate", None) == "23514"
    assert (
        getattr(getattr(error.value.orig, "diag", None), "constraint_name", None)
        == "ck_dispatch_outbox_exactly_one_target"
    )


def test_snapshot_dispatch_requires_pending_target_and_cpu_queue(
    db_session: Session,
) -> None:
    projects, snapshot = _pending_snapshot_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)

    with pytest.raises(InvalidResourceStateError, match="must use the cpu queue"):
        repository.ensure_dispatch(
            _snapshot_dispatch_command(snapshot, available_at=now, queue_name="default")
        )

    assert projects.claim_snapshot_import(snapshot.id) is not None
    with pytest.raises(InvalidResourceStateError, match="is not dispatchable"):
        repository.ensure_dispatch(_snapshot_dispatch_command(snapshot, available_at=now))

    unknown_snapshot_id = uuid4()
    with pytest.raises(ResourceNotFoundError, match="does not exist"):
        repository.ensure_dispatch(
            SnapshotDispatchCreate(
                dataset_snapshot_id=unknown_snapshot_id,
                queue_name="cpu",
                payload=SnapshotImportTaskMessage(dataset_snapshot_id=unknown_snapshot_id),
                available_at=now,
            )
        )


def test_ensure_dispatch_validates_batch_ownership(db_session: Session) -> None:
    _, _, execution, batch = _execution_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)
    unknown_batch_id = uuid4()

    with pytest.raises(ResourceNotFoundError, match="does not exist"):
        repository.ensure_dispatch(
            BatchDispatchCreate(
                task_batch_id=unknown_batch_id,
                queue_name="cpu",
                payload=TaskBatchMessage(
                    method_execution_id=execution.id,
                    task_batch_id=unknown_batch_id,
                ),
                available_at=now,
            )
        )

    with pytest.raises(InvalidResourceStateError, match="must own"):
        repository.ensure_dispatch(_dispatch_command(batch, uuid4(), available_at=now))


def test_claim_and_publish_enforce_lease_ownership(db_session: Session) -> None:
    _, _, execution, batch = _execution_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)
    dispatch = repository.ensure_dispatch(_dispatch_command(batch, execution.id, available_at=now))

    claimed = repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=10,
    )

    assert [item.id for item in claimed] == [dispatch.id]
    assert claimed[0].attempt_count == 1
    assert claimed[0].lease_owner == "relay-1"
    with pytest.raises(InvalidResourceStateError, match="not leased"):
        repository.mark_published(dispatch.id, lease_owner="relay-2", published_at=now)

    published = repository.mark_published(
        dispatch.id,
        lease_owner="relay-1",
        published_at=now,
    )
    assert published.status is DispatchStatus.published
    assert published.published_at == now
    assert published.lease_owner is None
    assert (
        repository.claim_available(
            now=now,
            lease_owner="relay-2",
            lease_until=now + timedelta(seconds=30),
            limit=10,
        )
        == ()
    )


def test_failed_publication_is_released_for_delayed_retry(db_session: Session) -> None:
    _, _, execution, batch = _execution_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)
    dispatch = repository.ensure_dispatch(_dispatch_command(batch, execution.id, available_at=now))
    repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )

    retry_at = now + timedelta(minutes=1)
    released = repository.release_after_failure(
        dispatch.id,
        lease_owner="relay-1",
        available_at=retry_at,
        last_error="broker unavailable",
    )

    assert released.lease_owner is None
    assert released.last_error == "broker unavailable"
    assert (
        repository.claim_available(
            now=retry_at - timedelta(microseconds=1),
            lease_owner="relay-2",
            lease_until=retry_at + timedelta(seconds=30),
            limit=1,
        )
        == ()
    )
    reclaimed = repository.claim_available(
        now=retry_at,
        lease_owner="relay-2",
        lease_until=retry_at + timedelta(seconds=30),
        limit=1,
    )
    assert reclaimed[0].id == dispatch.id
    assert reclaimed[0].attempt_count == 2


def test_expired_lease_can_be_reclaimed_by_another_relay(db_session: Session) -> None:
    _, _, execution, batch = _execution_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)
    dispatch = repository.ensure_dispatch(_dispatch_command(batch, execution.id, available_at=now))
    repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )

    reclaimed = repository.claim_available(
        now=now + timedelta(seconds=30),
        lease_owner="relay-2",
        lease_until=now + timedelta(seconds=60),
        limit=1,
    )

    assert reclaimed[0].id == dispatch.id
    assert reclaimed[0].lease_owner == "relay-2"
    assert reclaimed[0].attempt_count == 2


def test_reconciler_repairs_missing_and_rearms_stale_dispatches(
    db_session: Session,
) -> None:
    _, _, _execution, batch = _execution_context(db_session, scheduled=True)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)

    assert repository.ensure_missing(now=now, limit=10) == 1
    assert repository.ensure_missing(now=now, limit=10) == 0
    dispatch = repository.get_dispatch_for_batch(batch.id)
    assert dispatch is not None

    repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )
    repository.mark_published(
        dispatch.id,
        lease_owner="relay-1",
        published_at=now,
    )

    rearm_time = now + timedelta(minutes=10)
    assert (
        repository.rearm_stale_published(
            now=rearm_time,
            published_before=now + timedelta(minutes=5),
            limit=10,
        )
        == 1
    )
    rearmed = repository.get_dispatch(dispatch.id)
    assert rearmed is not None
    assert rearmed.status is DispatchStatus.pending
    assert rearmed.available_at == rearm_time
    assert rearmed.published_at is None
    assert rearmed.attempt_count == 1
    assert rearmed.last_error is not None


def test_reconciler_repairs_and_rearms_aggregation_dispatches(
    db_session: Session,
) -> None:
    aggregation = _aggregation_context(
        db_session,
        status=AggregationExecutionStatus.queued,
    )
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)

    assert repository.ensure_missing(now=now, limit=10) == 1
    assert repository.ensure_missing(now=now, limit=10) == 0
    dispatch = repository.get_dispatch_for_aggregation(aggregation.id)
    assert dispatch is not None

    repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )
    repository.mark_published(
        dispatch.id,
        lease_owner="relay-1",
        published_at=now,
    )

    rearm_time = now + timedelta(minutes=10)
    assert (
        repository.rearm_stale_published(
            now=rearm_time,
            published_before=now + timedelta(minutes=5),
            limit=10,
        )
        == 1
    )
    rearmed = repository.get_dispatch_for_aggregation(aggregation.id)
    assert rearmed is not None
    assert rearmed.status is DispatchStatus.pending
    assert rearmed.available_at == rearm_time
    assert rearmed.published_at is None


def test_reconciler_repairs_and_rearms_pending_snapshot_dispatches(
    db_session: Session,
) -> None:
    _, snapshot = _pending_snapshot_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)

    assert repository.ensure_missing(now=now, limit=10) == 1
    assert repository.ensure_missing(now=now, limit=10) == 0
    dispatch = repository.get_dispatch_for_snapshot(snapshot.id)
    assert dispatch is not None

    repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )
    repository.mark_published(
        dispatch.id,
        lease_owner="relay-1",
        published_at=now,
    )

    rearm_time = now + timedelta(minutes=10)
    assert (
        repository.rearm_stale_published(
            now=rearm_time,
            published_before=now + timedelta(minutes=5),
            limit=10,
        )
        == 1
    )
    rearmed = repository.get_dispatch_for_snapshot(snapshot.id)
    assert rearmed is not None
    assert rearmed.status is DispatchStatus.pending
    assert rearmed.available_at == rearm_time
    assert rearmed.published_at is None


def test_reconciler_does_not_rearm_snapshot_claimed_by_import_worker(
    db_session: Session,
) -> None:
    projects, snapshot = _pending_snapshot_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)
    dispatch = repository.ensure_dispatch(_snapshot_dispatch_command(snapshot, available_at=now))
    repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )
    repository.mark_published(
        dispatch.id,
        lease_owner="relay-1",
        published_at=now,
    )
    assert projects.claim_snapshot_import(snapshot.id) is not None

    assert (
        repository.rearm_stale_published(
            now=now + timedelta(minutes=10),
            published_before=now + timedelta(minutes=5),
            limit=10,
        )
        == 0
    )


def test_reconciler_does_not_rearm_an_aggregation_claimed_by_a_worker(
    db_session: Session,
) -> None:
    aggregation = _aggregation_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)
    dispatch = repository.ensure_dispatch(
        _aggregation_dispatch_command(aggregation, available_at=now)
    )
    repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )
    repository.mark_published(
        dispatch.id,
        lease_owner="relay-1",
        published_at=now,
    )
    aggregation.status = AggregationExecutionStatus.running
    aggregation.started_at = now
    db_session.flush()

    assert (
        repository.rearm_stale_published(
            now=now + timedelta(minutes=10),
            published_before=now + timedelta(minutes=5),
            limit=10,
        )
        == 0
    )


def test_reconciler_does_not_rearm_a_batch_already_claimed_by_a_worker(
    db_session: Session,
) -> None:
    runs, run, execution, batch = _execution_context(db_session, scheduled=True)
    repository = SqlAlchemyDispatchRepository(db_session)
    now = datetime.now(UTC)
    dispatch = repository.ensure_dispatch(_dispatch_command(batch, execution.id, available_at=now))
    repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )
    repository.mark_published(
        dispatch.id,
        lease_owner="relay-1",
        published_at=now,
    )
    runs.mark_run_started(run.id, started_at=now)
    runs.mark_execution_started(execution.id, started_at=now)
    claimed_batch = runs.claim_batch(
        batch.id,
        method_execution_id=execution.id,
        worker_task_id="worker-task-1",
        started_at=now,
        attempt_count=1,
        worker_provenance=seed_worker_provenance(),
    )
    assert claimed_batch is not None

    assert (
        repository.rearm_stale_published(
            now=now + timedelta(minutes=10),
            published_before=now + timedelta(minutes=5),
            limit=10,
        )
        == 0
    )


def test_claim_available_skips_rows_locked_by_another_relay(
    postgres_engine: Engine,
) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as seed_session:
        runs, _, execution, first_batch = _execution_context(seed_session)
        _, second_batch = runs.create_task_batches(
            execution.id, [TaskBatchPlan(batch_index=1, record_offset=1, record_count=1)]
        )
        seed_repository = SqlAlchemyDispatchRepository(seed_session)
        seed_repository.ensure_dispatch(
            _dispatch_command(first_batch, execution.id, available_at=now)
        )
        seed_repository.ensure_dispatch(
            _dispatch_command(second_batch, execution.id, available_at=now)
        )
        seed_session.commit()

    with (
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as first_session,
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as second_session,
    ):
        first_claim = SqlAlchemyDispatchRepository(first_session).claim_available(
            now=now,
            lease_owner="relay-1",
            lease_until=now + timedelta(seconds=30),
            limit=1,
        )
        second_claim = SqlAlchemyDispatchRepository(second_session).claim_available(
            now=now,
            lease_owner="relay-2",
            lease_until=now + timedelta(seconds=30),
            limit=1,
        )

        assert len(first_claim) == 1
        assert len(second_claim) == 1
        assert first_claim[0].id != second_claim[0].id
        first_session.rollback()
        second_session.rollback()


def test_rearm_skips_a_task_batch_locked_by_a_worker(postgres_engine: Engine) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as seed_session:
        _, _, execution, batch = _execution_context(seed_session, scheduled=True)
        seed_repository = SqlAlchemyDispatchRepository(seed_session)
        dispatch = seed_repository.ensure_dispatch(
            _dispatch_command(batch, execution.id, available_at=now)
        )
        seed_repository.claim_available(
            now=now,
            lease_owner="relay-1",
            lease_until=now + timedelta(seconds=30),
            limit=1,
        )
        seed_repository.mark_published(
            dispatch.id,
            lease_owner="relay-1",
            published_at=now,
        )
        seed_session.commit()

    with (
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as worker_session,
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as relay_session,
    ):
        locked_batch = worker_session.scalar(
            select(TaskBatchRow).where(TaskBatchRow.id == batch.id).with_for_update()
        )
        assert locked_batch is not None

        rearmed_count = SqlAlchemyDispatchRepository(relay_session).rearm_stale_published(
            now=now + timedelta(minutes=10),
            published_before=now + timedelta(minutes=5),
            limit=10,
        )

        assert rearmed_count == 0
        worker_session.rollback()
        relay_session.rollback()


def test_rearm_skips_an_aggregation_locked_by_a_worker(postgres_engine: Engine) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as seed_session:
        aggregation = _aggregation_context(seed_session)
        seed_repository = SqlAlchemyDispatchRepository(seed_session)
        dispatch = seed_repository.ensure_dispatch(
            _aggregation_dispatch_command(aggregation, available_at=now)
        )
        seed_repository.claim_available(
            now=now,
            lease_owner="relay-1",
            lease_until=now + timedelta(seconds=30),
            limit=1,
        )
        seed_repository.mark_published(
            dispatch.id,
            lease_owner="relay-1",
            published_at=now,
        )
        seed_session.commit()

    with (
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as worker_session,
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as relay_session,
    ):
        locked_aggregation = worker_session.scalar(
            select(AggregationExecutionRow)
            .where(AggregationExecutionRow.id == aggregation.id)
            .with_for_update()
        )
        assert locked_aggregation is not None

        rearmed_count = SqlAlchemyDispatchRepository(relay_session).rearm_stale_published(
            now=now + timedelta(minutes=10),
            published_before=now + timedelta(minutes=5),
            limit=10,
        )

        assert rearmed_count == 0
        worker_session.rollback()
        relay_session.rollback()


def test_rearm_skips_a_snapshot_locked_by_an_import_worker(postgres_engine: Engine) -> None:
    now = datetime.now(UTC)
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as seed_session:
        _, snapshot = _pending_snapshot_context(seed_session)
        seed_repository = SqlAlchemyDispatchRepository(seed_session)
        dispatch = seed_repository.ensure_dispatch(
            _snapshot_dispatch_command(snapshot, available_at=now)
        )
        seed_repository.claim_available(
            now=now,
            lease_owner="relay-1",
            lease_until=now + timedelta(seconds=30),
            limit=1,
        )
        seed_repository.mark_published(
            dispatch.id,
            lease_owner="relay-1",
            published_at=now,
        )
        seed_session.commit()

    with (
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as worker_session,
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as relay_session,
    ):
        locked_snapshot = worker_session.scalar(
            select(DatasetSnapshotRow).where(DatasetSnapshotRow.id == snapshot.id).with_for_update()
        )
        assert locked_snapshot is not None

        rearmed_count = SqlAlchemyDispatchRepository(relay_session).rearm_stale_published(
            now=now + timedelta(minutes=10),
            published_before=now + timedelta(minutes=5),
            limit=10,
        )

        assert rearmed_count == 0
        worker_session.rollback()
        relay_session.rollback()


@pytest.mark.parametrize(
    "target",
    [DispatchTarget.evaluation_execution, DispatchTarget.export],
)
@pytest.mark.parametrize("worker_claimed", [False, True])
def test_reconciler_repairs_and_only_rearms_unclaimed_evaluation_and_export(
    db_session: Session,
    target: DispatchTarget,
    *,
    worker_claimed: bool,
) -> None:
    now = datetime.now(UTC)
    command = _dispatch_context(db_session, target, available_at=now)
    if target is DispatchTarget.evaluation_execution:
        SqlAlchemyEvaluationRepository(db_session).mark_evaluation_queued(command.target_id)
    else:
        SqlAlchemyExportRepository(db_session).mark_export_queued(command.target_id)
    repository = SqlAlchemyDispatchRepository(db_session)

    assert repository.ensure_missing(now=now, limit=10) == 1
    assert repository.ensure_missing(now=now, limit=10) == 0
    dispatch = repository.ensure_dispatch(command)
    repository.claim_available(
        now=now,
        lease_owner="relay-1",
        lease_until=now + timedelta(seconds=30),
        limit=1,
    )
    published = repository.mark_published(
        dispatch.id,
        lease_owner="relay-1",
        published_at=now,
    )
    rearm_time = now + timedelta(minutes=10)
    if worker_claimed:
        if target is DispatchTarget.evaluation_execution:
            assert (
                SqlAlchemyEvaluationRepository(db_session).claim_evaluation(
                    command.target_id, started_at=rearm_time
                )
                is not None
            )
        else:
            assert (
                SqlAlchemyExportRepository(db_session).claim_export(
                    command.target_id, started_at=rearm_time
                )
                is not None
            )
        with pytest.raises(InvalidResourceStateError, match="is not dispatchable"):
            repository.ensure_dispatch(command)

    assert repository.rearm_stale_published(
        now=rearm_time,
        published_before=now + timedelta(minutes=5),
        limit=10,
    ) == (0 if worker_claimed else 1)
    reconciled = repository.get_dispatch(dispatch.id)
    assert reconciled is not None
    assert reconciled.target is target
    assert reconciled.target_id == command.target_id
    assert reconciled.queue_name == command.queue_name
    assert reconciled.payload == command.payload
    if worker_claimed:
        assert reconciled == published
    else:
        assert reconciled.status is DispatchStatus.pending
        assert reconciled.available_at == rearm_time
        assert reconciled.published_at is None
        assert reconciled.attempt_count == 1
        assert reconciled.last_error is not None


@pytest.mark.parametrize(
    "target",
    [DispatchTarget.evaluation_execution, DispatchTarget.export],
)
@pytest.mark.parametrize("has_published_dispatch", [False, True])
def test_reconciler_skips_evaluation_and_export_targets_locked_by_workers(
    postgres_engine: Engine,
    target: DispatchTarget,
    *,
    has_published_dispatch: bool,
) -> None:
    now = datetime.now(UTC)
    published: Dispatch | None = None
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as seed_session:
        command = _dispatch_context(seed_session, target, available_at=now)
        if has_published_dispatch:
            repository = SqlAlchemyDispatchRepository(seed_session)
            dispatch = repository.ensure_dispatch(command)
            repository.claim_available(
                now=now,
                lease_owner="relay-1",
                lease_until=now + timedelta(seconds=30),
                limit=1,
            )
            published = repository.mark_published(
                dispatch.id,
                lease_owner="relay-1",
                published_at=now,
            )
        seed_session.commit()

    with (
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as worker_session,
        Session(postgres_engine, autoflush=False, expire_on_commit=False) as relay_session,
    ):
        if target is DispatchTarget.evaluation_execution:
            assert (
                worker_session.scalar(
                    select(EvaluationExecutionRow)
                    .where(EvaluationExecutionRow.id == command.target_id)
                    .with_for_update()
                )
                is not None
            )
        else:
            assert (
                worker_session.scalar(
                    select(ExportExecutionRow)
                    .where(ExportExecutionRow.id == command.target_id)
                    .with_for_update()
                )
                is not None
            )
        relay = SqlAlchemyDispatchRepository(relay_session)
        rearm_time = now + timedelta(minutes=10)

        if published is None:
            assert relay.ensure_missing(now=rearm_time, limit=10) == 0
            assert tuple(relay_session.scalars(select(DispatchOutboxRow.id))) == ()
        else:
            assert (
                relay.rearm_stale_published(
                    now=rearm_time,
                    published_before=now + timedelta(minutes=5),
                    limit=10,
                )
                == 0
            )
            assert relay.get_dispatch(published.id) == published
        worker_session.rollback()
        relay_session.rollback()


def test_reconciler_repairs_and_rearms_expired_public_jobs_without_losing_llm_queue(
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    job = _classification_context(db_session, created_at=now)
    jobs = SqlAlchemyPublicClassificationRepository(db_session)
    dispatches = SqlAlchemyDispatchRepository(db_session)
    first_lease_id = uuid4()
    first_expiry = now + timedelta(minutes=1)
    first_claim = jobs.claim_job(
        job.id,
        now=now,
        lease_id=first_lease_id,
        lease_until=first_expiry,
    )
    assert first_claim is not None
    assert dispatches.ensure_missing(now=now, limit=10) == 0
    assert dispatches.ensure_missing(now=first_expiry - timedelta(microseconds=1), limit=10) == 0

    assert dispatches.ensure_missing(now=first_expiry, limit=10) == 1
    assert dispatches.ensure_missing(now=first_expiry, limit=10) == 0
    dispatch = dispatches.get_dispatch_for_classification(job.id)
    assert dispatch is not None
    assert dispatch.queue_name == "llm"
    assert dispatch.payload == PublicClassificationTaskMessage(classification_job_id=job.id)
    assert jobs.get_job(job.id) == first_claim
    dispatches.claim_available(
        now=first_expiry,
        lease_owner="relay-1",
        lease_until=first_expiry + timedelta(seconds=30),
        limit=1,
    )
    published = dispatches.mark_published(
        dispatch.id,
        lease_owner="relay-1",
        published_at=first_expiry,
    )
    second_lease_id = uuid4()
    second_expiry = first_expiry + timedelta(minutes=1)
    second_claim = jobs.claim_job(
        job.id,
        now=first_expiry,
        lease_id=second_lease_id,
        lease_until=second_expiry,
    )
    assert second_claim is not None

    assert (
        dispatches.rearm_stale_published(
            now=second_expiry - timedelta(microseconds=1),
            published_before=first_expiry,
            limit=10,
        )
        == 0
    )
    assert dispatches.get_dispatch(dispatch.id) == published
    assert (
        dispatches.rearm_stale_published(
            now=second_expiry,
            published_before=first_expiry,
            limit=10,
        )
        == 1
    )
    rearmed = dispatches.get_dispatch_for_classification(job.id)
    assert rearmed is not None
    assert rearmed.id == dispatch.id
    assert rearmed.status is DispatchStatus.pending
    assert rearmed.queue_name == "llm"
    assert rearmed.payload == dispatch.payload
    assert rearmed.available_at == second_expiry
    assert rearmed.published_at is None
    assert rearmed.attempt_count == 1
    assert jobs.get_job(job.id) == second_claim
    assert (
        jobs.claim_job(
            job.id,
            now=second_expiry,
            lease_id=uuid4(),
            lease_until=second_expiry + timedelta(minutes=1),
        )
        is not None
    )
    assert not jobs.fail_job(job.id, lease_id=first_lease_id, completed_at=second_expiry)
    assert not jobs.fail_job(job.id, lease_id=second_lease_id, completed_at=second_expiry)
    current = jobs.get_job(job.id)
    assert current is not None
    assert current.status is PublicClassificationStatus.running
    assert current.queue_name == "llm"
