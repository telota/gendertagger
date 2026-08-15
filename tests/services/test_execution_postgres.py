from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial
from queue import Queue
from threading import Barrier
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, func, select, text
from sqlalchemy.orm import Session

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.dispatch_repository import SqlAlchemyDispatchRepository
from gendertagger.db.executions import PredictionRow
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.dispatch import (
    BatchDispatch,
    BatchDispatchCreate,
    BatchDispatchStatus,
    DispatchMessage,
)
from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus, TaskBatchStatus
from gendertagger.models.person import ImportedPerson, PersonInput
from gendertagger.models.project import (
    DatasetSnapshotCreate,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotSourceMemberCreate,
)
from gendertagger.models.run import Run, RunCreate, TaskBatch, TaskBatchMessage
from gendertagger.services.dispatch import OutboxRelay
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
    PersonInput(tei_id="p02", surname="Müller"),
    PersonInput(tei_id="p03", surname="Schmidt (Sohn des Karl)"),
    PersonInput(tei_id="p04", surname="Weber (Kind des Johann)"),
]


class _FailOncePublisher:
    def __init__(self) -> None:
        self.call_count = 0

    def publish(
        self,
        message: DispatchMessage,
        *,
        queue_name: str,
        task_id: UUID,
    ) -> None:
        del message, queue_name, task_id
        self.call_count += 1
        if self.call_count == 1:
            raise ConnectionError("simulated broker outage")


def _seed_created_run(factory: UnitOfWorkFactory) -> UUID:
    with factory() as unit_of_work:
        project = unit_of_work.projects.add_project(
            ProjectCreate(slug=f"exec-{uuid4().hex}", display_name="Execution project")
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
        import_config = SnapshotImportConfig(limits=SnapshotImportLimits())
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
                    person=person,
                    source_member_name="source.xml",
                    source_record_locator=str(idx),
                )
                for idx, person in enumerate(PEOPLE, start=1)
            ],
        )
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


def _seed_gnd_lookup_run(
    factory: UnitOfWorkFactory,
    *,
    register_lookup: bool = True,
) -> tuple[UUID, UUID | None]:
    with factory() as unit_of_work:
        project = unit_of_work.projects.add_project(
            ProjectCreate(slug=f"gnd-exec-{uuid4().hex}", display_name="GND execution")
        )
        source = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="source_tei",
                storage_uri="file:///synthetic/gnd-source.xml",
                sha256="d" * 64,
                byte_size=1,
                media_type="application/xml",
                project_id=project.id,
            )
        )
        lookup_sha256 = "c" * 64
        lookup = (
            unit_of_work.artifacts.add_artifact(
                ArtifactCreate(
                    logical_type="gnd_lookup_snapshot",
                    storage_uri=f"local-sha256:{lookup_sha256}",
                    sha256=lookup_sha256,
                    byte_size=1,
                    media_type="application/vnd.sqlite3",
                    project_id=project.id,
                )
            )
            if register_lookup
            else None
        )
        import_config = SnapshotImportConfig(limits=SnapshotImportLimits())
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
                    person=PersonInput(tei_id="p-gnd", gnd_id="123"),
                    source_member_name="source.xml",
                    source_record_locator="1",
                )
            ],
        )
        unit_of_work.projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
        run = unit_of_work.runs.add_run(
            RunCreate(
                dataset_snapshot_id=snapshot.id,
                resolved_config=RunConfig(
                    methods=[
                        MethodRunConfig(
                            name="gnd",
                            config={"lookup_sha256": lookup_sha256},
                        )
                    ]
                ),
                code_git_commit="abc123",
                application_version="0.0.0",
                python_version="3.11.0",
                dependency_lock_sha256="b" * 64,
            )
        )
        unit_of_work.commit()
        return run.id, None if lookup is None else lookup.id


def test_scheduler_seals_resolved_lookup_artifact_on_method_execution(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    run_id, lookup_artifact_id = _seed_gnd_lookup_run(factory)
    assert lookup_artifact_id is not None

    (scheduled,) = RunScheduler(
        unit_of_work_factory=factory,
        method_registry=default_method_registry(),
        clock=lambda: NOW,
    ).schedule_run(run_id)

    with factory() as unit_of_work:
        execution = unit_of_work.runs.get_method_execution(scheduled.method_execution_id)
        assert execution is not None
        assert execution.data_artifact_id == lookup_artifact_id


def test_scheduler_rejects_an_unregistered_lookup_digest(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    run_id, _ = _seed_gnd_lookup_run(factory, register_lookup=False)

    with pytest.raises(InvalidResourceStateError, match="is not registered"):
        RunScheduler(
            unit_of_work_factory=factory,
            method_registry=default_method_registry(),
            clock=lambda: NOW,
        ).schedule_run(run_id)


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


def test_batch_claim_rejects_a_mismatched_execution_envelope(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    registry = default_method_registry()
    first_run_id = _seed_created_run(factory)
    second_run_id = _seed_created_run(factory)
    scheduler = RunScheduler(
        unit_of_work_factory=factory,
        method_registry=registry,
        clock=lambda: NOW,
    )
    (first_batch,) = scheduler.schedule_run(first_run_id)
    (second_batch,) = scheduler.schedule_run(second_run_id)
    mismatched = TaskBatchMessage(
        method_execution_id=second_batch.method_execution_id,
        task_batch_id=first_batch.task_batch_id,
    )

    with pytest.raises(InvalidResourceStateError, match="does not belong"):
        BatchExecutor(
            unit_of_work_factory=factory,
            method_registry=registry,
            clock=lambda: LATER,
        ).execute(mismatched, worker_task_id="wrong-owner", attempt_count=1)

    with factory() as unit_of_work:
        persisted = unit_of_work.runs.get_task_batch(first_batch.task_batch_id)
    assert persisted is not None
    assert persisted.status is TaskBatchStatus.pending


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


def test_scheduling_rolls_back_work_when_dispatch_intent_cannot_be_persisted(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, _ = postgres_unit_of_work
    run_id = _seed_created_run(factory)

    def fail_dispatch_persistence(
        _repository: SqlAlchemyDispatchRepository,
        _command: BatchDispatchCreate,
    ) -> BatchDispatch:
        raise RuntimeError("simulated outbox write failure")

    monkeypatch.setattr(
        SqlAlchemyDispatchRepository,
        "ensure_dispatch",
        fail_dispatch_persistence,
    )
    scheduler = RunScheduler(
        unit_of_work_factory=factory,
        method_registry=default_method_registry(),
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="outbox write failure"):
        scheduler.schedule_run(run_id)

    with factory() as unit_of_work:
        run = unit_of_work.runs.get_run(run_id)
        executions = unit_of_work.runs.list_method_executions(run_id)
    assert run is not None
    assert run.status is RunStatus.created
    assert executions == []


def test_broker_failure_keeps_dispatch_recoverable_for_a_later_relay_cycle(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
) -> None:
    factory, _ = postgres_unit_of_work
    run_id = _seed_created_run(factory)
    scheduler = RunScheduler(
        unit_of_work_factory=factory,
        method_registry=default_method_registry(),
        clock=lambda: NOW,
    )
    (scheduled,) = scheduler.schedule_run(run_id)
    publisher = _FailOncePublisher()
    relay = OutboxRelay(
        unit_of_work_factory=factory,
        publisher=publisher,
        relay_id="recovery-test-relay",
        clock=lambda: NOW,
        retry_delay=lambda _attempt: timedelta(0),
    )

    failed_cycle = relay.run_once()
    with factory() as unit_of_work:
        pending = unit_of_work.dispatches.get_dispatch_for_batch(scheduled.task_batch_id)
        run_after_failure = unit_of_work.runs.get_run(run_id)

    assert failed_cycle.failed == 1
    assert pending is not None
    assert pending.status is BatchDispatchStatus.pending
    assert pending.attempt_count == 1
    assert pending.last_error == "ConnectionError: simulated broker outage"
    assert run_after_failure is not None
    assert run_after_failure.status is RunStatus.running

    recovered_cycle = relay.run_once()
    with factory() as unit_of_work:
        published = unit_of_work.dispatches.get_dispatch_for_batch(scheduled.task_batch_id)

    assert recovered_cycle.published == 1
    assert publisher.call_count == 2
    assert published is not None
    assert published.status is BatchDispatchStatus.published
    assert published.attempt_count == 2


def test_concurrent_schedulers_atomically_claim_one_created_run(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    run_id = _seed_created_run(factory)
    both_read_created = Barrier(2)
    original_get_run = SqlAlchemyRunRepository.get_run

    def synchronized_get_run(
        repository: SqlAlchemyRunRepository,
        requested_run_id: UUID,
    ) -> Run | None:
        run = original_get_run(repository, requested_run_id)
        if requested_run_id == run_id:
            both_read_created.wait(timeout=10)
        return run

    monkeypatch.setattr(SqlAlchemyRunRepository, "get_run", synchronized_get_run)
    scheduler = RunScheduler(
        unit_of_work_factory=factory,
        method_registry=default_method_registry(),
        clock=lambda: NOW,
    )

    successful_schedules = 0
    scheduling_conflicts = 0
    scheduled_batch_ids: list[UUID] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(scheduler.schedule_run, run_id) for _ in range(2)]
        for future in futures:
            try:
                scheduled = future.result(timeout=15)
            except InvalidResourceStateError:
                scheduling_conflicts += 1
            else:
                successful_schedules += 1
                assert len(scheduled) == 1
                scheduled_batch_ids.append(scheduled[0].task_batch_id)

    assert successful_schedules == 1
    assert scheduling_conflicts == 1
    assert len(scheduled_batch_ids) == 1
    with factory() as unit_of_work:
        executions = unit_of_work.runs.list_method_executions(run_id)
        dispatch = unit_of_work.dispatches.get_dispatch_for_batch(scheduled_batch_ids[0])
    assert len(executions) == 1
    assert dispatch is not None


def test_concurrent_worker_deliveries_execute_only_one_batch_claim(
    postgres_engine: Engine,
) -> None:
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    run_id = _seed_created_run(factory)
    (scheduled,) = RunScheduler(
        unit_of_work_factory=factory,
        method_registry=default_method_registry(),
        clock=lambda: NOW,
    ).schedule_run(run_id)
    competing_backend_pid: Queue[int] = Queue(maxsize=1)

    def claim_from_competing_session() -> TaskBatch | None:
        with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
            backend_pid = session.scalar(select(func.pg_backend_pid()))
            assert isinstance(backend_pid, int)
            competing_backend_pid.put(backend_pid)
            claimed = SqlAlchemyRunRepository(session).claim_batch(
                scheduled.task_batch_id,
                method_execution_id=scheduled.method_execution_id,
                worker_task_id="worker-2",
                started_at=LATER,
                attempt_count=1,
            )
            session.commit()
            return claimed

    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as first_session:
        first_claim = SqlAlchemyRunRepository(first_session).claim_batch(
            scheduled.task_batch_id,
            method_execution_id=scheduled.method_execution_id,
            worker_task_id="worker-1",
            started_at=NOW,
            attempt_count=1,
        )
        assert first_claim is not None

        with ThreadPoolExecutor(max_workers=1) as pool:
            competing = pool.submit(claim_from_competing_session)
            backend_pid = competing_backend_pid.get(timeout=5)
            observed_lock_wait = False
            deadline = monotonic() + 5
            try:
                while monotonic() < deadline and not competing.done():
                    with postgres_engine.connect() as observer:
                        wait_event_type = observer.execute(
                            text(
                                "SELECT wait_event_type FROM pg_stat_activity "
                                "WHERE pid = :backend_pid"
                            ),
                            {"backend_pid": backend_pid},
                        ).scalar_one_or_none()
                    if wait_event_type == "Lock":
                        observed_lock_wait = True
                        break
                    sleep(0.01)
            finally:
                first_session.commit()
            duplicate_claim = competing.result(timeout=5)

    assert observed_lock_wait
    assert duplicate_claim is None
    with factory() as unit_of_work:
        persisted = unit_of_work.runs.get_task_batch(scheduled.task_batch_id)
    assert persisted is not None
    assert persisted.status is TaskBatchStatus.running
    assert persisted.worker_task_id == "worker-1"
