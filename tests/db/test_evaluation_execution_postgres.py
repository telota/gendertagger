from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.aggregation_repository import SqlAlchemyAggregationRepository
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.evaluation_repository import SqlAlchemyEvaluationRepository
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.domain.aggregation_assessment import assess_reference_predictions
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.aggregation import AggregationExecutionCreate, AggregationResultWrite
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.evaluation import EvaluationDefinition, EvaluationExecutionCreate
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    EvaluationExecutionStatus,
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
    TeiImportProfile,
)
from gendertagger.models.run import (
    MethodExecutionCreate,
    PredictionWrite,
    RunCreate,
    TaskBatchCreate,
)
from gendertagger.services.persistence_errors import InvalidResourceStateError

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
DEFAULT_DEFINITION = EvaluationDefinition()


def _seed_reference_run(
    session: Session,
    *,
    extra_methods: tuple[str, ...] = (),
) -> tuple[UUID, tuple[UUID, ...], UUID]:
    projects = SqlAlchemyProjectRepository(session)
    project = projects.add_project(
        ProjectCreate(
            slug=f"evaluation-core-{uuid4().hex}",
            display_name="Evaluation core fixture",
        )
    )
    artifacts = SqlAlchemyArtifactRepository(session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri=f"local-sha256:{uuid4().hex}",
            sha256=uuid4().hex * 2,
            byte_size=1,
            media_type="application/tei+xml",
            project_id=project.id,
        )
    )
    # The legacy profile captures no structured name forms, which this fixture does not model.
    import_config = SnapshotImportConfig(
        profile=TeiImportProfile.tei_p5_person_register_v1,
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
                person=PersonInput(tei_id="p1", surname="Example"),
                source_member_name="source.xml",
                source_record_locator="1",
            )
        ],
    )
    projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
    person = projects.get_person_record_by_tei_id(snapshot.id, "p1")
    assert person is not None

    all_methods = (*DEFAULT_DEFINITION.required_methods, *extra_methods)
    runs = SqlAlchemyRunRepository(session)
    run = runs.add_run(
        RunCreate(
            dataset_snapshot_id=snapshot.id,
            resolved_config=RunConfig(
                methods=[MethodRunConfig(name=method_name) for method_name in all_methods]
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
    for method_name in all_methods:
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
            label=CanonicalLabel.male if method_name == "gnd" else None,
            status=(PredictionStatus.success if method_name == "gnd" else PredictionStatus.abstain),
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
            error_count=0,
        )
        runs.finalize_execution_if_complete(execution.id, finished_at=NOW)
    runs.finalize_run_if_complete(run.id, finished_at=NOW)
    return run.id, tuple(execution_ids), person.id


def _seed_reference_run_with_completed_aggregation(
    session: Session,
) -> tuple[UUID, tuple[UUID, ...], UUID, UUID]:
    """Seed a run covering both the aggregation and evaluation method rosters."""
    run_id, all_execution_ids, person_id = _seed_reference_run(
        session,
        extra_methods=("parenthetical_qualifier",),
    )
    evaluation_execution_ids = all_execution_ids[: len(DEFAULT_DEFINITION.required_methods)]

    aggregations = SqlAlchemyAggregationRepository(session)
    aggregation = aggregations.add_aggregation(
        AggregationExecutionCreate(
            run_id=run_id,
            method_execution_ids=all_execution_ids,
        )
    )
    aggregations.mark_aggregation_queued(aggregation.id)
    aggregations.claim_aggregation(aggregation.id, started_at=NOW)
    (person_predictions,) = aggregations.load_prediction_matrix(aggregation.id)
    aggregations.add_results(
        aggregation.id,
        [
            AggregationResultWrite(
                person_record_id=person_predictions.person_record_id,
                result=assess_reference_predictions(person_predictions.predictions),
            )
        ],
    )
    completed_aggregation = aggregations.mark_aggregation_finished(
        aggregation.id,
        status=AggregationExecutionStatus.completed,
        finished_at=NOW,
    )
    return run_id, evaluation_execution_ids, person_id, completed_aggregation.id


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
