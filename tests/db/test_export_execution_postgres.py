from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from tests.factories import tei_person_input

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.aggregation_repository import SqlAlchemyAggregationRepository
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.export_repository import SqlAlchemyExportRepository
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.review_repository import SqlAlchemyReviewRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.db.user_repository import SqlAlchemyUserRepository
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.domain.aggregation_assessment import assess_reference_predictions
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.aggregation import AggregationExecutionCreate, AggregationResultWrite
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.export import (
    ExportExecutionCreate,
    ExportFormat,
    LabelSourcePolicy,
    TeiExportProfile,
)
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    ExportExecutionStatus,
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
    SourceFormat,
    SourcePackaging,
    TabularImportProfile,
    TeiImportProfile,
)
from gendertagger.models.review import AnnotationCreate, ReviewAction
from gendertagger.models.run import (
    MethodExecutionCreate,
    PredictionWrite,
    RunCreate,
    TaskBatchCreate,
)
from gendertagger.models.user import UserCreate
from gendertagger.services.persistence_errors import InvalidResourceStateError

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
_TEST_IMPORT_LIMITS = SnapshotImportLimits(
    max_member_count=8,
    max_member_expanded_bytes=1_000_000,
    max_total_expanded_bytes=2_000_000,
    max_compression_ratio=100.0,
    max_record_count=10_000,
    max_cell_bytes=1_000_000,
)


def _seed_reference_run_with_completed_aggregation(
    session: Session,
) -> tuple[UUID, UUID, UUID]:
    """Seed one snapshot person with a completed reference aggregation."""
    projects = SqlAlchemyProjectRepository(session)
    project = projects.add_project(
        ProjectCreate(
            slug=f"export-core-{uuid4().hex}",
            display_name="Export core fixture",
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

    aggregations = SqlAlchemyAggregationRepository(session)
    aggregation = aggregations.add_aggregation(
        AggregationExecutionCreate(
            run_id=run.id,
            method_execution_ids=tuple(execution_ids),
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
    return run.id, completed_aggregation.id, person.id


def _create(run_id: UUID, aggregation_execution_id: UUID) -> ExportExecutionCreate:
    return ExportExecutionCreate(
        run_id=run_id,
        aggregation_execution_id=aggregation_execution_id,
        format=ExportFormat.json,
    )


def test_add_export_rejects_an_incomplete_aggregation(db_session: Session) -> None:
    projects = SqlAlchemyProjectRepository(db_session)
    project = projects.add_project(
        ProjectCreate(slug=f"export-incomplete-{uuid4().hex}", display_name="Incomplete fixture")
    )
    other_source = SqlAlchemyArtifactRepository(db_session).add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri=f"local-sha256:{uuid4().hex}",
            sha256=uuid4().hex * 2,
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
            source_artifact_id=other_source.id,
            source_sha256=other_source.sha256,
            parser_version=version_for_snapshot_import(import_config),
            import_config=import_config.model_dump(mode="json"),
        )
    )
    projects.add_snapshot_source_members(
        snapshot.id,
        [
            SnapshotSourceMemberCreate(
                artifact_id=other_source.id,
                ordinal=0,
                logical_name="source.xml",
                sha256=other_source.sha256,
                byte_size=other_source.byte_size,
                media_type=other_source.media_type,
            )
        ],
    )
    projects.begin_snapshot_import(snapshot.id)
    projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
    runs = SqlAlchemyRunRepository(db_session)
    other_run = runs.add_run(
        RunCreate(
            dataset_snapshot_id=snapshot.id,
            resolved_config=RunConfig(
                methods=[
                    MethodRunConfig(name=method_name) for method_name in REFERENCE_REQUIRED_METHODS
                ],
            ),
            code_git_commit="f" * 40,
            application_version="0.0.0",
            python_version="3.13.14",
            dependency_lock_sha256="a" * 64,
        )
    )
    runs.mark_run_queued(other_run.id)
    runs.mark_run_started(other_run.id, started_at=NOW)
    execution_ids: list[UUID] = []
    for method_name in REFERENCE_REQUIRED_METHODS:
        execution = runs.add_method_execution(
            MethodExecutionCreate(
                run_id=other_run.id,
                descriptor=MethodDescriptor(
                    name=method_name,
                    implementation_version="test_v1",
                    normalization_version="test_v1",
                ),
                queue_name="cpu",
                total_count=0,
            )
        )
        execution_ids.append(execution.id)
        runs.mark_execution_queued(execution.id)
        runs.mark_execution_started(execution.id, started_at=NOW)
        runs.finalize_execution_if_complete(execution.id, finished_at=NOW)

    aggregations = SqlAlchemyAggregationRepository(db_session)
    pending_aggregation = aggregations.add_aggregation(
        AggregationExecutionCreate(run_id=other_run.id, method_execution_ids=tuple(execution_ids))
    )

    with pytest.raises(
        InvalidResourceStateError,
        match=f"aggregation execution {pending_aggregation.id} is not completed",
    ):
        SqlAlchemyExportRepository(db_session).add_export(
            _create(other_run.id, pending_aggregation.id)
        )


def test_add_export_rejects_a_run_mismatched_aggregation(db_session: Session) -> None:
    run_id, aggregation_id, _person_id = _seed_reference_run_with_completed_aggregation(db_session)
    _other_run_id, _other_aggregation_id, _other_person_id = (
        _seed_reference_run_with_completed_aggregation(db_session)
    )

    with pytest.raises(
        InvalidResourceStateError,
        match="the selected aggregation execution must belong to the export run",
    ):
        SqlAlchemyExportRepository(db_session).add_export(_create(_other_run_id, aggregation_id))
    assert run_id != _other_run_id


def test_repository_claims_and_completes_with_a_manifest_artifact(db_session: Session) -> None:
    run_id, aggregation_id, person_id = _seed_reference_run_with_completed_aggregation(db_session)
    repository = SqlAlchemyExportRepository(db_session)
    export = repository.add_export(_create(run_id, aggregation_id))

    queued = repository.mark_export_queued(export.id)
    claimed = repository.claim_export(export.id, started_at=NOW)
    assert queued.status is ExportExecutionStatus.queued
    assert claimed is not None
    assert claimed.status is ExportExecutionStatus.running
    assert repository.claim_export(export.id, started_at=NOW) is None

    inputs = repository.load_export_inputs(export.id)
    assert len(inputs.records) == 1
    assert inputs.records[0].person_record_id == person_id
    assert inputs.records[0].label is CanonicalLabel.male

    manifest_artifact = SqlAlchemyArtifactRepository(db_session).add_artifact(
        ArtifactCreate(
            logical_type="export_manifest",
            storage_uri=f"local-sha256:{uuid4().hex}",
            sha256=uuid4().hex * 2,
            byte_size=2,
            media_type="application/json",
            run_id=run_id,
            export_id=export.id,
        )
    )
    completed = repository.mark_export_finished(
        export.id,
        status=ExportExecutionStatus.completed,
        finished_at=NOW,
        manifest_artifact_id=manifest_artifact.id,
    )

    assert completed.status is ExportExecutionStatus.completed
    assert completed.manifest_artifact_id == manifest_artifact.id
    assert repository.claim_export(export.id, started_at=NOW) is None
    with pytest.raises(
        InvalidResourceStateError,
        match="cannot load export inputs from status completed",
    ):
        repository.load_export_inputs(export.id)


def test_repository_fails_without_reopening_after_failure(db_session: Session) -> None:
    run_id, aggregation_id, _person_id = _seed_reference_run_with_completed_aggregation(db_session)
    repository = SqlAlchemyExportRepository(db_session)
    export = repository.add_export(_create(run_id, aggregation_id))
    repository.claim_export(export.id, started_at=NOW)

    failed = repository.mark_export_finished(
        export.id,
        status=ExportExecutionStatus.failed,
        finished_at=NOW,
        failure_class="InvalidResourceStateError",
        failure_diagnostic="synthetic failure",
    )

    assert failed.status is ExportExecutionStatus.failed
    assert failed.manifest_artifact_id is None
    assert repository.claim_export(export.id, started_at=NOW) is None


def test_mark_finished_rejects_completion_without_a_manifest_artifact(
    db_session: Session,
) -> None:
    run_id, aggregation_id, _person_id = _seed_reference_run_with_completed_aggregation(db_session)
    repository = SqlAlchemyExportRepository(db_session)
    export = repository.add_export(_create(run_id, aggregation_id))
    repository.claim_export(export.id, started_at=NOW)

    with pytest.raises(ValueError, match="requires a manifest artifact"):
        repository.mark_export_finished(
            export.id,
            status=ExportExecutionStatus.completed,
            finished_at=NOW,
        )


def test_concurrent_workers_claim_an_export_only_once(postgres_engine: Engine) -> None:
    with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
        run_id, aggregation_id, _person_id = _seed_reference_run_with_completed_aggregation(session)
        repository = SqlAlchemyExportRepository(session)
        export = repository.add_export(_create(run_id, aggregation_id))
        repository.mark_export_queued(export.id)
        session.commit()

    def claim() -> bool:
        with Session(postgres_engine, autoflush=False, expire_on_commit=False) as session:
            claimed = SqlAlchemyExportRepository(session).claim_export(
                export.id,
                started_at=NOW,
            )
            session.commit()
            return claimed is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = [future.result(timeout=10) for future in [pool.submit(claim), pool.submit(claim)]]

    assert claims.count(True) == 1
    assert claims.count(False) == 1


def _expected_primary_logical_type(import_config: SnapshotImportConfig) -> str:
    if import_config.packaging is SourcePackaging.zip:
        return "source_zip"
    if import_config.packaging is SourcePackaging.tar_gz:
        return "source_tar_gz"
    return f"source_{import_config.source_format.value}"


def _seed_zero_person_run_with_completed_aggregation(
    session: Session,
    *,
    import_config: SnapshotImportConfig,
) -> tuple[UUID, UUID]:
    """Seed a zero-person modern-import snapshot with a completed aggregation."""
    projects = SqlAlchemyProjectRepository(session)
    project = projects.add_project(
        ProjectCreate(
            slug=f"export-zero-person-{uuid4().hex}",
            display_name="Export zero-person fixture",
        )
    )
    artifacts = SqlAlchemyArtifactRepository(session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type=_expected_primary_logical_type(import_config),
            storage_uri=f"local-sha256:{uuid4().hex}",
            sha256=uuid4().hex * 2,
            byte_size=1,
            media_type="application/octet-stream",
            project_id=project.id,
        )
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
                logical_name="primary",
                sha256=source.sha256,
                byte_size=source.byte_size,
                media_type=source.media_type,
            )
        ],
    )
    projects.begin_snapshot_import(snapshot.id)
    ready = projects.complete_snapshot_import(snapshot.id, ready_at=NOW)
    assert ready.record_count == 0

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
                total_count=0,
            )
        )
        execution_ids.append(execution.id)
        runs.mark_execution_queued(execution.id)
        runs.mark_execution_started(execution.id, started_at=NOW)
        runs.finalize_execution_if_complete(execution.id, finished_at=NOW)
    runs.finalize_run_if_complete(run.id, finished_at=NOW)

    aggregations = SqlAlchemyAggregationRepository(session)
    aggregation = aggregations.add_aggregation(
        AggregationExecutionCreate(run_id=run.id, method_execution_ids=tuple(execution_ids))
    )
    aggregations.mark_aggregation_queued(aggregation.id)
    aggregations.claim_aggregation(aggregation.id, started_at=NOW)
    assert aggregations.load_prediction_matrix(aggregation.id) == ()
    aggregations.add_results(aggregation.id, [])
    completed = aggregations.mark_aggregation_finished(
        aggregation.id,
        status=AggregationExecutionStatus.completed,
        finished_at=NOW,
    )
    return run.id, completed.id


def test_load_export_inputs_rejects_tei_format_for_a_non_tei_snapshot(
    db_session: Session,
) -> None:
    run_id, aggregation_id = _seed_zero_person_run_with_completed_aggregation(
        db_session,
        import_config=SnapshotImportConfig(
            source_format=SourceFormat.csv,
            packaging=SourcePackaging.single,
            profile=TabularImportProfile.tei_equivalent_person_register_v1,
            limits=_TEST_IMPORT_LIMITS,
        ),
    )
    repository = SqlAlchemyExportRepository(db_session)
    export = repository.add_export(
        ExportExecutionCreate(
            run_id=run_id,
            aggregation_execution_id=aggregation_id,
            format=ExportFormat.tei,
            tei_profile=TeiExportProfile.tei_p5_gender_v1,
        )
    )
    repository.claim_export(export.id, started_at=NOW)

    with pytest.raises(InvalidResourceStateError, match="is not a TEI source"):
        repository.load_export_inputs(export.id)


def test_load_export_inputs_rejects_tei_format_for_unsupported_packaging(
    db_session: Session,
) -> None:
    run_id, aggregation_id = _seed_zero_person_run_with_completed_aggregation(
        db_session,
        import_config=SnapshotImportConfig(
            source_format=SourceFormat.tei,
            packaging=SourcePackaging.zip,
            profile=TeiImportProfile.tei_p5_person_register,
            limits=_TEST_IMPORT_LIMITS,
        ),
    )
    repository = SqlAlchemyExportRepository(db_session)
    export = repository.add_export(
        ExportExecutionCreate(
            run_id=run_id,
            aggregation_execution_id=aggregation_id,
            format=ExportFormat.tei,
            tei_profile=TeiExportProfile.tei_p5_gender_v1,
        )
    )
    repository.claim_export(export.id, started_at=NOW)

    with pytest.raises(InvalidResourceStateError, match="does not yet support"):
        repository.load_export_inputs(export.id)


def test_load_export_inputs_projects_human_overrides_when_policy_is_human_overrides(
    db_session: Session,
) -> None:
    run_id, aggregation_id, person_id = _seed_reference_run_with_completed_aggregation(db_session)
    users = SqlAlchemyUserRepository(db_session)
    reviewer = users.add_user(UserCreate(display_name="Export reviewer"))
    snapshot_id = SqlAlchemyRunRepository(db_session).get_run(run_id)
    assert snapshot_id is not None
    SqlAlchemyReviewRepository(db_session).add_annotation(
        AnnotationCreate(
            snapshot_id=snapshot_id.dataset_snapshot_id,
            tei_id="p1",
            action=ReviewAction.correct,
            label=CanonicalLabel.female,
            expected_revision=0,
        ),
        reviewer_user_id=reviewer.id,
    )
    repository = SqlAlchemyExportRepository(db_session)
    export = repository.add_export(
        ExportExecutionCreate(
            run_id=run_id,
            aggregation_execution_id=aggregation_id,
            format=ExportFormat.json,
            label_source_policy=LabelSourcePolicy.human_overrides,
        )
    )
    repository.claim_export(export.id, started_at=NOW)

    inputs = repository.load_export_inputs(export.id)

    assert len(inputs.records) == 1
    assert inputs.records[0].person_record_id == person_id
    assert inputs.records[0].label is CanonicalLabel.female
    assert inputs.records[0].is_human_reviewed is True
