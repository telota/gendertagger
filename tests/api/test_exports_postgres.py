import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
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
from gendertagger.models.export import ExportTaskMessage
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    ExportExecutionStatus,
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
    MethodExecutionCreate,
    PredictionWrite,
    RunCreate,
    TaskBatchCreate,
)
from gendertagger.models.user import Role, UserCreate
from gendertagger.services.export_execution import ExportExecutor
from gendertagger.services.unit_of_work import UnitOfWork, UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"
CODE_GIT_COMMIT = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"
DEPENDENCY_LOCK_SHA256 = "b" * 64
NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)


class StaticAuthenticationBackend(AuthenticationBackend):
    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    def authenticate(self, request: Request) -> UUID | None:
        return self._user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        return user_id == self._user_id


def _unit_of_work_factory(
    engine: Engine,
) -> tuple[UnitOfWorkFactory, sessionmaker[Session]]:
    session_factory = create_session_factory(engine)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory, session_factory


def _seed_completed_aggregation(
    unit_of_work_factory: UnitOfWorkFactory,
) -> tuple[UUID, UUID, UUID]:
    with unit_of_work_factory() as unit_of_work:
        user = unit_of_work.users.add_user(
            UserCreate(display_name="Export operator", roles={Role.operator})
        )
        project = unit_of_work.projects.add_project(
            ProjectCreate(
                slug=f"export-{uuid4().hex}",
                display_name="Export fixture",
            )
        )
        artifact = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="source_tei",
                storage_uri=f"local-sha256:{'a' * 64}",
                sha256="a" * 64,
                byte_size=1,
                media_type="application/tei+xml",
                project_id=project.id,
            )
        )
        import_config = SnapshotImportConfig(limits=SnapshotImportLimits())
        snapshot = unit_of_work.projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=artifact.id,
                source_sha256=artifact.sha256,
                parser_version=version_for_snapshot_import(import_config),
                import_config=import_config.model_dump(mode="json"),
            )
        )
        unit_of_work.projects.add_snapshot_source_members(
            snapshot.id,
            [
                SnapshotSourceMemberCreate(
                    artifact_id=artifact.id,
                    ordinal=0,
                    logical_name="source.xml",
                    sha256=artifact.sha256,
                    byte_size=artifact.byte_size,
                    media_type=artifact.media_type,
                )
            ],
        )
        unit_of_work.projects.begin_snapshot_import(snapshot.id)
        unit_of_work.projects.add_imported_person_records(
            snapshot.id,
            [
                ImportedPerson(
                    person=PersonInput(tei_id="p1", surname="Example"),
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
                        MethodRunConfig(name=method_name)
                        for method_name in REFERENCE_REQUIRED_METHODS
                    ]
                ),
                code_git_commit=CODE_GIT_COMMIT,
                application_version="0.0.0",
                python_version="3.13.14",
                dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            )
        )
        unit_of_work.runs.mark_run_queued(run.id)
        unit_of_work.runs.mark_run_started(run.id, started_at=NOW)
        person = unit_of_work.projects.get_person_record_by_tei_id(snapshot.id, "p1")
        assert person is not None
        execution_ids: list[UUID] = []
        for method_name in REFERENCE_REQUIRED_METHODS:
            execution = unit_of_work.runs.add_method_execution(
                MethodExecutionCreate(
                    run_id=run.id,
                    descriptor=MethodDescriptor(
                        name=method_name,
                        implementation_version=f"{method_name}_v1",
                        normalization_version=f"{method_name}_v1",
                    ),
                    queue_name="cpu",
                    total_count=1,
                )
            )
            execution_ids.append(execution.id)
            batch = unit_of_work.runs.add_task_batch(
                TaskBatchCreate(
                    method_execution_id=execution.id,
                    batch_index=0,
                    queue_name="cpu",
                    record_offset=0,
                    record_count=1,
                )
            )
            unit_of_work.runs.mark_execution_queued(execution.id)
            unit_of_work.runs.mark_execution_started(execution.id, started_at=NOW)
            claimed_batch = unit_of_work.runs.claim_batch(
                batch.id,
                method_execution_id=execution.id,
                worker_task_id=f"fixture-{method_name}",
                started_at=NOW,
                attempt_count=1,
            )
            assert claimed_batch is not None
            result = (
                PredictionResult(label=CanonicalLabel.male, status=PredictionStatus.success)
                if method_name == "gnd"
                else PredictionResult(label=None, status=PredictionStatus.abstain)
            )
            unit_of_work.runs.add_predictions(
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
            unit_of_work.runs.mark_batch_finished(
                batch.id,
                status=TaskBatchStatus.completed,
                finished_at=NOW,
                success_count=int(result.status is PredictionStatus.success),
                abstain_count=int(result.status is PredictionStatus.abstain),
            )
            unit_of_work.runs.finalize_execution_if_complete(execution.id, finished_at=NOW)
        unit_of_work.runs.finalize_run_if_complete(run.id, finished_at=NOW)

        aggregation = unit_of_work.aggregations.add_aggregation(
            AggregationExecutionCreate(
                run_id=run.id,
                method_execution_ids=tuple(execution_ids),
            )
        )
        unit_of_work.aggregations.mark_aggregation_queued(aggregation.id)
        unit_of_work.aggregations.claim_aggregation(aggregation.id, started_at=NOW)
        (person_predictions,) = unit_of_work.aggregations.load_prediction_matrix(aggregation.id)
        unit_of_work.aggregations.add_results(
            aggregation.id,
            [
                AggregationResultWrite(
                    person_record_id=person_predictions.person_record_id,
                    result=assess_reference_predictions(person_predictions.predictions),
                )
            ],
        )
        completed_aggregation = unit_of_work.aggregations.mark_aggregation_finished(
            aggregation.id,
            status=AggregationExecutionStatus.completed,
            finished_at=NOW,
        )
        unit_of_work.commit()
    return user.id, run.id, completed_aggregation.id


def test_queued_export_executes_and_output_round_trips_through_http(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    unit_of_work_factory, _session_factory = _unit_of_work_factory(postgres_engine)
    user_id, run_id, aggregation_id = _seed_completed_aggregation(unit_of_work_factory)
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            artifact_root=tmp_path,
        ),
        unit_of_work_factory=unit_of_work_factory,
        authentication_backend=StaticAuthenticationBackend(user_id),
    )
    client = TestClient(application)

    create_response = client.post(
        "/api/v1/exports",
        json={
            "run_id": str(run_id),
            "aggregation_execution_id": str(aggregation_id),
            "format": "json",
        },
    )

    assert create_response.status_code == 202
    export_body = create_response.json()
    assert export_body["status"] == ExportExecutionStatus.queued.value
    assert export_body["run_id"] == str(run_id)
    assert export_body["format"] == "json"
    export_id = UUID(export_body["id"])
    assert client.get(f"/api/v1/exports/{export_id}").json() == export_body

    completed = ExportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(tmp_path),
        max_output_bytes=1_000_000,
        clock=lambda: NOW,
    ).execute(
        ExportTaskMessage(export_id=export_id),
        attempt_count=1,
    )
    assert completed.status is ExportExecutionStatus.completed
    assert completed.manifest_artifact_id is not None

    download_response = client.get(f"/api/v1/exports/{export_id}/download")
    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith("application/json")
    records = json.loads(download_response.content)
    assert len(records) == 1
    assert records[0]["label"] == "male"

    missing_download_response = client.get(f"/api/v1/exports/{uuid4()}/download")
    assert missing_download_response.status_code == 404
