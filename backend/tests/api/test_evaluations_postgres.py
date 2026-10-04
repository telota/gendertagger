import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from tests.factories import tei_person_input
from tests.seeding import (
    only_method_answers,
    seed_completed_run,
    seed_member,
    seed_project,
    seed_ready_snapshot,
)

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.evaluation import (
    EvaluationDefinition,
    EvaluationReport,
    EvaluationTaskMessage,
)
from gendertagger.models.lifecycle import EvaluationExecutionStatus
from gendertagger.models.user import UserCreate
from gendertagger.services.evaluation_execution import EvaluationExecutor
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"
CODE_GIT_COMMIT = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"
DEPENDENCY_LOCK_SHA256 = "b" * 64
NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)
DEFINITION = EvaluationDefinition()


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
) -> tuple[UUID, UUID, tuple[UUID, ...]]:
    with unit_of_work_factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="evaluation")
        user = seed_member(unit_of_work, project.id, display_name="Evaluation operator")
        snapshot = seed_ready_snapshot(
            unit_of_work, project.id, [tei_person_input(tei_id="p1", surname="Example")]
        )
        completed = seed_completed_run(
            unit_of_work,
            snapshot,
            DEFINITION.required_methods,
            only_method_answers("gnd", CanonicalLabel.male),
        )
        unit_of_work.commit()
    return user.id, completed.run.id, completed.execution_ids


def _outsider_id(unit_of_work_factory: UnitOfWorkFactory) -> UUID:
    with unit_of_work_factory() as unit_of_work:
        outsider = unit_of_work.users.add_user(UserCreate(display_name="Other project member"))
        unit_of_work.commit()
    return outsider.id


def test_queued_evaluation_executes_and_report_round_trips_through_http(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    unit_of_work_factory, _session_factory = _unit_of_work_factory(postgres_engine)
    user_id, run_id, execution_ids = _seed_completed_reference_executions(unit_of_work_factory)
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

    storage = LocalArtifactStorage(tmp_path)
    create_response = client.post(
        "/api/v1/evaluations",
        json={
            "run_id": str(run_id),
            "method_execution_ids": [str(execution_id) for execution_id in execution_ids],
        },
    )

    assert create_response.status_code == 202
    evaluation_body = create_response.json()
    assert evaluation_body["status"] == EvaluationExecutionStatus.queued.value
    assert evaluation_body["run_id"] == str(run_id)
    assert evaluation_body["definition"] == "gnd_benchmark_v1"
    evaluation_id = UUID(evaluation_body["id"])
    assert client.get(f"/api/v1/evaluations/{evaluation_id}").json() == evaluation_body

    completed = EvaluationExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        max_report_bytes=1_000_000,
        clock=lambda: NOW,
    ).execute(
        EvaluationTaskMessage(evaluation_execution_id=evaluation_id),
        attempt_count=1,
    )
    assert completed.status is EvaluationExecutionStatus.completed
    assert completed.report_artifact_id is not None
    with unit_of_work_factory() as unit_of_work:
        report_artifact = unit_of_work.artifacts.get_artifact(completed.report_artifact_id)
    assert report_artifact is not None
    with storage.open(report_artifact.storage_uri) as source:
        stored_report_bytes = source.read()

    report_response = client.get(f"/api/v1/evaluations/{evaluation_id}/report")
    assert report_response.status_code == 200
    assert report_response.headers["content-type"] == report_artifact.media_type
    assert report_response.content == stored_report_bytes
    assert hashlib.sha256(report_response.content).hexdigest() == report_artifact.sha256
    assert len(report_response.content) == report_artifact.byte_size
    report_body = report_response.json()
    EvaluationReport.model_validate(report_body)
    assert report_body["definition"] == "gnd_benchmark_v1"
    assert report_body["benchmark"]["size"] == 1
    assert len(report_body["coverage"]) == len(DEFINITION.required_methods)

    missing_report_response = client.get(f"/api/v1/evaluations/{uuid4()}/report")
    assert missing_report_response.status_code == 404

    rerun_body = client.post(
        "/api/v1/evaluations",
        json={
            "run_id": str(run_id),
            "method_execution_ids": [str(execution_id) for execution_id in execution_ids],
        },
    ).json()
    listed = client.get(f"/api/v1/runs/{run_id}/evaluations").json()
    assert [(item["id"], item["status"]) for item in listed["items"]] == [
        (rerun_body["id"], EvaluationExecutionStatus.queued.value),
        (str(evaluation_id), EvaluationExecutionStatus.completed.value),
    ]
    assert listed["items"][1]["method_execution_ids"] == [
        str(execution_id) for execution_id in execution_ids
    ]
    assert client.get(f"/api/v1/runs/{uuid4()}/evaluations").status_code == 404

    application.state.authentication_backend = StaticAuthenticationBackend(
        _outsider_id(unit_of_work_factory)
    )
    hidden_responses = [
        client.get(f"/api/v1/evaluations/{evaluation_id}"),
        client.get(f"/api/v1/evaluations/{evaluation_id}/report"),
        client.get(f"/api/v1/runs/{run_id}/evaluations"),
        client.post(
            "/api/v1/evaluations",
            json={
                "run_id": str(run_id),
                "method_execution_ids": [str(execution_id) for execution_id in execution_ids],
            },
        ),
    ]
    assert [response.status_code for response in hidden_responses] == [404, 404, 404, 404]
