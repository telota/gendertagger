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
from tests.factories import tei_person_input
from tests.seeding import (
    only_method_answers,
    seed_completed_aggregation,
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
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.export import ExportTaskMessage
from gendertagger.models.lifecycle import ExportExecutionStatus
from gendertagger.models.user import UserCreate
from gendertagger.services.export_execution import ExportExecutor
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
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
        project = seed_project(unit_of_work, slug_prefix="export")
        user = seed_member(unit_of_work, project.id, display_name="Export operator")
        snapshot = seed_ready_snapshot(
            unit_of_work, project.id, [tei_person_input(tei_id="p1", surname="Example")]
        )
        completed = seed_completed_run(
            unit_of_work,
            snapshot,
            REFERENCE_REQUIRED_METHODS,
            only_method_answers("gnd", CanonicalLabel.male),
        )
        aggregation = seed_completed_aggregation(
            unit_of_work, completed.run.id, completed.execution_ids
        )
        unit_of_work.commit()
    return user.id, completed.run.id, aggregation.id


def _outsider_id(unit_of_work_factory: UnitOfWorkFactory) -> UUID:
    with unit_of_work_factory() as unit_of_work:
        outsider = unit_of_work.users.add_user(UserCreate(display_name="Other project member"))
        unit_of_work.commit()
    return outsider.id


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

    rerun_body = client.post(
        "/api/v1/exports",
        json={
            "run_id": str(run_id),
            "aggregation_execution_id": str(aggregation_id),
            "format": "csv",
        },
    ).json()
    listed = client.get(f"/api/v1/runs/{run_id}/exports").json()
    assert [(item["id"], item["format"], item["status"]) for item in listed["items"]] == [
        (rerun_body["id"], "csv", ExportExecutionStatus.queued.value),
        (str(export_id), "json", ExportExecutionStatus.completed.value),
    ]
    assert client.get(f"/api/v1/runs/{uuid4()}/exports").status_code == 404

    application.state.authentication_backend = StaticAuthenticationBackend(
        _outsider_id(unit_of_work_factory)
    )
    hidden_responses = [
        client.get(f"/api/v1/exports/{export_id}"),
        client.get(f"/api/v1/exports/{export_id}/download"),
        client.get(f"/api/v1/runs/{run_id}/exports"),
        client.post(
            "/api/v1/exports",
            json={
                "run_id": str(run_id),
                "aggregation_execution_id": str(aggregation_id),
                "format": "json",
            },
        ),
    ]
    assert [response.status_code for response in hidden_responses] == [404, 404, 404, 404]
