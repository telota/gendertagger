import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.project import TeiImportProfile
from gendertagger.models.user import Role, UserCreate
from gendertagger.services.unit_of_work import UnitOfWork, UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

DATABASE_URL = "postgresql+psycopg://unused:unused@localhost/unused"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64
VALID_TEI = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body><listPerson>
    <person xml:id="p3">
      <persName type="reg"><surname>Third</surname></persName>
    </person>
    <person xml:id="p1">
      <persName type="reg"><surname>Example</surname><forename>Anna</forename></persName>
      <idno type="uri">https://d-nb.info/gnd/123456789</idno>
    </person>
    <person xml:id="p2">
      <persName type="reg"><surname>Second</surname></persName>
    </person>
  </listPerson></body></text>
</TEI>
"""


class StaticAuthenticationBackend(AuthenticationBackend):
    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    def authenticate(self, request: Request) -> UUID | None:
        return self._user_id

    def validate_csrf(self, request: Request, *, user_id: UUID) -> bool:
        return user_id == self._user_id


def _unit_of_work_factory(engine: Engine) -> UnitOfWorkFactory:
    session_factory = create_session_factory(engine)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory


def _operator_id(unit_of_work_factory: UnitOfWorkFactory) -> UUID:
    with unit_of_work_factory() as unit_of_work:
        operator = unit_of_work.users.add_user(
            UserCreate(display_name="HTTP operator", roles={Role.operator})
        )
        unit_of_work.commit()
    return operator.id


def _client(
    *,
    postgres_engine: Engine,
    artifact_root: Path,
) -> tuple[TestClient, UnitOfWorkFactory]:
    unit_of_work_factory = _unit_of_work_factory(postgres_engine)
    operator_id = _operator_id(unit_of_work_factory)
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
            artifact_root=artifact_root,
            tei_import_batch_record_count=1,
        ),
        unit_of_work_factory=unit_of_work_factory,
        authentication_backend=StaticAuthenticationBackend(operator_id),
    )
    return TestClient(application), unit_of_work_factory


def test_project_and_ready_snapshot_round_trip_through_http(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory = _client(
        postgres_engine=postgres_engine,
        artifact_root=tmp_path,
    )
    slug = f"http-{uuid4().hex}"

    project_response = client.post(
        "/api/v1/projects",
        json={"slug": slug, "display_name": "HTTP fixture"},
    )
    assert project_response.status_code == 201
    project_id = UUID(project_response.json()["id"])

    import_response = client.post(
        f"/api/v1/projects/{project_id}/snapshots",
        data={"profile": TeiImportProfile.tei_p5_person_register_v1.value},
        files={"source": ("register.xml", VALID_TEI, "application/xml")},
    )

    assert import_response.status_code == 202
    snapshot_body = import_response.json()
    assert snapshot_body["status"] == DatasetSnapshotStatus.ready.value
    assert snapshot_body["record_count"] == 3
    assert snapshot_body["source_sha256"] == hashlib.sha256(VALID_TEI).hexdigest()
    assert "storage_uri" not in snapshot_body

    snapshot_id = UUID(snapshot_body["id"])
    source_artifact_id = UUID(snapshot_body["source_artifact_id"])
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 200
    assert client.get(f"/api/v1/snapshots/{snapshot_id}").json() == snapshot_body
    assert snapshot_body["created_at"].endswith("Z")

    first_page_response = client.get(
        f"/api/v1/snapshots/{snapshot_id}/people",
        params={"limit": 2},
    )
    first_page = first_page_response.json()
    assert first_page_response.status_code == 200
    assert [person["tei_id"] for person in first_page["items"]] == ["p1", "p2"]
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]

    second_page = client.get(
        f"/api/v1/snapshots/{snapshot_id}/people",
        params={"limit": 2, "cursor": first_page["next_cursor"]},
    ).json()
    assert [person["tei_id"] for person in second_page["items"]] == ["p3"]
    assert second_page["has_more"] is False
    assert second_page["next_cursor"] is None

    invalid_cursor_response = client.get(
        f"/api/v1/snapshots/{snapshot_id}/people",
        params={"cursor": "invalid+cursor"},
    )
    assert invalid_cursor_response.status_code == 422
    assert invalid_cursor_response.json()["error"]["details"] == {"reason": "invalid_cursor"}

    oversized_limit_response = client.get(
        f"/api/v1/snapshots/{snapshot_id}/people",
        params={"limit": 201},
    )
    assert oversized_limit_response.status_code == 422
    assert oversized_limit_response.json()["error"]["code"] == "validation_error"

    with unit_of_work_factory() as unit_of_work:
        person = unit_of_work.projects.get_person_record_by_tei_id(snapshot_id, "p1")
        artifact = unit_of_work.artifacts.get_artifact(source_artifact_id)
    assert person is not None
    assert person.gnd_id == "123456789"
    assert artifact is not None
    assert artifact.project_id == project_id
    with LocalArtifactStorage(tmp_path).open(artifact.storage_uri) as stored_source:
        assert stored_source.read() == VALID_TEI


def test_invalid_tei_persists_failed_snapshot_without_source_disclosure(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, _ = _client(postgres_engine=postgres_engine, artifact_root=tmp_path)
    project_response = client.post(
        "/api/v1/projects",
        json={"slug": f"failed-{uuid4().hex}", "display_name": "Failed fixture"},
    )
    project_id = UUID(project_response.json()["id"])
    malicious_source = b"""<!DOCTYPE TEI [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<TEI xmlns="http://www.tei-c.org/ns/1.0"><person xml:id="p1"><note>&xxe;</note></person></TEI>
"""

    response = client.post(
        f"/api/v1/projects/{project_id}/snapshots",
        files={"source": ("malicious.xml", malicious_source, "application/xml")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == DatasetSnapshotStatus.failed.value
    assert "DOCTYPE" in body["failure_diagnostic"]
    assert "root:" not in body["failure_diagnostic"]
