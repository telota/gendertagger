from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from unittest.mock import MagicMock, Mock, call
from uuid import UUID

import pytest
from pydantic import ValidationError

from gendertagger.models.artifact import Artifact
from gendertagger.models.export import (
    ExportDownload,
    ExportExecution,
    ExportFormat,
    ExportManifest,
    ExportManifestOutput,
    LabelSourcePolicy,
)
from gendertagger.models.lifecycle import ExportExecutionStatus
from gendertagger.services.exports import ExportService
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.artifact_storage import ArtifactStorage
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.ports.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
EXPORT_ID = UUID(int=1)
MANIFEST_ID = UUID(int=2)
RUN_ID = UUID(int=3)
AGGREGATION_ID = UUID(int=4)

ReadExport = Callable[[ExportService, UUID], ExportManifest | ExportDownload]


def _download_known_output(service: ExportService, export_execution_id: UUID) -> ExportDownload:
    return service.download_output(export_execution_id, "b" * 64)


def _artifact(artifact_id: UUID, *, sha256: str = "a" * 64) -> Artifact:
    return Artifact(
        id=artifact_id,
        logical_type="export_manifest" if artifact_id == MANIFEST_ID else "export_output",
        storage_uri=f"local:{artifact_id}",
        sha256=sha256,
        byte_size=100,
        media_type="application/json",
        export_execution_id=EXPORT_ID,
        created_at=NOW,
    )


def _manifest() -> ExportManifest:
    return ExportManifest(
        export_execution_id=EXPORT_ID,
        dataset_snapshot_id=UUID(int=5),
        source_snapshot_sha256="c" * 64,
        run_id=RUN_ID,
        aggregation_execution_id=AGGREGATION_ID,
        format=ExportFormat.json,
        label_source_policy=LabelSourcePolicy.human_overrides,
        outputs=(
            ExportManifestOutput(
                logical_name="retained-results.json",
                sha256="b" * 64,
                byte_size=42,
                media_type="application/json",
            ),
        ),
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _multi_output_manifest() -> ExportManifest:
    return _manifest().model_copy(
        update={
            "outputs": (
                ExportManifestOutput(
                    logical_name="member-one.xml",
                    sha256="b" * 64,
                    byte_size=10,
                    media_type="application/tei+xml",
                ),
                ExportManifestOutput(
                    logical_name="member-two.xml",
                    sha256="c" * 64,
                    byte_size=20,
                    media_type="application/tei+xml",
                ),
            )
        }
    )


@pytest.fixture
def export_service() -> tuple[ExportService, MagicMock, Mock]:
    unit_of_work = MagicMock(spec=UnitOfWork)
    unit_of_work.__enter__.return_value = unit_of_work
    unit_of_work.exports.get_export.return_value = ExportExecution(
        id=EXPORT_ID,
        run_id=RUN_ID,
        aggregation_execution_id=AGGREGATION_ID,
        format=ExportFormat.json,
        status=ExportExecutionStatus.completed,
        manifest_artifact_id=MANIFEST_ID,
        started_at=NOW,
        finished_at=NOW,
        created_at=NOW,
    )
    unit_of_work.artifacts.get_artifact.return_value = _artifact(MANIFEST_ID)
    storage = Mock(spec=ArtifactStorage)
    service = ExportService(
        unit_of_work_factory=lambda: unit_of_work,
        artifact_storage=storage,
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
    )
    return service, unit_of_work, storage


@pytest.mark.parametrize(
    "read", [ExportService.get_manifest, ExportService.download_export, _download_known_output]
)
def test_export_read_missing_execution_raises_not_found(
    export_service: tuple[ExportService, MagicMock, Mock], read: ReadExport
) -> None:
    service, unit_of_work, storage = export_service
    unit_of_work.exports.get_export.return_value = None

    with pytest.raises(ResourceNotFoundError, match=r"export execution .* does not exist"):
        read(service, EXPORT_ID)

    storage.open.assert_not_called()


@pytest.mark.parametrize(
    "read", [ExportService.get_manifest, ExportService.download_export, _download_known_output]
)
def test_export_read_without_manifest_raises_not_found(
    export_service: tuple[ExportService, MagicMock, Mock], read: ReadExport
) -> None:
    service, unit_of_work, storage = export_service
    unit_of_work.exports.get_export.return_value = ExportExecution(
        id=EXPORT_ID,
        run_id=RUN_ID,
        aggregation_execution_id=AGGREGATION_ID,
        format=ExportFormat.json,
        status=ExportExecutionStatus.queued,
        created_at=NOW,
    )

    with pytest.raises(ResourceNotFoundError, match="has no output artifacts"):
        read(service, EXPORT_ID)

    storage.open.assert_not_called()


@pytest.mark.parametrize(
    "read", [ExportService.get_manifest, ExportService.download_export, _download_known_output]
)
def test_export_read_missing_manifest_artifact_raises_not_found(
    export_service: tuple[ExportService, MagicMock, Mock], read: ReadExport
) -> None:
    service, unit_of_work, storage = export_service
    unit_of_work.artifacts.get_artifact.return_value = None

    with pytest.raises(ResourceNotFoundError, match=r"artifact .* does not exist"):
        read(service, EXPORT_ID)

    unit_of_work.artifacts.get_artifact.assert_called_once_with(MANIFEST_ID)
    storage.open.assert_not_called()


def test_get_manifest_returns_persisted_provenance_without_reconstruction(
    export_service: tuple[ExportService, MagicMock, Mock],
) -> None:
    service, unit_of_work, storage = export_service
    persisted = _manifest()
    storage.open.return_value = BytesIO(persisted.model_dump_json().encode())

    assert service.get_manifest(EXPORT_ID) == persisted

    storage.open.assert_called_once_with(f"local:{MANIFEST_ID}")
    unit_of_work.artifacts.list_artifacts_by_export.assert_not_called()
    unit_of_work.exports.load_export_inputs.assert_not_called()
    unit_of_work.commit.assert_not_called()


@pytest.mark.parametrize("content", [b"not json", b'{"version": 2}'])
def test_get_manifest_rejects_invalid_persisted_contract(
    export_service: tuple[ExportService, MagicMock, Mock], content: bytes
) -> None:
    service, _, storage = export_service
    storage.open.return_value = BytesIO(content)

    with pytest.raises(ValidationError):
        service.get_manifest(EXPORT_ID)


def test_download_returns_persisted_metadata_even_when_bytes_have_changed(
    export_service: tuple[ExportService, MagicMock, Mock],
) -> None:
    service, unit_of_work, storage = export_service
    output = _artifact(UUID(int=6))
    manifest = unit_of_work.artifacts.get_artifact.return_value
    unit_of_work.artifacts.list_artifacts_by_export.return_value = [manifest, output]
    changed_content = b"changed after export creation"
    storage.open.side_effect = [
        BytesIO(_manifest().model_dump_json().encode()),
        BytesIO(changed_content),
    ]

    download = service.download_export(EXPORT_ID)

    assert download == ExportDownload(
        content=changed_content,
        logical_name="retained-results.json",
        sha256=output.sha256,
        media_type=output.media_type,
    )
    assert download.sha256 != sha256(changed_content).hexdigest()
    assert storage.open.call_args_list == [
        call(manifest.storage_uri),
        call(output.storage_uri),
    ]


def test_download_multiple_outputs_returns_manifest_bytes_and_metadata(
    export_service: tuple[ExportService, MagicMock, Mock],
) -> None:
    service, unit_of_work, storage = export_service
    manifest = unit_of_work.artifacts.get_artifact.return_value
    unit_of_work.artifacts.list_artifacts_by_export.return_value = [
        manifest,
        _artifact(UUID(int=6)),
        _artifact(UUID(int=7)),
    ]
    persisted_content = b'{ "persisted": "manifest bytes" }'
    storage.open.return_value = BytesIO(persisted_content)

    download = service.download_export(EXPORT_ID)

    assert download == ExportDownload(
        content=persisted_content,
        logical_name="manifest.json",
        sha256=manifest.sha256,
        media_type=manifest.media_type,
    )
    storage.open.assert_called_once_with(manifest.storage_uri)


def test_download_output_returns_the_requested_member_by_checksum(
    export_service: tuple[ExportService, MagicMock, Mock],
) -> None:
    service, unit_of_work, storage = export_service
    manifest = unit_of_work.artifacts.get_artifact.return_value
    first = _artifact(UUID(int=6), sha256="b" * 64)
    second = _artifact(UUID(int=7), sha256="c" * 64)
    unit_of_work.artifacts.list_artifacts_by_export.return_value = [manifest, first, second]
    second_content = b"<TEI>member two</TEI>"
    storage.open.side_effect = [
        BytesIO(_multi_output_manifest().model_dump_json().encode()),
        BytesIO(second_content),
    ]

    download = service.download_output(EXPORT_ID, "c" * 64)

    assert download == ExportDownload(
        content=second_content,
        logical_name="member-two.xml",
        sha256=second.sha256,
        media_type=second.media_type,
    )
    assert storage.open.call_args_list == [call(manifest.storage_uri), call(second.storage_uri)]


def test_download_output_rejects_a_checksum_the_manifest_never_listed(
    export_service: tuple[ExportService, MagicMock, Mock],
) -> None:
    service, unit_of_work, storage = export_service
    storage.open.return_value = BytesIO(_multi_output_manifest().model_dump_json().encode())

    with pytest.raises(ResourceNotFoundError, match="no output with checksum"):
        service.download_output(EXPORT_ID, "d" * 64)

    unit_of_work.artifacts.list_artifacts_by_export.assert_not_called()


def test_download_output_rejects_a_listed_checksum_with_no_matching_artifact(
    export_service: tuple[ExportService, MagicMock, Mock],
) -> None:
    service, unit_of_work, storage = export_service
    manifest = unit_of_work.artifacts.get_artifact.return_value
    unit_of_work.artifacts.list_artifacts_by_export.return_value = [manifest]
    storage.open.return_value = BytesIO(_multi_output_manifest().model_dump_json().encode())

    with pytest.raises(ResourceNotFoundError, match="no output with checksum"):
        service.download_output(EXPORT_ID, "b" * 64)
