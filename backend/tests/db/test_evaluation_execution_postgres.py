from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from tests.factories import tei_person_input
from tests.seeding import (
    only_method_answers,
    seed_completed_aggregation,
    seed_completed_run,
    seed_project,
    seed_ready_snapshot,
    session_repositories,
)

from gendertagger.db.repositories.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.repositories.evaluation_repository import SqlAlchemyEvaluationRepository
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionStatus,
)
from gendertagger.models.evaluation import EvaluationDefinition, EvaluationExecutionCreate
from gendertagger.models.lifecycle import EvaluationExecutionStatus
from gendertagger.services.ports.persistence_errors import InvalidResourceStateError

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
DEFAULT_DEFINITION = EvaluationDefinition()


def _seed_reference_run(
    session: Session,
    *,
    extra_methods: tuple[str, ...] = (),
) -> tuple[UUID, tuple[UUID, ...], UUID]:
    repositories = session_repositories(session)
    project = seed_project(repositories, slug_prefix="evaluation-core")
    snapshot = seed_ready_snapshot(
        repositories, project.id, [tei_person_input(tei_id="p1", surname="Example")]
    )
    completed = seed_completed_run(
        repositories,
        snapshot,
        (*DEFAULT_DEFINITION.required_methods, *extra_methods),
        only_method_answers("gnd", CanonicalLabel.male),
    )
    return completed.run.id, completed.execution_ids, completed.people["p1"].id


def _seed_reference_run_with_completed_aggregation(
    session: Session,
) -> tuple[UUID, tuple[UUID, ...], UUID, UUID]:
    """Seed a run covering both the aggregation and evaluation method rosters."""
    run_id, all_execution_ids, person_id = _seed_reference_run(
        session,
        extra_methods=("parenthetical_qualifier",),
    )
    evaluation_execution_ids = all_execution_ids[: len(DEFAULT_DEFINITION.required_methods)]

    aggregation = seed_completed_aggregation(
        session_repositories(session), run_id, all_execution_ids
    )
    return run_id, evaluation_execution_ids, person_id, aggregation.id


def _create(run_id: UUID, method_execution_ids: tuple[UUID, ...]) -> EvaluationExecutionCreate:
    return EvaluationExecutionCreate(
        run_id=run_id,
        resolved_config=DEFAULT_DEFINITION.model_dump(mode="json"),
        method_execution_ids=method_execution_ids,
    )


def test_evaluation_requires_every_definition_method_exactly_once(db_session: Session) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyEvaluationRepository(db_session)

    with pytest.raises(
        InvalidResourceStateError,
        match="invalid gnd_benchmark_v1 method selection: missing required methods: hivoto_xgboost",
    ):
        repository.add_evaluation(_create(run_id, execution_ids[:-1]))


def test_repository_claims_and_completes_with_a_report_artifact(db_session: Session) -> None:
    run_id, execution_ids, person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyEvaluationRepository(db_session)
    evaluation = repository.add_evaluation(_create(run_id, execution_ids))

    queued = repository.mark_evaluation_queued(evaluation.id)
    claimed = repository.claim_evaluation(evaluation.id, started_at=NOW)
    assert queued.status is EvaluationExecutionStatus.queued
    assert claimed is not None
    assert claimed.status is EvaluationExecutionStatus.running
    assert repository.claim_evaluation(evaluation.id, started_at=NOW) is None

    inputs = repository.load_evaluation_inputs(evaluation.id)
    assert len(inputs.corpus) == 1
    assert inputs.corpus[0].person_record_id == person_id
    assert set(inputs.corpus[0].predictions) == set(DEFAULT_DEFINITION.required_methods)
    assert inputs.corpus[0].predictions["gnd"].status is PredictionStatus.success
    assert inputs.aggregated_results is None

    report_artifact = SqlAlchemyArtifactRepository(db_session).add_artifact(
        ArtifactCreate(
            logical_type="evaluation_report",
            storage_uri=f"local-sha256:{uuid4().hex}",
            sha256=uuid4().hex * 2,
            byte_size=2,
            media_type="application/json",
            run_id=run_id,
            evaluation_execution_id=evaluation.id,
        )
    )
    completed = repository.mark_evaluation_finished(
        evaluation.id,
        status=EvaluationExecutionStatus.completed,
        finished_at=NOW,
        report_artifact_id=report_artifact.id,
    )

    assert completed.status is EvaluationExecutionStatus.completed
    assert completed.report_artifact_id == report_artifact.id
    assert repository.claim_evaluation(evaluation.id, started_at=NOW) is None
    with pytest.raises(
        InvalidResourceStateError,
        match="cannot load evaluation inputs from status completed",
    ):
        repository.load_evaluation_inputs(evaluation.id)


def test_repository_fails_without_reopening_after_completeness_failure(
    db_session: Session,
) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyEvaluationRepository(db_session)
    evaluation = repository.add_evaluation(_create(run_id, execution_ids))
    repository.claim_evaluation(evaluation.id, started_at=NOW)

    failed = repository.mark_evaluation_finished(
        evaluation.id,
        status=EvaluationExecutionStatus.failed,
        finished_at=NOW,
        failure_class="EvaluationInputError",
        failure_diagnostic="synthetic failure",
    )

    assert failed.status is EvaluationExecutionStatus.failed
    assert failed.report_artifact_id is None
    assert repository.claim_evaluation(evaluation.id, started_at=NOW) is None


def test_mark_finished_rejects_completion_without_a_report_artifact(
    db_session: Session,
) -> None:
    run_id, execution_ids, _person_id = _seed_reference_run(db_session)
    repository = SqlAlchemyEvaluationRepository(db_session)
    evaluation = repository.add_evaluation(_create(run_id, execution_ids))
    repository.claim_evaluation(evaluation.id, started_at=NOW)

    with pytest.raises(ValueError, match="requires a report artifact"):
        repository.mark_evaluation_finished(
            evaluation.id,
            status=EvaluationExecutionStatus.completed,
            finished_at=NOW,
        )


def test_concurrent_workers_claim_an_evaluation_only_once(postgres_engine: Engine) -> None:
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
        run_id, execution_ids, _person_id = _seed_reference_run(session)
        repository = SqlAlchemyEvaluationRepository(session)
        evaluation = repository.add_evaluation(_create(run_id, execution_ids))
        repository.mark_evaluation_queued(evaluation.id)
        session.commit()

    def claim() -> bool:
        with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
            claimed = SqlAlchemyEvaluationRepository(session).claim_evaluation(
                evaluation.id,
                started_at=NOW,
            )
            session.commit()
            return claimed is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = [future.result(timeout=10) for future in [pool.submit(claim), pool.submit(claim)]]

    assert claims.count(True) == 1
    assert claims.count(False) == 1


def test_evaluation_inputs_include_ensemble_evidence_from_a_completed_aggregation(
    db_session: Session,
) -> None:
    run_id, execution_ids, person_id, aggregation_id = (
        _seed_reference_run_with_completed_aggregation(db_session)
    )
    repository = SqlAlchemyEvaluationRepository(db_session)
    evaluation = repository.add_evaluation(
        EvaluationExecutionCreate(
            run_id=run_id,
            resolved_config=DEFAULT_DEFINITION.model_dump(mode="json"),
            method_execution_ids=execution_ids,
            aggregation_execution_id=aggregation_id,
        )
    )
    repository.claim_evaluation(evaluation.id, started_at=NOW)

    inputs = repository.load_evaluation_inputs(evaluation.id)

    assert inputs.aggregated_results is not None
    assert len(inputs.aggregated_results) == 1
    assert inputs.aggregated_results[0].person_record_id == person_id
    assert inputs.aggregated_results[0].label is CanonicalLabel.male
    assert inputs.human_reviewed_count == 0
    assert inputs.human_correction_count == 0


def test_add_evaluation_rejects_an_incomplete_aggregation(db_session: Session) -> None:
    _run_id, _execution_ids, _person_id, aggregation_id = (
        _seed_reference_run_with_completed_aggregation(db_session)
    )
    other_run_id, other_execution_ids, _other_person_id = _seed_reference_run(db_session)

    with pytest.raises(
        InvalidResourceStateError,
        match="the selected aggregation execution must belong to the evaluation run",
    ):
        SqlAlchemyEvaluationRepository(db_session).add_evaluation(
            EvaluationExecutionCreate(
                run_id=other_run_id,
                resolved_config=DEFAULT_DEFINITION.model_dump(mode="json"),
                method_execution_ids=other_execution_ids,
                aggregation_execution_id=aggregation_id,
            )
        )
