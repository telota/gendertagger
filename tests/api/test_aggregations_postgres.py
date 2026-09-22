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
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.aggregation import (
    AggregationTaskMessage,
)
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.lifecycle import AggregationExecutionStatus, TaskBatchStatus
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
from gendertagger.models.user import ProjectRole, UserCreate
from gendertagger.services.aggregation_execution import AggregationExecutor
from gendertagger.services.unit_of_work import UnitOfWork, UnitOfWorkFactory

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


def _seed_completed_reference_executions(
    unit_of_work_factory: UnitOfWorkFactory,
    _session_factory: sessionmaker[Session],
) -> tuple[UUID, UUID, tuple[UUID, ...], tuple[UUID, UUID]]:
    with unit_of_work_factory() as unit_of_work:
        user = unit_of_work.users.add_user(
            UserCreate(display_name="Aggregation operator", roles=set())
        )
        project = unit_of_work.projects.add_project(
            ProjectCreate(
                slug=f"aggregation-{uuid4().hex}",
                display_name="Aggregation fixture",
            )
        )
        unit_of_work.access.set_member_role(project.id, user.id, ProjectRole.operator)
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
        # The legacy profile captures no structured name forms, which this fixture does not model.
        import_config = SnapshotImportConfig(
            profile=TeiImportProfile.tei_p5_person_register_v1,
            limits=SnapshotImportLimits(),
        )
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
                ),
                ImportedPerson(
                    person=PersonInput(tei_id="p2", surname="Second"),
                    source_member_name="source.xml",
                    source_record_locator="2",
                ),
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
        first_person = unit_of_work.projects.get_person_record_by_tei_id(snapshot.id, "p1")
        second_person = unit_of_work.projects.get_person_record_by_tei_id(snapshot.id, "p2")
        assert first_person is not None
        assert second_person is not None
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
                    total_count=2,
                )
            )
            execution_ids.append(execution.id)
            batch = unit_of_work.runs.add_task_batch(
                TaskBatchCreate(
                    method_execution_id=execution.id,
                    batch_index=0,
                    queue_name="cpu",
                    record_offset=0,
                    record_count=2,
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
            results: list[PredictionWrite] = []
            for index, person in enumerate((first_person, second_person), start=1):
                if method_name == "local_llm":
                    result = PredictionResult(
                        label=(
                            CanonicalLabel.female
                            if person.id == first_person.id
                            else CanonicalLabel.male
                        ),
                        status=PredictionStatus.success,
                        raw_label="female" if person.id == first_person.id else "male",
                        metadata={"self_reported_certainty": "high"},
                    )
                else:
                    result = PredictionResult(
                        label=None,
                        status=PredictionStatus.abstain,
                    )
                results.append(
                    PredictionWrite(
                        person_record_id=person.id,
                        task_batch_id=batch.id,
                        input_fingerprint=str(index) * 64,
                        result=result,
                    )
                )
            unit_of_work.runs.add_predictions(execution.id, results)
            unit_of_work.runs.mark_batch_finished(
                batch.id,
                status=TaskBatchStatus.completed,
                finished_at=NOW,
                success_count=2 if method_name == "local_llm" else 0,
                abstain_count=0 if method_name == "local_llm" else 2,
            )
            unit_of_work.runs.finalize_execution_if_complete(execution.id, finished_at=NOW)
        unit_of_work.runs.finalize_run_if_complete(run.id, finished_at=NOW)
        unit_of_work.commit()
    return user.id, run.id, tuple(execution_ids), (first_person.id, second_person.id)


def _outsider_id(unit_of_work_factory: UnitOfWorkFactory) -> UUID:
    with unit_of_work_factory() as unit_of_work:
        outsider = unit_of_work.users.add_user(UserCreate(display_name="Other project member"))
        unit_of_work.commit()
    return outsider.id


def test_queued_aggregation_executes_and_results_round_trip_through_http(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    unit_of_work_factory, session_factory = _unit_of_work_factory(postgres_engine)
    user_id, run_id, execution_ids, person_ids = _seed_completed_reference_executions(
        unit_of_work_factory,
        session_factory,
    )
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
        f"/api/v1/runs/{run_id}/aggregations",
        json={"method_execution_ids": [str(execution_id) for execution_id in execution_ids]},
    )

    assert create_response.status_code == 202
    aggregation_body = create_response.json()
    assert aggregation_body["status"] == AggregationExecutionStatus.queued.value
    assert aggregation_body["run_id"] == str(run_id)
    assert aggregation_body["method_execution_ids"] == [
        str(execution_id) for execution_id in execution_ids
    ]
    aggregation_id = UUID(aggregation_body["id"])
    assert client.get(f"/api/v1/aggregations/{aggregation_id}").json() == aggregation_body

    completed = AggregationExecutor(
        unit_of_work_factory=unit_of_work_factory,
        clock=lambda: NOW,
    ).execute(
        AggregationTaskMessage(aggregation_execution_id=aggregation_id),
        attempt_count=1,
    )
    assert completed.status is AggregationExecutionStatus.completed

    with unit_of_work_factory() as unit_of_work:
        dispatch = unit_of_work.dispatches.get_dispatch_for_aggregation(aggregation_id)
        persisted_results = unit_of_work.aggregations.list_results(
            aggregation_id,
            limit=10,
        )
    assert dispatch is not None
    assert len(persisted_results) == 2
    results_by_person = {result.person_record_id: result for result in persisted_results}
    assert results_by_person[person_ids[0]].label is CanonicalLabel.female
    assert results_by_person[person_ids[1]].label is CanonicalLabel.male
    result_id = persisted_results[0].id

    first_page = client.get(
        f"/api/v1/aggregations/{aggregation_id}/results",
        params={"limit": 1},
    ).json()
    second_page = client.get(
        f"/api/v1/aggregations/{aggregation_id}/results",
        params={"limit": 1, "cursor": first_page["next_cursor"]},
    ).json()
    assert [item["id"] for item in first_page["items"] + second_page["items"]] == [
        str(result.id) for result in persisted_results
    ]
    assert first_page["has_more"] is True
    assert second_page["has_more"] is False
    assert second_page["next_cursor"] is None

    result_response = client.get(f"/api/v1/aggregations/{aggregation_id}/results/{result_id}")

    assert result_response.status_code == 200
    expected_label = persisted_results[0].label
    assert expected_label is not None
    assert result_response.json()["label"] == expected_label.value
    wrong_owner_response = client.get(f"/api/v1/aggregations/{uuid4()}/results/{result_id}")
    assert wrong_owner_response.status_code == 404

    application.state.authentication_backend = StaticAuthenticationBackend(
        _outsider_id(unit_of_work_factory)
    )
    hidden_responses = [
        client.get(f"/api/v1/aggregations/{aggregation_id}"),
        client.get(f"/api/v1/aggregations/{aggregation_id}/results"),
        client.get(f"/api/v1/aggregations/{aggregation_id}/results/{result_id}"),
        client.get(f"/api/v1/runs/{run_id}"),
        client.post(
            f"/api/v1/runs/{run_id}/aggregations",
            json={"method_execution_ids": [str(execution_id) for execution_id in execution_ids]},
        ),
    ]
    assert [response.status_code for response in hidden_responses] == [404] * 5
