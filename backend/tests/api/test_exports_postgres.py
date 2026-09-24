import csv
import hashlib
import json
from datetime import UTC, datetime
from io import BytesIO, StringIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from lxml import etree
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from tests.seeding import (
    only_method_answers,
    seed_completed_aggregation,
    seed_completed_run,
    seed_member,
    seed_project,
)

from gendertagger.api.app import create_app
from gendertagger.api.authentication import AuthenticationBackend
from gendertagger.api.settings import AppSettings
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.export import ExportFormat, ExportManifest, ExportTaskMessage
from gendertagger.models.lifecycle import DatasetSnapshotStatus, ExportExecutionStatus
from gendertagger.models.project import (
    SnapshotImportRequest,
    SnapshotImportTaskMessage,
    SourcePackaging,
)
from gendertagger.models.user import ProjectRole, UserCreate
from gendertagger.services.export_execution import ExportExecutor
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from gendertagger.services.projects import ProjectService, SnapshotUpload
from gendertagger.services.snapshot_import import SnapshotImportExecutor
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
    storage: LocalArtifactStorage,
    source_names: tuple[str, ...],
) -> tuple[UUID, UUID, UUID, UUID]:
    with unit_of_work_factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="export")
        user = seed_member(unit_of_work, project.id, display_name="Export operator")
        viewer = seed_member(
            unit_of_work, project.id, role=ProjectRole.viewer, display_name="Export viewer"
        )
        unit_of_work.commit()
    snapshot = ProjectService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        parser=TeiPersonParser(),
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
        max_upload_bytes=1_000_000,
    ).import_snapshot(
        project_id=project.id,
        command=SnapshotImportRequest(
            packaging=SourcePackaging.single if len(source_names) == 1 else SourcePackaging.loose,
        ),
        sources=[
            SnapshotUpload(
                filename=source_name,
                source=BytesIO(
                    (
                        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>'
                        f'<person xml:id="p{index}"><persName type="reg">'
                        "<surname>Example</surname></persName></person>"
                        "</listPerson></body></text></TEI>"
                    ).encode(),
                ),
            )
            for index, source_name in enumerate(source_names, start=1)
        ],
    )
    snapshot = SnapshotImportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        parser=TeiPersonParser(),
        clock=lambda: NOW,
        import_batch_record_count=10,
    ).execute(SnapshotImportTaskMessage(dataset_snapshot_id=snapshot.id), attempt_count=1)
    assert snapshot.status is DatasetSnapshotStatus.ready
    with unit_of_work_factory() as unit_of_work:
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
    return user.id, viewer.id, completed.run.id, aggregation.id


def _outsider_id(unit_of_work_factory: UnitOfWorkFactory) -> UUID:
    with unit_of_work_factory() as unit_of_work:
        outsider = unit_of_work.users.add_user(UserCreate(display_name="Other project member"))
        unit_of_work.commit()
    return outsider.id


@pytest.mark.parametrize(
    ("export_format", "source_names", "media_type", "content_disposition"),
    [
        ("json", ("source.xml",), "application/json", 'attachment; filename="export.json"'),
        ("csv", ("source.xml",), "text/csv", 'attachment; filename="export.csv"'),
        ("tei", ("source.xml",), "application/tei+xml", 'attachment; filename="source.xml"'),
        (
            "tei",
            ("collection/Überblick.xml",),
            "application/tei+xml",
            "attachment; filename*=UTF-8''%C3%9Cberblick.xml",
        ),
        (
            "tei",
            ("first.xml", "second.xml"),
            "application/json",
            'attachment; filename="manifest.json"',
        ),
    ],
    ids=("json", "csv", "single-tei", "unicode-tei", "multiple-tei"),
)
def test_queued_export_executes_and_output_round_trips_through_http(
    postgres_engine: Engine,
    tmp_path: Path,
    export_format: str,
    source_names: tuple[str, ...],
    media_type: str,
    content_disposition: str,
) -> None:
    unit_of_work_factory, _session_factory = _unit_of_work_factory(postgres_engine)
    storage = LocalArtifactStorage(tmp_path)
    user_id, viewer_id, run_id, aggregation_id = _seed_completed_aggregation(
        unit_of_work_factory, storage, source_names
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
        "/api/v1/exports",
        json={
            "run_id": str(run_id),
            "aggregation_execution_id": str(aggregation_id),
            "format": export_format,
        },
    )

    assert create_response.status_code == 202
    export_body = create_response.json()
    assert export_body["status"] == ExportExecutionStatus.queued.value
    assert export_body["run_id"] == str(run_id)
    assert export_body["format"] == export_format
    export_execution_id = UUID(export_body["id"])
    assert client.get(f"/api/v1/exports/{export_execution_id}").json() == export_body
    assert client.get(f"/api/v1/exports/{export_execution_id}/manifest").status_code == 404
    assert client.get(f"/api/v1/exports/{export_execution_id}/download").status_code == 404

    completed = ExportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        max_output_bytes=1_000_000,
        clock=lambda: NOW,
    ).execute(
        ExportTaskMessage(export_execution_id=export_execution_id),
        attempt_count=1,
    )
    assert completed.status is ExportExecutionStatus.completed
    assert completed.manifest_artifact_id is not None

    application.state.authentication_backend = StaticAuthenticationBackend(viewer_id)
    manifest_response = client.get(f"/api/v1/exports/{export_execution_id}/manifest")
    assert manifest_response.status_code == 200
    manifest = ExportManifest.model_validate(manifest_response.json())
    assert manifest.export_execution_id == export_execution_id
    assert manifest.run_id == run_id
    assert manifest.aggregation_execution_id == aggregation_id
    assert manifest.format is ExportFormat(export_format)
    assert len(manifest.outputs) == len(source_names)
    with unit_of_work_factory() as unit_of_work:
        manifest_artifact = unit_of_work.artifacts.get_artifact(completed.manifest_artifact_id)
        artifacts = unit_of_work.artifacts.list_artifacts_by_export(export_execution_id)
    assert manifest_artifact is not None
    with storage.open(manifest_artifact.storage_uri) as source:
        manifest_bytes = source.read()
    assert manifest_response.json() == json.loads(manifest_bytes)

    download_response = client.get(f"/api/v1/exports/{export_execution_id}/download")
    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith(media_type)
    assert download_response.headers["content-disposition"] == content_disposition
    checksum = hashlib.sha256(download_response.content).hexdigest()
    assert download_response.headers["x-checksum-sha256"] == checksum
    if len(manifest.outputs) == 1:
        output = manifest.outputs[0]
        assert output.sha256 == checksum
        assert output.byte_size == len(download_response.content)
        assert output.media_type == media_type
        expected_name = source_names[0] if export_format == "tei" else f"export.{export_format}"
        assert output.logical_name == expected_name
        output_artifact = next(
            artifact for artifact in artifacts if artifact.id != manifest_artifact.id
        )
        assert output_artifact.sha256 == checksum
        with storage.open(output_artifact.storage_uri) as source:
            assert download_response.content == source.read()
        if export_format == "json":
            records = download_response.json()
            assert len(records) == 1
            assert records[0]["label"] == "male"
        elif export_format == "csv":
            rows = list(csv.DictReader(StringIO(download_response.text)))
            assert len(rows) == 1
            assert rows[0]["label"] == "male"
        else:
            gender = etree.fromstring(download_response.content).find(
                ".//{http://www.tei-c.org/ns/1.0}gender"
            )
            assert gender is not None
            assert gender.get("value") == "male"
    else:
        assert download_response.content == manifest_bytes
        assert checksum == manifest_artifact.sha256
        assert tuple(output.logical_name for output in manifest.outputs) == source_names

    missing_download_response = client.get(f"/api/v1/exports/{uuid4()}/download")
    assert missing_download_response.status_code == 404
    assert client.get(f"/api/v1/exports/{uuid4()}/manifest").status_code == 404

    application.state.authentication_backend = StaticAuthenticationBackend(user_id)
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
        (str(export_execution_id), export_format, ExportExecutionStatus.completed.value),
    ]
    assert client.get(f"/api/v1/runs/{uuid4()}/exports").status_code == 404

    application.state.authentication_backend = StaticAuthenticationBackend(
        _outsider_id(unit_of_work_factory)
    )
    hidden_responses = [
        client.get(f"/api/v1/exports/{export_execution_id}"),
        client.get(f"/api/v1/exports/{export_execution_id}/download"),
        client.get(f"/api/v1/exports/{export_execution_id}/manifest"),
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
    assert [response.status_code for response in hidden_responses] == [404, 404, 404, 404, 404]
