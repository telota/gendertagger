from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.aggregations import AggregationExecutionRow
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.dispatch_repository import SqlAlchemyDispatchRepository
from gendertagger.db.executions import TaskBatchRow
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.dispatch import (
    AggregationDispatchCreate,
    BatchDispatchCreate,
    BatchDispatchStatus,
)
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.models.project import DatasetSnapshotCreate, ProjectCreate
from gendertagger.models.run import (
    MethodExecution,
    MethodExecutionCreate,
    Run,
    RunCreate,
    TaskBatch,
    TaskBatchCreate,
    TaskBatchMessage,
)
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _execution_context(
    session: Session,
    *,
    scheduled: bool = False,
) -> tuple[SqlAlchemyRunRepository, Run, MethodExecution, TaskBatch]:
    now = datetime.now(UTC)
    artifacts = SqlAlchemyArtifactRepository(session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri=f"file:///synthetic/dispatch-{uuid4().hex}.xml",
            sha256=uuid4().hex * 2,
            byte_size=1,
            media_type="application/xml",
        )
    )
    projects = SqlAlchemyProjectRepository(session)
    project = projects.add_project(
        ProjectCreate(
            slug=f"dispatch-{uuid4().hex}",
            display_name="Dispatch repository project",
        )
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source.id,
            source_sha256=source.sha256,
            parser_version="tei_parser_v1",
        )
    )
    projects.begin_snapshot_import(snapshot.id)
    projects.add_person_records(
        snapshot.id,
        [PersonInput(tei_id="p1"), PersonInput(tei_id="p2")],
    )
    projects.complete_snapshot_import(snapshot.id, ready_at=now)

    runs = SqlAlchemyRunRepository(session)
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
            total_count=2,
        )
    )
    batch = runs.add_task_batch(
        TaskBatchCreate(
            method_execution_id=execution.id,
            batch_index=0,
            queue_name="cpu",
            record_offset=0,
            record_count=1,
        )
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
    _, run, _, _ = _execution_context(session)
    row = AggregationExecutionRow(
        run_id=run.id,
        strategy="reference_v1",
        resolved_config={},
        config_sha256="a" * 64,
        status=status,
    )
    session.add(row)
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


def test_ensure_dispatch_is_idempotent_per_task_batch(db_session: Session) -> None:
    _, _, execution, batch = _execution_context(db_session)
    repository = SqlAlchemyDispatchRepository(db_session)
    command = _dispatch_command(batch, execution.id, available_at=datetime.now(UTC))

    first = repository.ensure_dispatch(command)
    second = repository.ensure_dispatch(command)

    assert first.id == second.id
    assert first.payload == command.payload
    assert first.status is BatchDispatchStatus.pending
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
    assert published.status is BatchDispatchStatus.published
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
    assert rearmed.status is BatchDispatchStatus.pending
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
    assert rearmed.status is BatchDispatchStatus.pending
    assert rearmed.available_at == rearm_time
    assert rearmed.published_at is None


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
        second_batch = runs.add_task_batch(
            TaskBatchCreate(
                method_execution_id=execution.id,
                batch_index=1,
                queue_name="cpu",
                record_offset=1,
                record_count=1,
            )
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
