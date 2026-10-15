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
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.export import (
    ExportExecutionCreate,
    ExportFormat,
    ExportManifest,
    ExportManifestOutput,
    ExportTaskMessage,
)
from gendertagger.models.lifecycle import DatasetSnapshotStatus, ExportExecutionStatus
from gendertagger.models.project import (
    SnapshotImportRequest,
    SnapshotImportTaskMessage,
    SourceFormat,
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
    *,
    json_identifier: str | None = None,
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
            source_format=SourceFormat.json if json_identifier is not None else SourceFormat.tei,
            packaging=SourcePackaging.single if len(source_names) == 1 else SourcePackaging.loose,
        ),
        sources=[
            SnapshotUpload(
                filename=source_name,
                source=BytesIO(
                    (
                        json.dumps(
                            [
                                {
                                    "xml:id": json_identifier,
                                    "persName": [{"type": "reg", "name": "Example"}],
                                    "birth": None,
                                    "death": None,
                                    "event": [],
                                    "note": None,
                                    "idno": [],
                                }
                            ]
                        )
                        if json_identifier is not None
                        else (
                            '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>'
                            f'<person xml:id="p{index}"><persName type="reg">'
                            "<surname>Example</surname></persName></person>"
                            "</listPerson></body></text></TEI>"
                        )
                    ).encode("utf-8")
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
        output_artifacts_by_sha = {
            artifact.sha256: artifact
            for artifact in artifacts
            if artifact.id != manifest_artifact.id
        }
        for output in manifest.outputs:
            member_response = client.get(
                f"/api/v1/exports/{export_execution_id}/download/{output.sha256}"
            )
            assert member_response.status_code == 200
            assert member_response.headers["x-checksum-sha256"] == output.sha256
            assert (
                member_response.headers["content-disposition"]
                == f'attachment; filename="{output.logical_name}"'
            )
            with storage.open(output_artifacts_by_sha[output.sha256].storage_uri) as source:
                assert member_response.content == source.read()
        missing_output_response = client.get(
            f"/api/v1/exports/{export_execution_id}/download/{'f' * 64}"
        )
        assert missing_output_response.status_code == 404

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


def test_csv_download_preserves_legacy_bytes_while_new_exports_protect_identifiers(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    unit_of_work_factory, _session_factory = _unit_of_work_factory(postgres_engine)
    storage = LocalArtifactStorage(tmp_path)
    identifier = '=1+1,"source"\r\nnext'
    user_id, _viewer_id, run_id, aggregation_id = _seed_completed_aggregation(
        unit_of_work_factory, storage, ("source.json",), json_identifier=identifier
    )
    legacy_buffer = StringIO()
    legacy_writer = csv.writer(legacy_buffer, lineterminator="\n")
    legacy_writer.writerow(
        [
            "tei_id",
            "label",
            "evidence",
            "resp",
            "cert",
            "agreement_tier",
            "certainty_tier",
            "human_reviewed",
        ]
    )
    legacy_writer.writerow(
        [identifier, "male", "assigned", "#gendertagger", "high", "unanimous", "high", "false"]
    )
    legacy_content = legacy_buffer.getvalue().encode("utf-8")
    with unit_of_work_factory() as unit_of_work:
        legacy_export = unit_of_work.exports.add_export(
            ExportExecutionCreate(
                run_id=run_id,
                aggregation_execution_id=aggregation_id,
                format=ExportFormat.csv,
            )
        )
        unit_of_work.exports.claim_export(legacy_export.id, started_at=NOW)
        inputs = unit_of_work.exports.load_export_inputs(legacy_export.id)
        stored = storage.store(BytesIO(legacy_content), max_byte_size=1_000_000)
        output = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="export_output_csv",
                storage_uri=stored.storage_uri,
                sha256=stored.sha256,
                byte_size=stored.byte_size,
                media_type="text/csv",
                run_id=run_id,
                export_execution_id=legacy_export.id,
            )
        )
        legacy_manifest = ExportManifest(
            export_execution_id=legacy_export.id,
            dataset_snapshot_id=inputs.dataset_snapshot_id,
            source_snapshot_sha256=inputs.source_snapshot_sha256,
            run_id=run_id,
            aggregation_execution_id=aggregation_id,
            format=ExportFormat.csv,
            label_source_policy=legacy_export.label_source_policy,
            generated_at=NOW,
            outputs=(
                ExportManifestOutput(
                    logical_name="export.csv",
                    sha256=output.sha256,
                    byte_size=output.byte_size,
                    media_type=output.media_type,
                ),
            ),
        )
        manifest_bytes = legacy_manifest.model_dump_json().encode("utf-8")
        stored_manifest = storage.store(BytesIO(manifest_bytes), max_byte_size=1_000_000)
        manifest_artifact = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="export_manifest",
                storage_uri=stored_manifest.storage_uri,
                sha256=stored_manifest.sha256,
                byte_size=stored_manifest.byte_size,
                media_type="application/json",
                run_id=run_id,
                export_execution_id=legacy_export.id,
            )
        )
        unit_of_work.exports.mark_export_finished(
            legacy_export.id,
            status=ExportExecutionStatus.completed,
            finished_at=NOW,
            manifest_artifact_id=manifest_artifact.id,
        )
        unit_of_work.commit()
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
    executor = ExportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        max_output_bytes=1_000_000,
        clock=lambda: NOW,
    )
    for export_format in ("csv", "json"):
        response = client.post(
            "/api/v1/exports",
            json={
                "run_id": str(run_id),
                "aggregation_execution_id": str(aggregation_id),
                "format": export_format,
            },
        )
        assert response.status_code == 202
        execution_id = UUID(response.json()["id"])
        completed = executor.execute(
            ExportTaskMessage(export_execution_id=execution_id), attempt_count=1
        )
        assert completed.status is ExportExecutionStatus.completed
        download = client.get(f"/api/v1/exports/{execution_id}/download")
        assert download.status_code == 200
        if export_format == "csv":
            row = next(csv.DictReader(StringIO(download.text)))
            assert row["tei_id"] == "'" + identifier
            manifest_response = client.get(f"/api/v1/exports/{execution_id}/manifest")
            assert manifest_response.status_code == 200
            descriptor = manifest_response.json()["outputs"][0]
            assert descriptor["sha256"] == hashlib.sha256(download.content).hexdigest()
            assert descriptor["byte_size"] == len(download.content)
        else:
            assert download.json()[0]["tei_id"] == identifier

    retained = executor.execute(
        ExportTaskMessage(export_execution_id=legacy_export.id), attempt_count=2
    )
    assert retained.manifest_artifact_id == manifest_artifact.id
    legacy_download = client.get(f"/api/v1/exports/{legacy_export.id}/download")
    assert legacy_download.status_code == 200
    assert legacy_download.content == legacy_content
    assert legacy_download.headers["x-checksum-sha256"] == output.sha256
    legacy_manifest_response = client.get(f"/api/v1/exports/{legacy_export.id}/manifest")
    assert legacy_manifest_response.status_code == 200
    assert legacy_manifest_response.json() == json.loads(manifest_bytes)
