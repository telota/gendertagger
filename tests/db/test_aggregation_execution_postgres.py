from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.aggregation_repository import SqlAlchemyAggregationRepository
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.executions import MethodExecutionRow, RunRow
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.domain.aggregation_assessment import assess_reference_predictions
from gendertagger.models.aggregation import (
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
)
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.models.project import DatasetSnapshotCreate, ProjectCreate
from gendertagger.models.run import MethodExecutionCreate, PredictionWrite, RunCreate
from gendertagger.services.persistence_errors import InvalidResourceStateError

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def _seed_reference_run(
    session: Session,
    *,
    omitted_prediction_method: str | None = None,
) -> tuple[UUID, tuple[UUID, ...], UUID]:
    artifacts = SqlAlchemyArtifactRepository(session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri=f"local-sha256:{uuid4().hex}",
            sha256=uuid4().hex * 2,
            byte_size=1,
            media_type="application/tei+xml",
        )
    )
    projects = SqlAlchemyProjectRepository(session)
    project = projects.add_project(
        ProjectCreate(
            slug=f"aggregation-core-{uuid4().hex}",
            display_name="Aggregation core fixture",
        )
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
    projects.add_person_records(
        snapshot.id,
        [PersonInput(tei_id="p1", surname="Example")],
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
        if method_name != omitted_prediction_method:
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
                        input_fingerprint="e" * 64,
                        result=result,
                    )
                ],
            )
        execution_row = session.get(MethodExecutionRow, execution.id)
        assert execution_row is not None
        execution_row.status = (
            MethodExecutionStatus.completed_with_errors
            if method_name == "gnd"
            else MethodExecutionStatus.completed
        )
        execution_row.started_at = NOW
        execution_row.finished_at = NOW
        execution_row.completed_count = 0 if method_name == "gnd" else 1
        execution_row.failed_count = 1 if method_name == "gnd" else 0
    session.flush()
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


def test_prediction_matrix_preserves_an_unexplained_missing_cell(
    db_session: Session,
) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(
        db_session,
        omitted_prediction_method="gnd",
    )
    repository = SqlAlchemyAggregationRepository(db_session)
    aggregation = repository.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=execution_ids,
        )
    )
    repository.claim_aggregation(aggregation.id, started_at=NOW)

    matrix = repository.load_prediction_matrix(aggregation.id)

    assert len(matrix) == 1
    assert "gnd" not in matrix[0].predictions
    assert matrix[0].predictions["parenthetical_qualifier"].status is PredictionStatus.abstain


def test_prediction_matrix_revalidates_selected_execution_completion(
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
    execution_row.status = MethodExecutionStatus.running
    execution_row.finished_at = None
    db_session.flush()

    with pytest.raises(
        InvalidResourceStateError,
        match="selected method executions are no longer complete: parenthetical_qualifier",
    ):
        repository.load_prediction_matrix(aggregation.id)


def test_prediction_matrix_revalidates_selected_execution_run_ownership(
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
    execution_row.run_id = other_run.id
    db_session.flush()

    with pytest.raises(
        InvalidResourceStateError,
        match="must still belong to the aggregation run",
    ):
        repository.load_prediction_matrix(aggregation.id)


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
        match="requires exactly one result per snapshot person: expected 1, found 0",
    ):
        repository.mark_aggregation_finished(
            aggregation.id,
            status=AggregationExecutionStatus.completed,
            finished_at=NOW,
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
