from datetime import UTC, datetime
from io import BytesIO
from typing import cast
from uuid import UUID

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.datastructures import Headers

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user
from gendertagger.api.authorization import ProjectAccessGuard
from gendertagger.api.dependencies import get_project_access_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.api.projects import import_snapshot
from gendertagger.api.settings import AppSettings
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.project import (
    DatasetSnapshot,
    SnapshotImportRequest,
    SourceFormat,
    SourcePackaging,
)
from gendertagger.models.user import CurrentUser, ProjectRole
from gendertagger.services.project_access import ProjectAccessService
from gendertagger.services.project_access_repository import ProjectScope
from gendertagger.services.projects import (
    InvalidSnapshotSourceError,
    ProjectService,
    SnapshotUpload,
    SnapshotUploadTooLargeError,
)
from gendertagger.services.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)


class _CapturingProjectService:
    def __init__(self) -> None:
        self.calls: list[tuple[SnapshotImportRequest, list[tuple[str, bytes]]]] = []
        self.error: Exception | None = None

    def import_snapshot(
        self,
        *,
        project_id: UUID,
        command: SnapshotImportRequest,
        sources: list[SnapshotUpload],
    ) -> DatasetSnapshot:
        assert project_id == PROJECT_ID
        if self.error is not None:
            raise self.error
        captured = [(upload.filename, upload.source.read()) for upload in sources]
        self.calls.append((command, captured))
        return DatasetSnapshot(
            id=SNAPSHOT_ID,
            project_id=PROJECT_ID,
            source_artifact_id=ARTIFACT_ID,
            source_sha256="a" * 64,
            parser_version="pending_importer_v1",
            import_config=command.model_dump(mode="json"),
            status=DatasetSnapshotStatus.pending,
            created_at=NOW,
        )


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("OpenAPI generation must not open persistence")


def _operator() -> CurrentUser:
    return CurrentUser(
        id=UUID("a2f03480-77a7-4f24-82cb-07604d5c2483"),
        display_name="Snapshot operator",
        roles=set(),
    )


class _GrantingProjectAccess:
    """Grant the caller operator in every project without persistence."""

    def effective_role(
        self, user: CurrentUser, scope: ProjectScope, resource_id: UUID
    ) -> ProjectRole:
        return ProjectRole.operator

    def has_any_grant(self, user: CurrentUser) -> bool:
        return True


def _upload(filename: str, content: bytes, media_type: str) -> UploadFile:
    return UploadFile(
        BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": media_type}),
    )


def _call_import(
    service: _CapturingProjectService,
    uploads: list[UploadFile],
    *,
    source_format: SourceFormat = SourceFormat.tei,
    packaging: SourcePackaging = SourcePackaging.single,
) -> DatasetSnapshot:
    return import_snapshot(
        project_id=PROJECT_ID,
        source=uploads,
        service=cast(ProjectService, service),
        access=ProjectAccessGuard(
            user=_operator(),
            service=cast(ProjectAccessService, _GrantingProjectAccess()),
        ),
        source_format=source_format,
        packaging=packaging,
    )


def test_single_source_defaults_to_tei_without_a_public_profile_option() -> None:
    service = _CapturingProjectService()

    snapshot = _call_import(
        service,
        [_upload("register.xml", b"<TEI/>", "application/tei+xml")],
    )

    assert snapshot.status is DatasetSnapshotStatus.pending
    [(command, sources)] = service.calls
    assert command.model_dump(mode="json") == {
        "source_format": "tei",
        "packaging": "single",
    }
    assert sources == [("register.xml", b"<TEI/>")]


def test_repeated_loose_tei_parts_preserve_all_filenames() -> None:
    service = _CapturingProjectService()

    _call_import(
        service,
        [
            _upload("B.xml", b"<TEI>B</TEI>", "application/tei+xml"),
            _upload("A.xml", b"<TEI>A</TEI>", "application/tei+xml"),
        ],
        packaging=SourcePackaging.loose,
    )

    [(command, sources)] = service.calls
    assert command.packaging is SourcePackaging.loose
    assert sources == [
        ("B.xml", b"<TEI>B</TEI>"),
        ("A.xml", b"<TEI>A</TEI>"),
    ]


@pytest.mark.parametrize(
    ("source_format", "filename", "media_type"),
    [
        (SourceFormat.csv, "people.csv", "text/csv"),
        (SourceFormat.xlsx, "people.xlsx", "application/octet-stream"),
        (SourceFormat.json, "people.json", "application/json"),
    ],
)
def test_tabular_formats_are_selected_by_source_format(
    source_format: SourceFormat,
    filename: str,
    media_type: str,
) -> None:
    service = _CapturingProjectService()

    _call_import(
        service,
        [_upload(filename, b"source", media_type)],
        source_format=source_format,
    )

    assert service.calls[0][0].source_format is source_format


def test_incompatible_format_and_packaging_returns_422() -> None:
    service = _CapturingProjectService()

    with pytest.raises(ApiRequestError) as caught:
        _call_import(
            service,
            [_upload("source.bin", b"source", "application/octet-stream")],
            source_format=SourceFormat.json,
            packaging=SourcePackaging.loose,
        )

    assert caught.value.status_code == 422
    assert caught.value.code == "validation_error"
    assert caught.value.details == {"reason": "incompatible_import_options"}
    assert service.calls == []


def test_source_acceptance_validation_maps_to_422() -> None:
    service = _CapturingProjectService()
    service.error = InvalidSnapshotSourceError(
        "source member logical names collide after normalization"
    )

    with pytest.raises(ApiRequestError) as caught:
        _call_import(
            service,
            [
                _upload("A.xml", b"one", "application/tei+xml"),
                _upload("a.XML", b"two", "application/tei+xml"),
            ],
            packaging=SourcePackaging.loose,
        )

    assert caught.value.status_code == 422
    assert caught.value.code == "validation_error"
    assert "collide" in caught.value.message


def test_aggregate_upload_overflow_maps_to_413() -> None:
    service = _CapturingProjectService()
    service.error = SnapshotUploadTooLargeError(
        "source collection exceeds the aggregate upload limit"
    )

    with pytest.raises(ApiRequestError) as caught:
        _call_import(
            service,
            [_upload("register.xml", b"source", "application/tei+xml")],
        )

    assert caught.value.status_code == 413
    assert caught.value.code == "payload_too_large"
    assert "aggregate upload limit" in caught.value.message


def test_openapi_describes_repeated_sources_and_strict_options() -> None:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )

    schema = application.openapi()
    operation = schema["paths"]["/api/v1/projects/{project_id}/snapshots"]["post"]
    request_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    body_name = request_schema["$ref"].removeprefix("#/components/schemas/")
    body_schema = schema["components"]["schemas"][body_name]

    assert "202" in operation["responses"]
    assert body_schema["properties"]["source"]["type"] == "array"
    assert body_schema["properties"]["source"]["items"] == {
        "contentMediaType": "application/octet-stream",
        "type": "string",
    }
    assert schema["components"]["schemas"]["SourceFormat"]["enum"] == [
        "tei",
        "csv",
        "xlsx",
        "json",
    ]
    assert schema["components"]["schemas"]["SourcePackaging"]["enum"] == [
        "single",
        "loose",
        "zip",
        "tar_gz",
    ]


def test_upload_limits_report_the_configured_bounds_the_import_enforces() -> None:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
            max_snapshot_upload_bytes=4096,
            max_snapshot_source_files=7,
            max_archive_member_bytes=1024,
            max_archive_expanded_bytes=8192,
            max_archive_compression_ratio=12.5,
            max_import_record_count=300,
            max_tabular_cell_bytes=256,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    application.dependency_overrides[require_authenticated_user] = _operator
    application.dependency_overrides[get_project_access_service] = _GrantingProjectAccess

    response = TestClient(application).get("/api/v1/snapshot-upload-limits")

    assert response.status_code == 200
    assert response.json() == {
        "max_upload_part_bytes": 1024,
        "max_total_upload_bytes": 4096,
        "import_limits": {
            "max_member_count": 7,
            "max_member_expanded_bytes": 1024,
            "max_total_expanded_bytes": 8192,
            "max_compression_ratio": 12.5,
            "max_record_count": 300,
            "max_cell_bytes": 256,
        },
    }
