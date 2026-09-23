import hashlib
from datetime import UTC, datetime
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
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.dispatch import DispatchStatus
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.project import (
    SnapshotImportTaskMessage,
    SourceFormat,
    SourcePackaging,
    TeiImportProfile,
)
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.models.user import GlobalRole, UserCreate
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from gendertagger.services.snapshot_import import SnapshotImportExecutor
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
      <persName type="alt" subtype="birthname"><surname>Earlier</surname><forename>Annette</forename></persName>
      <persName type="alt"><name>A. Example</name></persName>
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
            UserCreate(display_name="HTTP operator", roles={GlobalRole.operator})
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


def _execute_snapshot_import(
    unit_of_work_factory: UnitOfWorkFactory,
    artifact_root: Path,
    snapshot_id: UUID,
) -> None:
    SnapshotImportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(artifact_root),
        parser=TeiPersonParser(),
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=UTC),
        import_batch_record_count=1,
    ).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=snapshot_id),
        attempt_count=1,
    )


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
        files={"source": ("register.xml", VALID_TEI, "application/xml")},
    )

    assert import_response.status_code == 202
    snapshot_body = import_response.json()
    assert snapshot_body["status"] == DatasetSnapshotStatus.pending.value
    assert snapshot_body["record_count"] is None
    assert snapshot_body["ready_at"] is None
    assert snapshot_body["parser_version"] == (
        "tei_parser_v3+tei_collection_v1+tei_single_source_v1"
    )
    assert snapshot_body["import_config"] == {
        "source_format": SourceFormat.tei.value,
        "packaging": SourcePackaging.single.value,
        "profile": TeiImportProfile.tei_p5_person_register.value,
        "limits": {
            "max_member_count": 128,
            "max_member_expanded_bytes": 100 * 1024 * 1024,
            "max_total_expanded_bytes": 500 * 1024 * 1024,
            "max_compression_ratio": 100.0,
            "max_record_count": 1_000_000,
            "max_cell_bytes": 1024 * 1024,
        },
    }
    assert snapshot_body["source_sha256"] == hashlib.sha256(VALID_TEI).hexdigest()
    assert "storage_uri" not in snapshot_body

    snapshot_id = UUID(snapshot_body["id"])
    source_artifact_id = UUID(snapshot_body["source_artifact_id"])
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 200
    assert client.get(f"/api/v1/snapshots/{snapshot_id}").json() == snapshot_body
    assert snapshot_body["created_at"].endswith("Z")

    source_members_response = client.get(f"/api/v1/snapshots/{snapshot_id}/source-members")
    assert source_members_response.status_code == 200
    source_members = source_members_response.json()
    assert len(source_members) == 1
    assert source_members[0]["logical_name"] == "register.xml"
    assert source_members[0]["sha256"] == hashlib.sha256(VALID_TEI).hexdigest()
    assert source_members[0]["byte_size"] == len(VALID_TEI)
    assert source_members[0]["media_type"] == "application/xml"
    assert source_members[0]["ordinal"] == 0
    assert "storage_uri" not in source_members[0]

    pending_people_response = client.get(f"/api/v1/snapshots/{snapshot_id}/people")
    assert pending_people_response.status_code == 409
    pending_person_response = client.get(f"/api/v1/snapshots/{snapshot_id}/people/p1")
    assert pending_person_response.status_code == 409

    with unit_of_work_factory() as unit_of_work:
        dispatch = unit_of_work.dispatches.get_dispatch_for_snapshot(snapshot_id)
        artifact = unit_of_work.artifacts.get_artifact(source_artifact_id)
    assert dispatch is not None
    assert dispatch.status is DispatchStatus.pending
    assert dispatch.queue_name == CPU_QUEUE
    assert dispatch.payload == SnapshotImportTaskMessage(dataset_snapshot_id=snapshot_id)
    assert artifact is not None
    assert artifact.project_id == project_id
    with LocalArtifactStorage(tmp_path).open(artifact.storage_uri) as stored_source:
        assert stored_source.read() == VALID_TEI

    _execute_snapshot_import(unit_of_work_factory, tmp_path, snapshot_id)
    _execute_snapshot_import(unit_of_work_factory, tmp_path, snapshot_id)
    ready_snapshot_body = client.get(f"/api/v1/snapshots/{snapshot_id}").json()
    assert ready_snapshot_body["status"] == DatasetSnapshotStatus.ready.value
    assert ready_snapshot_body["record_count"] == 3
    assert ready_snapshot_body["ready_at"].endswith("Z")

    first_page_response = client.get(
        f"/api/v1/snapshots/{snapshot_id}/people",
        params={"limit": 2},
    )
    first_page = first_page_response.json()
    assert first_page_response.status_code == 200
    assert [person["tei_id"] for person in first_page["items"]] == ["p1", "p2"]
    assert first_page["items"][0]["surname"] == "Example"
    assert first_page["items"][0]["forenames"] == ["Anna"]
    assert first_page["items"][0]["source_member_name"] == "register.xml"
    assert first_page["items"][0]["source_record_locator"] == "xml:id=p1"
    assert first_page["items"][0]["alt_names"] == [
        "Earlier Annette",
        "A. Example",
    ]
    assert first_page["items"][0]["name_forms"] == [
        {
            "type": "reg",
            "subtype": None,
            "name": None,
            "surname": "Example",
            "forenames": ["Anna"],
        },
        {
            "type": "alt",
            "subtype": "birthname",
            "name": None,
            "surname": "Earlier",
            "forenames": ["Annette"],
        },
        {
            "type": "alt",
            "subtype": None,
            "name": "A. Example",
            "surname": None,
            "forenames": [],
        },
    ]
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]

    person_response = client.get(f"/api/v1/snapshots/{snapshot_id}/people/p1")
    assert person_response.status_code == 200
    assert person_response.json() == first_page["items"][0]
    missing_person_response = client.get(f"/api/v1/snapshots/{snapshot_id}/people/missing")
    assert missing_person_response.status_code == 404
    assert missing_person_response.json()["error"]["code"] == "resource_not_found"

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
    assert person.alt_names == ["Earlier Annette", "A. Example"]
    assert person.name_forms is not None
    assert [name_form.projected_text() for name_form in person.name_forms] == [
        "Example Anna",
        "Earlier Annette",
        "A. Example",
    ]
    assert artifact is not None


def test_invalid_tei_persists_failed_snapshot_without_source_disclosure(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    client, unit_of_work_factory = _client(
        postgres_engine=postgres_engine,
        artifact_root=tmp_path,
    )
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
    accepted = response.json()
    assert accepted["status"] == DatasetSnapshotStatus.pending.value
    assert accepted["failure_class"] is None
    assert accepted["failure_diagnostic"] is None

    snapshot_id = UUID(accepted["id"])
    _execute_snapshot_import(unit_of_work_factory, tmp_path, snapshot_id)
    failed = client.get(f"/api/v1/snapshots/{snapshot_id}").json()
    assert failed["status"] == DatasetSnapshotStatus.failed.value
    assert failed["failure_class"] == "TeiImportError"
    assert "DOCTYPE" in failed["failure_diagnostic"]
    assert "root:" not in failed["failure_diagnostic"]
