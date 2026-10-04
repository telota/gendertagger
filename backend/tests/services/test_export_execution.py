from datetime import UTC, datetime
from io import BytesIO
from types import TracebackType
from typing import BinaryIO, Self, cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.export.tei_profile import TeiExportError
from gendertagger.models.artifact import Artifact
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.export import (
    ExportExecution,
    ExportExecutionCreate,
    ExportFormat,
    ExportInputs,
    ExportPersonRecord,
    ExportSourceMember,
    ExportTaskMessage,
    TeiExportProfile,
)
from gendertagger.models.lifecycle import ExportExecutionStatus
from gendertagger.models.project import SourceFormat, SourcePackaging
from gendertagger.services.export_execution import (
    ExportExecutor,
    TransientExportError,
)
from gendertagger.services.ports.artifact_storage import ArtifactStorage, StoredArtifact
from gendertagger.services.ports.export_repository import ExportRepository
from gendertagger.services.ports.persistence_errors import InvalidResourceStateError
from gendertagger.services.ports.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
EXPORT_ID = UUID("20000000-0000-0000-0000-000000000001")
AGGREGATION_ID = UUID("40000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("30000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("50000000-0000-0000-0000-000000000001")


class _StubUnitOfWork:
    def __init__(self, exports: ExportRepository, artifacts: Mock) -> None:
        self._exports = exports
        self._artifacts = artifacts
        self.commit_count = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    @property
    def exports(self) -> ExportRepository:
        return self._exports

    @property
    def artifacts(self) -> Mock:
        return self._artifacts

    def commit(self) -> None:
        self.commit_count += 1


class _UnitOfWorkFactory:
    def __init__(self, exports: ExportRepository, artifacts: Mock) -> None:
        self._exports = exports
        self._artifacts = artifacts
        self.units: list[_StubUnitOfWork] = []

    def __call__(self) -> UnitOfWork:
        unit_of_work = _StubUnitOfWork(self._exports, self._artifacts)
        self.units.append(unit_of_work)
        return cast(UnitOfWork, unit_of_work)


class _StubArtifactStorage:
    def __init__(self, *, sources: dict[str, bytes] | None = None) -> None:
        self.stored: list[bytes] = []
        self._sources = sources or {}
        self.opened: list[str] = []

    def store(self, source: BinaryIO, *, max_byte_size: int) -> StoredArtifact:
        content = source.read()
        assert len(content) <= max_byte_size
        self.stored.append(content)
        return StoredArtifact(storage_uri="local:test", sha256="a" * 64, byte_size=len(content))

    def open(self, storage_uri: str) -> BinaryIO:
        self.opened.append(storage_uri)
        return BytesIO(self._sources[storage_uri])

    def materialize(self, storage_uri: str) -> object:  # pragma: no cover - unused here
        raise NotImplementedError


def _export(
    status: ExportExecutionStatus,
    *,
    export_format: ExportFormat = ExportFormat.json,
) -> ExportExecution:
    command = ExportExecutionCreate(
        run_id=RUN_ID,
        aggregation_execution_id=AGGREGATION_ID,
        format=export_format,
        tei_profile=(
            TeiExportProfile.tei_p5_gender_v1 if export_format is ExportFormat.tei else None
        ),
    )
    started_at = NOW if status is not ExportExecutionStatus.pending else None
    finished_at = (
        NOW if status in {ExportExecutionStatus.completed, ExportExecutionStatus.failed} else None
    )
    return ExportExecution(
        id=EXPORT_ID,
        status=status,
        manifest_artifact_id=(ARTIFACT_ID if status is ExportExecutionStatus.completed else None),
        started_at=started_at,
        finished_at=finished_at,
        failure_class="InvalidResourceStateError"
        if status is ExportExecutionStatus.failed
        else None,
        failure_diagnostic=("missing evidence" if status is ExportExecutionStatus.failed else None),
        created_at=NOW,
        **command.model_dump(),
    )


def _complete_inputs() -> ExportInputs:
    return ExportInputs(
        dataset_snapshot_id=UUID(int=9),
        source_snapshot_sha256="e" * 64,
        source_format=SourceFormat.tei,
        packaging=SourcePackaging.single,
        records=(
            ExportPersonRecord(
                tei_id="p1",
                person_record_id=PERSON_ID,
                label=CanonicalLabel.male,
                evidence="assigned",
                resp="#gendertagger",
                cert="high",
                agreement_tier=AgreementTier.unanimous,
                certainty_tier=CertaintyTier.high,
                is_human_reviewed=False,
            ),
        ),
    )


def _executor(
    repository: ExportRepository,
    artifact_storage: ArtifactStorage,
    artifacts: Mock,
) -> tuple[ExportExecutor, _UnitOfWorkFactory]:
    factory = _UnitOfWorkFactory(repository, artifacts)
    executor = ExportExecutor(
        unit_of_work_factory=factory,
        artifact_storage=artifact_storage,
        max_output_bytes=1_000_000,
        clock=lambda: NOW,
    )
    return executor, factory


def test_executor_persists_a_manifest_artifact_and_completes() -> None:
    repository = Mock(spec=ExportRepository)
    repository.claim_export.return_value = _export(ExportExecutionStatus.running)
    repository.load_export_inputs.return_value = _complete_inputs()
    repository.mark_export_finished.return_value = _export(ExportExecutionStatus.completed)
    artifacts = Mock()
    artifacts.add_artifact.return_value = Artifact(
        id=ARTIFACT_ID,
        logical_type="export_manifest",
        storage_uri="local:test",
        sha256="a" * 64,
        byte_size=10,
        media_type="application/json",
        created_at=NOW,
    )
    storage = _StubArtifactStorage()
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)

    result = executor.execute(
        ExportTaskMessage(export_execution_id=EXPORT_ID),
        attempt_count=1,
    )

    assert result.status is ExportExecutionStatus.completed
    assert len(storage.stored) == 2
    finish_kwargs = repository.mark_export_finished.call_args.kwargs
    assert finish_kwargs["manifest_artifact_id"] == ARTIFACT_ID
    assert factory.units[0].commit_count == 1


def test_executor_fails_terminally_when_export_inputs_are_invalid() -> None:
    repository = Mock(spec=ExportRepository)
    repository.claim_export.return_value = _export(ExportExecutionStatus.running)
    repository.load_export_inputs.side_effect = InvalidResourceStateError(
        "1 person record(s) have no source-member locator and cannot be exported as TEI: p1"
    )
    repository.mark_export_finished.return_value = _export(ExportExecutionStatus.failed)
    artifacts = Mock()
    storage = _StubArtifactStorage()
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)

    result = executor.execute(
        ExportTaskMessage(export_execution_id=EXPORT_ID),
        attempt_count=1,
    )

    assert result.status is ExportExecutionStatus.failed
    artifacts.add_artifact.assert_not_called()
    finish_kwargs = repository.mark_export_finished.call_args.kwargs
    assert finish_kwargs["failure_class"] == "InvalidResourceStateError"
    assert "cannot be exported as TEI" in finish_kwargs["failure_diagnostic"]
    assert finish_kwargs.get("manifest_artifact_id") is None
    assert factory.units[0].commit_count == 1


@pytest.mark.parametrize("export_format", [ExportFormat.json, ExportFormat.csv])
def test_executor_duplicate_delivery_returns_terminal_resource_without_reexecution(
    export_format: ExportFormat,
) -> None:
    repository = Mock(spec=ExportRepository)
    repository.claim_export.return_value = None
    repository.get_export.return_value = _export(
        ExportExecutionStatus.completed, export_format=export_format
    )
    artifacts = Mock()
    storage = _StubArtifactStorage()
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)

    result = executor.execute(
        ExportTaskMessage(export_execution_id=EXPORT_ID),
        attempt_count=2,
    )

    assert result.status is ExportExecutionStatus.completed
    repository.load_export_inputs.assert_not_called()
    repository.mark_export_finished.assert_not_called()
    assert factory.units[0].commit_count == 0
    assert storage.stored == []


def test_executor_retries_unclassified_errors_then_redacts_final_diagnostic() -> None:
    repository = Mock(spec=ExportRepository)
    repository.claim_export.side_effect = [
        _export(ExportExecutionStatus.running),
        _export(ExportExecutionStatus.running),
        _export(ExportExecutionStatus.running),
    ]
    repository.load_export_inputs.side_effect = ConnectionError(
        "database postgresql://operator:secret@localhost/gendertagger unavailable"
    )
    repository.mark_export_finished.return_value = _export(ExportExecutionStatus.failed)
    artifacts = Mock()
    storage = _StubArtifactStorage()
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)
    message = ExportTaskMessage(export_execution_id=EXPORT_ID)

    with pytest.raises(TransientExportError):
        executor.execute(message, attempt_count=1, max_attempts=2)
    failed = executor.execute(message, attempt_count=2, max_attempts=2)

    assert failed.status is ExportExecutionStatus.failed
    finish_kwargs = repository.mark_export_finished.call_args.kwargs
    diagnostic = cast(str, finish_kwargs["failure_diagnostic"])
    assert "secret" not in diagnostic
    assert "postgresql://<redacted>@localhost" in diagnostic
    assert len(factory.units) == 3


_TEI_SOURCE_URI = "local:test-source"
_TEI_SOURCE_BYTES = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<TEI xmlns="http://www.tei-c.org/ns/1.0">'
    b'<person xml:id="p1"><persName>Example</persName></person>'
    b"</TEI>"
)


def _tei_inputs() -> ExportInputs:
    return ExportInputs(
        dataset_snapshot_id=UUID(int=9),
        source_snapshot_sha256="e" * 64,
        source_format=SourceFormat.tei,
        packaging=SourcePackaging.single,
        records=(
            ExportPersonRecord(
                tei_id="p1",
                person_record_id=PERSON_ID,
                source_member_name="A.xml",
                label=CanonicalLabel.male,
                evidence="assigned",
                resp="#gendertagger",
                cert="high",
                agreement_tier=AgreementTier.unanimous,
                certainty_tier=CertaintyTier.high,
                is_human_reviewed=False,
            ),
        ),
        source_members=(
            ExportSourceMember(
                logical_name="A.xml",
                artifact_id=ARTIFACT_ID,
                media_type="application/tei+xml",
            ),
        ),
    )


def test_executor_builds_tei_output_by_reading_and_injecting_each_source_member() -> None:
    repository = Mock(spec=ExportRepository)
    repository.claim_export.return_value = _export(
        ExportExecutionStatus.running, export_format=ExportFormat.tei
    )
    repository.load_export_inputs.return_value = _tei_inputs()
    repository.mark_export_finished.return_value = _export(
        ExportExecutionStatus.completed, export_format=ExportFormat.tei
    )
    artifacts = Mock()
    artifacts.get_artifact.return_value = Artifact(
        id=ARTIFACT_ID,
        logical_type="source_tei",
        storage_uri=_TEI_SOURCE_URI,
        sha256="a" * 64,
        byte_size=len(_TEI_SOURCE_BYTES),
        media_type="application/tei+xml",
        created_at=NOW,
    )
    artifacts.add_artifact.return_value = Artifact(
        id=ARTIFACT_ID,
        logical_type="export_manifest",
        storage_uri="local:test",
        sha256="a" * 64,
        byte_size=10,
        media_type="application/json",
        created_at=NOW,
    )
    storage = _StubArtifactStorage(sources={_TEI_SOURCE_URI: _TEI_SOURCE_BYTES})
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)

    result = executor.execute(
        ExportTaskMessage(export_execution_id=EXPORT_ID),
        attempt_count=1,
    )

    assert result.status is ExportExecutionStatus.completed
    assert storage.opened == [_TEI_SOURCE_URI]
    assert len(storage.stored) == 2
    assert b'<gender value="male"' in storage.stored[0]
    finish_kwargs = repository.mark_export_finished.call_args.kwargs
    assert finish_kwargs["manifest_artifact_id"] == ARTIFACT_ID
    assert factory.units[0].commit_count == 1


def test_executor_fails_terminally_when_a_labeled_person_is_missing_from_its_source_member() -> (
    None
):
    repository = Mock(spec=ExportRepository)
    repository.claim_export.return_value = _export(
        ExportExecutionStatus.running, export_format=ExportFormat.tei
    )
    missing_person_inputs = ExportInputs(
        dataset_snapshot_id=UUID(int=9),
        source_snapshot_sha256="e" * 64,
        source_format=SourceFormat.tei,
        packaging=SourcePackaging.single,
        records=(
            ExportPersonRecord(
                tei_id="not-in-source",
                person_record_id=PERSON_ID,
                source_member_name="A.xml",
                label=CanonicalLabel.male,
                evidence="assigned",
                resp="#gendertagger",
                cert="high",
                agreement_tier=AgreementTier.unanimous,
                certainty_tier=CertaintyTier.high,
                is_human_reviewed=False,
            ),
        ),
        source_members=(
            ExportSourceMember(
                logical_name="A.xml",
                artifact_id=ARTIFACT_ID,
                media_type="application/tei+xml",
            ),
        ),
    )
    repository.load_export_inputs.return_value = missing_person_inputs
    repository.mark_export_finished.return_value = _export(
        ExportExecutionStatus.failed, export_format=ExportFormat.tei
    )
    artifacts = Mock()
    artifacts.get_artifact.return_value = Artifact(
        id=ARTIFACT_ID,
        logical_type="source_tei",
        storage_uri=_TEI_SOURCE_URI,
        sha256="a" * 64,
        byte_size=len(_TEI_SOURCE_BYTES),
        media_type="application/tei+xml",
        created_at=NOW,
    )
    storage = _StubArtifactStorage(sources={_TEI_SOURCE_URI: _TEI_SOURCE_BYTES})
    executor, factory = _executor(repository, cast(ArtifactStorage, storage), artifacts)

    result = executor.execute(
        ExportTaskMessage(export_execution_id=EXPORT_ID),
        attempt_count=1,
    )

    assert result.status is ExportExecutionStatus.failed
    finish_kwargs = repository.mark_export_finished.call_args.kwargs
    assert finish_kwargs["failure_class"] == TeiExportError.__name__
    assert factory.units[0].commit_count == 1
