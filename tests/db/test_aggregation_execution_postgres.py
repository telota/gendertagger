from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from tests.factories import tei_person_input

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.aggregation_repository import SqlAlchemyAggregationRepository
from gendertagger.db.aggregations import (
    AggregatedResultRow,
    AggregationExecutionRow,
    AggregationMethodExecutionRow,
)
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.dispatch_repository import SqlAlchemyDispatchRepository
from gendertagger.db.dispatches import BatchDispatchRow
from gendertagger.db.executions import MethodExecutionRow, RunRow
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.domain.aggregation_assessment import assess_reference_predictions
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.aggregation import (
    AggregationCreateRequest,
    AggregationExecutionCreate,
    AggregationResultWrite,
)
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    MethodExecutionStatus,
    TaskBatchStatus,
)
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import ImportedPerson
from gendertagger.models.project import (
    DatasetSnapshotCreate,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotSourceMemberCreate,
    TeiImportProfile,
)
from gendertagger.models.run import (
    MethodExecutionCreate,
    PredictionWrite,
    RunCreate,
    TaskBatchCreate,
)
from gendertagger.services.aggregations import AggregationCreation, AggregationService
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.unit_of_work import UnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _mutate_and_flush(session: Session, mutation: Callable[[], object]) -> None:
    mutation()
    session.flush()


def _force_deferred_constraints(
    session: Session,
    mutation: Callable[[], object] | None,
) -> None:
    if mutation is not None:
        _mutate_and_flush(session, mutation)
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


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


def _assert_deferred_constraints_reject(
    session: Session,
    *,
    message: str,
    mutation: Callable[[], object] | None = None,
) -> None:
    with pytest.raises(DBAPIError, match=message) as error, session.begin_nested():
        _force_deferred_constraints(session, mutation)
    assert getattr(error.value.orig, "sqlstate", None) == "23514"
    session.expire_all()


def _seed_reference_run(
    session: Session,
) -> tuple[UUID, tuple[UUID, ...], UUID]:
    projects = SqlAlchemyProjectRepository(session)
    project = projects.add_project(
        ProjectCreate(
            slug=f"aggregation-core-{uuid4().hex}",
            display_name="Aggregation core fixture",
        )
    )
    artifacts = SqlAlchemyArtifactRepository(session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri=f"local-sha256:{'a' * 64}",
            sha256="a" * 64,
            byte_size=1,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    import_config = SnapshotImportConfig(
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
    projects.begin_snapshot_import(snapshot.id)
    projects.add_imported_person_records(
        snapshot.id,
        [
            ImportedPerson(
                person=tei_person_input(tei_id="p1", surname="Example"),
                source_member_name="source.xml",
                source_record_locator="1",
            )
        ],
    )
    projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
    person = projects.get_person_record_by_tei_id(snapshot.id, "p1")
    assert person is not None

    runs = SqlAlchemyRunRepository(session)
    run = runs.add_run(
        RunCreate(
            dataset_snapshot_id=snapshot.id,
            resolved_config=RunConfig(
                methods=[
                    MethodRunConfig(name=method_name) for method_name in REFERENCE_REQUIRED_METHODS
                ]
            ),
            code_git_commit="c" * 40,
            application_version="0.0.0",
            python_version="3.13.14",
            dependency_lock_sha256="d" * 64,
        )
    )
    runs.mark_run_queued(run.id)
    runs.mark_run_started(run.id, started_at=NOW)
    execution_ids: list[UUID] = []
    for method_name in REFERENCE_REQUIRED_METHODS:
        execution = runs.add_method_execution(
            MethodExecutionCreate(
                run_id=run.id,
                descriptor=MethodDescriptor(
                    name=method_name,
                    implementation_version="test_v1",
                    normalization_version="test_v1",
                ),
                queue_name="cpu",
                total_count=1,
            )
        )
        execution_ids.append(execution.id)
        batch = runs.add_task_batch(
            TaskBatchCreate(
                method_execution_id=execution.id,
                batch_index=0,
                queue_name="cpu",
                record_offset=0,
                record_count=1,
            )
        )
        runs.mark_execution_queued(execution.id)
        runs.mark_execution_started(execution.id, started_at=NOW)
        claimed = runs.claim_batch(
            batch.id,
            method_execution_id=execution.id,
            worker_task_id=f"fixture-{method_name}",
            started_at=NOW,
            attempt_count=1,
        )
        assert claimed is not None
        result = PredictionResult(
            label=(CanonicalLabel.female if method_name == "gender_guesser" else None),
            status=(
                PredictionStatus.success
                if method_name == "gender_guesser"
                else PredictionStatus.error
                if method_name == "gnd"
                else PredictionStatus.abstain
            ),
        )
        runs.add_predictions(
            execution.id,
            [
                PredictionWrite(
                    person_record_id=person.id,
                    task_batch_id=batch.id,
                    input_fingerprint="e" * 64,
                    result=result,
                )
            ],
        )
        runs.mark_batch_finished(
            batch.id,
            status=TaskBatchStatus.completed,
            finished_at=NOW,
            success_count=int(result.status is PredictionStatus.success),
            abstain_count=int(result.status is PredictionStatus.abstain),
            error_count=int(result.status is PredictionStatus.error),
        )
        runs.finalize_execution_if_complete(execution.id, finished_at=NOW)
    runs.finalize_run_if_complete(run.id, finished_at=NOW)
    return run.id, tuple(execution_ids), person.id


def test_reference_selection_requires_every_stable_method_once(db_session: Session) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)

    with pytest.raises(
        InvalidResourceStateError,
        match="invalid reference_v1 method selection: missing required methods: local_llm",
    ):
        repository.add_aggregation(
            AggregationExecutionCreate(
                run_id=run_id,
                method_execution_ids=execution_ids[:-1],
            )
        )


def test_repository_claims_and_completes_exactly_one_full_snapshot_result(
    db_session: Session,
) -> None:
    run_id, execution_ids, person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )

    queued = repository.mark_aggregation_queued(aggregation.id)
    claimed = repository.claim_aggregation(aggregation.id, started_at=NOW)
    assert queued.status is AggregationExecutionStatus.queued
    assert claimed is not None
    assert claimed.status is AggregationExecutionStatus.running
    assert repository.claim_aggregation(aggregation.id, started_at=NOW) is None

    matrix = repository.load_prediction_matrix(aggregation.id)
    assert len(matrix) == 1
    assert matrix[0].person_record_id == person_id
    assert set(matrix[0].predictions) == set(REFERENCE_REQUIRED_METHODS)
    assert matrix[0].predictions["gnd"].status is PredictionStatus.error
    assert matrix[0].predictions["parenthetical_qualifier"].status is PredictionStatus.abstain

    repository.add_results(
        aggregation.id,
        [
            AggregationResultWrite(
                person_record_id=person_id,
                result=assess_reference_predictions(matrix[0].predictions),
                metadata={"strategy": "reference_v1"},
            )
        ],
    )
    completed = repository.mark_aggregation_finished(
        aggregation.id,
        status=AggregationExecutionStatus.completed,
        finished_at=NOW,
    )

    assert completed.status is AggregationExecutionStatus.completed
    assert len(repository.list_results(aggregation.id, limit=10)) == 1
    assert repository.claim_aggregation(aggregation.id, started_at=NOW) is None
    with pytest.raises(InvalidResourceStateError, match="cannot add results from status completed"):
        repository.add_results(aggregation.id, [])


def test_database_rejects_reopening_a_selected_execution(
    db_session: Session,
) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.claim_aggregation(aggregation.id, started_at=NOW)
    execution_row = db_session.get(MethodExecutionRow, execution_ids[0])
    assert execution_row is not None

    def reopen_execution() -> None:
        execution_row.status = MethodExecutionStatus.running
        execution_row.finished_at = None

    _assert_database_rejects(
        db_session,
        reopen_execution,
        sqlstate="23514",
        message="illegal method_executions lifecycle transition",
    )


def test_database_rejects_changing_selected_execution_run_ownership(
    db_session: Session,
) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.claim_aggregation(aggregation.id, started_at=NOW)
    original_run = db_session.get(RunRow, run_id)
    assert original_run is not None
    other_run = SqlAlchemyRunRepository(db_session).add_run(
        RunCreate(
            dataset_snapshot_id=original_run.dataset_snapshot_id,
            resolved_config=RunConfig(methods=[]),
            code_git_commit="f" * 40,
            application_version="0.0.0",
            python_version="3.13.14",
            dependency_lock_sha256="a" * 64,
        )
    )
    execution_row = db_session.get(MethodExecutionRow, execution_ids[0])
    assert execution_row is not None
    _assert_database_rejects(
        db_session,
        lambda: setattr(execution_row, "run_id", other_run.id),
        sqlstate="55000",
        message="terminal method_executions rows are immutable",
    )


def test_repository_rejects_completion_with_partial_results(db_session: Session) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.claim_aggregation(aggregation.id, started_at=NOW)

    with pytest.raises(
        InvalidResourceStateError,
        match="aggregation results must exactly cover the run snapshot: expected 1 people, received 0",
    ):
        repository.add_results(aggregation.id, [])

    with pytest.raises(
        InvalidResourceStateError,
        match="requires exactly one result per snapshot person: expected 1, found 0",
    ):
        repository.mark_aggregation_finished(
            aggregation.id,
            status=AggregationExecutionStatus.completed,
            finished_at=NOW,
        )


def test_database_rejects_aggregation_provenance_mutation(db_session: Session) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    aggregation = SqlAlchemyAggregationRepository(db_session).add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    row = db_session.get(AggregationExecutionRow, aggregation.id)
    assert row is not None
    _assert_database_rejects(
        db_session,
        lambda: setattr(row, "strategy", "rewritten_v2"),
        sqlstate="55000",
        message="aggregation_executions provenance is immutable",
    )


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("resolved_config", {"minimum_methods": 2}),
        ("config_sha256", "e" * 64),
    ],
)
def test_database_rejects_aggregation_configuration_provenance_mutation(
    db_session: Session,
    attribute: str,
    value: object,
) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    aggregation = SqlAlchemyAggregationRepository(db_session).add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    row = db_session.get(AggregationExecutionRow, aggregation.id)
    assert row is not None

    _assert_database_rejects(
        db_session,
        lambda: setattr(row, attribute, value),
        sqlstate="55000",
        message="aggregation_executions provenance is immutable",
    )


def test_database_rejects_aggregation_membership_deletion(db_session: Session) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.mark_aggregation_queued(aggregation.id)
    membership = db_session.get(
        AggregationMethodExecutionRow,
        (aggregation.id, execution_ids[0]),
    )
    assert membership is not None
    _assert_database_rejects(
        db_session,
        lambda: db_session.delete(membership),
        sqlstate="55000",
        message="aggregation method-execution membership is immutable",
    )


def test_database_rejects_queuing_aggregation_without_membership(
    db_session: Session,
) -> None:
    run_id, _execution_ids, _person_id = _seed_reference_run(db_session)
    row = AggregationExecutionRow(
        run_id=run_id,
        strategy="reference_v1",
        resolved_config={},
        config_sha256="d" * 64,
        status=AggregationExecutionStatus.pending,
    )
    db_session.add(row)
    db_session.flush()

    _assert_database_rejects(
        db_session,
        lambda: setattr(row, "status", AggregationExecutionStatus.queued),
        sqlstate="23514",
        message="queued aggregation requires nonempty contiguous membership",
    )


def test_deferred_guard_rejects_results_without_aggregation_completion(
    db_session: Session,
) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.claim_aggregation(aggregation.id, started_at=NOW)
    (person_predictions,) = repository.load_prediction_matrix(aggregation.id)
    repository.add_results(
        aggregation.id,
        [
            AggregationResultWrite(
                person_record_id=person_predictions.person_record_id,
                result=assess_reference_predictions(person_predictions.predictions),
            )
        ],
    )

    _assert_deferred_constraints_reject(
        db_session,
        message="committed results require a completed aggregation",
    )


def test_deferred_guard_rejects_completed_aggregation_without_results(
    db_session: Session,
) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.claim_aggregation(aggregation.id, started_at=NOW)
    row = db_session.get(AggregationExecutionRow, aggregation.id)
    assert row is not None

    def complete_without_results() -> None:
        row.status = AggregationExecutionStatus.completed
        row.finished_at = NOW

    _assert_deferred_constraints_reject(
        db_session,
        message="completed aggregation requires one result per snapshot person",
        mutation=complete_without_results,
    )


def test_database_rejects_raw_result_insert_after_aggregation_finished(
    db_session: Session,
) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.claim_aggregation(aggregation.id, started_at=NOW)
    (person_predictions,) = repository.load_prediction_matrix(aggregation.id)
    result = assess_reference_predictions(person_predictions.predictions)
    repository.mark_aggregation_finished(
        aggregation.id,
        status=AggregationExecutionStatus.failed,
        finished_at=NOW,
        failure_class="PermanentAggregationError",
        failure_diagnostic="synthetic failure",
    )
    row = AggregatedResultRow(
        aggregation_execution_id=aggregation.id,
        person_record_id=person_predictions.person_record_id,
        outcome=result.outcome,
        label=result.label,
        male_vote_count=result.pooled_vote_counts.male,
        female_vote_count=result.pooled_vote_counts.female,
        unknown_vote_count=result.pooled_vote_counts.unknown,
        institution_vote_count=result.pooled_vote_counts.institution,
        tied_labels=[label.value for label in result.tied_labels],
        override_source=result.override_source,
        override_agreeing_count=result.override_agreeing_count,
        override_comparison_count=result.override_comparison_count,
        agreement_score=result.agreement_score,
        agreement_tier=result.agreement_tier,
        certainty_tier=result.certainty_tier,
        result_metadata={},
    )

    _assert_database_rejects(
        db_session,
        lambda: db_session.add(row),
        sqlstate="23514",
        message="aggregation result writes require a running aggregation",
    )


def test_repository_does_not_reopen_a_failed_aggregation(db_session: Session) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.claim_aggregation(aggregation.id, started_at=NOW)

    failed = repository.mark_aggregation_finished(
        aggregation.id,
        status=AggregationExecutionStatus.failed,
        finished_at=NOW,
        failure_class="PermanentAggregationError",
        failure_diagnostic="required prediction evidence is missing",
    )

    assert failed.status is AggregationExecutionStatus.failed
    assert repository.claim_aggregation(aggregation.id, started_at=NOW) is None
    with pytest.raises(InvalidResourceStateError, match="cannot add results from status failed"):
        repository.add_results(aggregation.id, [])


def test_concurrent_workers_claim_an_aggregation_only_once(postgres_engine: Engine) -> None:
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
        run_id, execution_ids, _person_id = _seed_reference_run(session)
        repository = SqlAlchemyAggregationRepository(session)
        aggregation = repository.add_aggregation(
            AggregationExecutionCreate(
                run_id=run_id,
                method_execution_ids=execution_ids,
            )
        )
        repository.mark_aggregation_queued(aggregation.id)
        session.commit()

    def claim() -> bool:
        with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
            claimed = SqlAlchemyAggregationRepository(session).claim_aggregation(
                aggregation.id,
                started_at=NOW,
            )
            session.commit()
            return claimed is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = [future.result(timeout=10) for future in [pool.submit(claim), pool.submit(claim)]]

    assert claims.count(True) == 1
    assert claims.count(False) == 1


def test_concurrent_identical_aggregation_requests_share_one_aggregation(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
        run_id, execution_ids, _person_id = _seed_reference_run(session)
        session.commit()
    session_factory = create_session_factory(postgres_engine)
    service = AggregationService(
        unit_of_work_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
    )
    command = AggregationExecutionCreate(run_id=run_id, method_execution_ids=execution_ids)

    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as first_session:
        repository = SqlAlchemyAggregationRepository(first_session)
        assert repository.find_reusable_aggregation(command) is None
        first = repository.add_aggregation(command)
        repository.mark_aggregation_queued(first.id)

        with ThreadPoolExecutor(max_workers=1) as pool:
            competing = pool.submit(
                service.create_aggregation,
                run_id=run_id,
                command=AggregationCreateRequest(method_execution_ids=execution_ids),
            )
            observed_lock_wait = False
            deadline = monotonic() + 5
            try:
                while monotonic() < deadline and not competing.done():
                    with postgres_engine.connect() as observer:
                        waiting_locks = observer.execute(
                            text("SELECT count(*) FROM pg_locks WHERE NOT granted")
                        ).scalar_one()
                    if waiting_locks:
                        observed_lock_wait = True
                        break
                    sleep(0.01)
            finally:
                first_session.commit()
            second: AggregationCreation = competing.result(timeout=5)

    assert observed_lock_wait
    assert second.created is False
    assert second.aggregation.id == first.id
    with Session(postgres_engine) as session:
        assert tuple(
            session.scalars(
                select(AggregationExecutionRow.id).where(AggregationExecutionRow.run_id == run_id)
            )
        ) == (first.id,)


def test_aggregation_creation_rolls_back_when_dispatch_intent_cannot_persist(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
        run_id, execution_ids, _person_id = _seed_reference_run(session)
        session.commit()

    def reject_dispatch(*_args: object, **_kwargs: object) -> object:
        msg = "dispatch persistence failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(SqlAlchemyDispatchRepository, "ensure_dispatch", reject_dispatch)
    session_factory = create_session_factory(postgres_engine)

    def unit_of_work_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    service = AggregationService(
        unit_of_work_factory=unit_of_work_factory,
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="dispatch persistence failed"):
        service.create_aggregation(
            run_id=run_id,
            command=AggregationCreateRequest(method_execution_ids=execution_ids),
        )

    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
        assert (
            tuple(
                session.scalars(
                    select(AggregationExecutionRow.id).where(
                        AggregationExecutionRow.run_id == run_id
                    )
                )
            )
            == ()
        )
        assert (
            tuple(
                session.scalars(
                    select(BatchDispatchRow.id).where(
                        BatchDispatchRow.aggregation_execution_id.is_not(None)
                    )
                )
            )
            == ()
        )


def test_repository_rejects_absent_runs_and_unowned_method_selections(
    db_session: Session,
) -> None:
    repository = SqlAlchemyAggregationRepository(db_session)

    with pytest.raises(ResourceNotFoundError, match="does not exist"):
        repository.add_aggregation(
            AggregationExecutionCreate(run_id=uuid4(), method_execution_ids=(uuid4(),))
        )

    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    with pytest.raises(InvalidResourceStateError, match="must belong to the aggregation run"):
        repository.add_aggregation(
            AggregationExecutionCreate(
                run_id=run_id,
                method_execution_ids=(*execution_ids[:-1], uuid4()),
            )
        )


def test_repository_distinguishes_missing_aggregations_from_illegal_transitions(
    db_session: Session,
) -> None:
    repository = SqlAlchemyAggregationRepository(db_session)
    missing_aggregation_id = uuid4()

    assert repository.get_aggregation(missing_aggregation_id) is None
    with pytest.raises(ResourceNotFoundError, match="does not exist"):
        repository.mark_aggregation_queued(missing_aggregation_id)
    with pytest.raises(ResourceNotFoundError, match="does not exist"):
        repository.claim_aggregation(missing_aggregation_id, started_at=NOW)

    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.mark_aggregation_queued(aggregation.id)

    with pytest.raises(InvalidResourceStateError, match="cannot queued from status queued"):
        repository.mark_aggregation_queued(aggregation.id)


def test_repository_rejects_duplicate_results_and_invalid_finish_commands(
    db_session: Session,
) -> None:
    run_id, execution_ids, person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    claimed = repository.claim_aggregation(aggregation.id, started_at=NOW)
    assert claimed is not None
    (person_predictions,) = repository.load_prediction_matrix(aggregation.id)
    result_write = AggregationResultWrite(
        person_record_id=person_id,
        result=assess_reference_predictions(person_predictions.predictions),
    )

    assert repository.get_result(uuid4()) is None
    with pytest.raises(ResourceNotFoundError, match="does not exist"):
        repository.add_results(uuid4(), [])
    with pytest.raises(ValueError, match="at most once"):
        repository.add_results(aggregation.id, [result_write, result_write])
    with pytest.raises(ValueError, match="not a supported terminal aggregation status"):
        repository.mark_aggregation_finished(
            aggregation.id,
            status=AggregationExecutionStatus.running,
            finished_at=NOW,
        )
    with pytest.raises(ValueError, match="requires a failure diagnostic"):
        repository.mark_aggregation_finished(
            aggregation.id,
            status=AggregationExecutionStatus.failed,
            finished_at=NOW,
        )
    with pytest.raises(ValueError, match="limit must be positive"):
        repository.list_results(aggregation.id, limit=0)
    with pytest.raises(ValueError, match="cursor fields must be supplied together"):
        repository.list_results(
            aggregation.id,
            limit=1,
            after_person_record_id=person_id,
        )

    assert repository.add_results(aggregation.id, [result_write]) == 1
    with pytest.raises(InvalidResourceStateError, match="must not retain partial results"):
        repository.mark_aggregation_finished(
            aggregation.id,
            status=AggregationExecutionStatus.failed,
            finished_at=NOW,
            failure_class="PermanentAggregationError",
            failure_diagnostic="synthetic failure",
        )
