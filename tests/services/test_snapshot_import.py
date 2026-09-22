from collections.abc import Sequence
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Self, cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.artifact import Artifact
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.person import ImportedPerson
from gendertagger.models.project import (
    DatasetSnapshot,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotImportTaskMessage,
    SnapshotSourceMember,
    SourceFormat,
    SourcePackaging,
    TeiImportProfile,
)
from gendertagger.services.artifact_repository import ArtifactRepository
from gendertagger.services.artifact_storage import ArtifactStorage
from gendertagger.services.project_repository import ProjectRepository
from gendertagger.services.snapshot_import import (
    SnapshotImportExecutor,
    TransientSnapshotImportError,
)
from gendertagger.services.unit_of_work import UnitOfWork
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)
PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-0000-0000-000000000001")
MEMBER_ID = UUID("40000000-0000-0000-0000-000000000001")

_DEFAULT_CONFIG = SnapshotImportConfig(
    profile=TeiImportProfile.tei_p5_person_register,
    source_format=SourceFormat.tei,
    packaging=SourcePackaging.single,
    limits=SnapshotImportLimits(),
)

VALID_TEI = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<text><body><listPerson>
<person xml:id="p3"><persName type="reg"><surname>Third</surname></persName></person>
<person xml:id="p1"><persName type="reg"><surname>First</surname></persName></person>
<person xml:id="p2"><persName type="reg"><surname>Second</surname></persName></person>
</listPerson></body></text></TEI>"""

INVALID_TEI_AFTER_PERSON = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<person xml:id="p1"><persName type="reg"><surname>First</surname></persName></person>
<broken></TEI>"""


class _UnreadableSource(BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        del size
        raise OSError("staged artifact /private/operator-only/source.xml became unreadable")


class _StubUnitOfWork:
    def __init__(self, projects: ProjectRepository, artifacts: ArtifactRepository) -> None:
        self._projects = projects
        self._artifacts = artifacts
        self.commit_count = 0
        self.exit_exception_type: type[BaseException] | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception, traceback
        self.exit_exception_type = exception_type

    @property
    def projects(self) -> ProjectRepository:
        return self._projects

    @property
    def artifacts(self) -> ArtifactRepository:
        return self._artifacts

    def commit(self) -> None:
        self.commit_count += 1


class _UnitOfWorkFactory:
    def __init__(self, projects: ProjectRepository, artifacts: ArtifactRepository) -> None:
        self._projects = projects
        self._artifacts = artifacts
        self.units: list[_StubUnitOfWork] = []
        if isinstance(projects, Mock):

            def _list_members(_snapshot_id: UUID) -> tuple[SnapshotSourceMember, ...]:
                art = artifacts.get_artifact(ARTIFACT_ID)
                sha = art.sha256 if art is not None else "a" * 64
                size = art.byte_size if art is not None else len(VALID_TEI)
                media = art.media_type if art is not None else "application/tei+xml"
                return (
                    SnapshotSourceMember(
                        id=MEMBER_ID,
                        dataset_snapshot_id=SNAPSHOT_ID,
                        artifact_id=ARTIFACT_ID,
                        ordinal=0,
                        logical_name="source.xml",
                        sha256=sha,
                        byte_size=size,
                        media_type=media,
                        created_at=NOW,
                    ),
                )

            projects.list_snapshot_source_members.side_effect = _list_members

    def __call__(self) -> UnitOfWork:
        unit_of_work = _StubUnitOfWork(self._projects, self._artifacts)
        self.units.append(unit_of_work)
        return cast(UnitOfWork, unit_of_work)


def _snapshot(
    status: DatasetSnapshotStatus,
    *,
    diagnostic: str | None = None,
    source_sha256: str = "a" * 64,
) -> DatasetSnapshot:
    return DatasetSnapshot(
        id=SNAPSHOT_ID,
        project_id=PROJECT_ID,
        source_artifact_id=ARTIFACT_ID,
        source_sha256=source_sha256,
        parser_version=version_for_snapshot_import(_DEFAULT_CONFIG),
        import_config=_DEFAULT_CONFIG.model_dump(mode="json"),
        status=status,
        record_count=3 if status is DatasetSnapshotStatus.ready else None,
        ready_at=NOW if status is DatasetSnapshotStatus.ready else None,
        failure_diagnostic=diagnostic if status is DatasetSnapshotStatus.failed else None,
        created_at=NOW,
    )


def _stored_artifact(root: Path, source: bytes) -> tuple[LocalArtifactStorage, Artifact]:
    storage = LocalArtifactStorage(root)
    stored = storage.store(BytesIO(source), max_byte_size=len(source))
    return storage, Artifact(
        id=ARTIFACT_ID,
        logical_type="source_tei",
        storage_uri=stored.storage_uri,
        sha256=stored.sha256,
        byte_size=stored.byte_size,
        media_type="application/tei+xml",
        project_id=PROJECT_ID,
        created_at=NOW,
    )


def _executor(
    factory: _UnitOfWorkFactory,
    storage: ArtifactStorage,
    *,
    batch_size: int = 2,
) -> SnapshotImportExecutor:
    from gendertagger.ingestion.tei import TeiPersonParser

    return SnapshotImportExecutor(
        unit_of_work_factory=factory,
        artifact_storage=storage,
        parser=TeiPersonParser(),
        clock=lambda: NOW,
        import_batch_record_count=batch_size,
    )


def test_executor_streams_imported_batches_and_commits_atomically(
    tmp_path: Path,
) -> None:
    storage, artifact = _stored_artifact(tmp_path, VALID_TEI)
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    projects.claim_snapshot_import.return_value = _snapshot(
        DatasetSnapshotStatus.importing,
        source_sha256=artifact.sha256,
    )
    projects.complete_snapshot_import.return_value = _snapshot(
        DatasetSnapshotStatus.ready,
        source_sha256=artifact.sha256,
    )
    artifacts.get_artifact.return_value = artifact
    persisted_batches: list[list[str]] = []

    def add_people(_snapshot_id: UUID, people: Sequence[ImportedPerson]) -> int:
        persisted_batches.append([imported.person.tei_id for imported in people])
        return len(people)

    projects.add_imported_person_records.side_effect = add_people
    factory = _UnitOfWorkFactory(projects, artifacts)

    result = _executor(factory, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.ready
    assert persisted_batches == [["p3", "p1"], ["p2"]]
    assert projects.add_imported_person_records.call_count == 2
    projects.complete_snapshot_import.assert_called_once_with(SNAPSHOT_ID, ready_at=NOW)
    assert len(factory.units) == 1
    assert factory.units[0].commit_count == 1
    assert factory.units[0].exit_exception_type is None


def test_executor_duplicate_delivery_returns_terminal_snapshot_without_reimport() -> None:
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    projects.claim_snapshot_import.return_value = None
    projects.get_snapshot.return_value = _snapshot(DatasetSnapshotStatus.ready)
    storage = Mock(spec=ArtifactStorage)
    factory = _UnitOfWorkFactory(projects, artifacts)

    result = _executor(factory, cast(ArtifactStorage, storage)).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=2,
    )

    assert result.status is DatasetSnapshotStatus.ready
    artifacts.get_artifact.assert_not_called()
    projects.add_imported_person_records.assert_not_called()
    assert factory.units[0].commit_count == 0


def test_invalid_tei_rolls_back_partial_batch_then_fails_in_fresh_transaction(
    tmp_path: Path,
) -> None:
    storage, artifact = _stored_artifact(tmp_path, INVALID_TEI_AFTER_PERSON)
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    projects.claim_snapshot_import.side_effect = [
        _snapshot(DatasetSnapshotStatus.importing, source_sha256=artifact.sha256),
        _snapshot(DatasetSnapshotStatus.importing, source_sha256=artifact.sha256),
    ]
    artifacts.get_artifact.return_value = artifact
    projects.fail_snapshot_import.return_value = _snapshot(
        DatasetSnapshotStatus.failed,
        diagnostic="TEI import failed: invalid TEI XML",
        source_sha256=artifact.sha256,
    )
    factory = _UnitOfWorkFactory(projects, artifacts)

    result = _executor(factory, storage, batch_size=1).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
        max_attempts=3,
    )

    assert result.status is DatasetSnapshotStatus.failed
    assert projects.add_imported_person_records.call_count == 1
    diagnostic = projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic.startswith("TEI import failed:")
    assert "invalid TEI XML" in diagnostic
    assert len(factory.units) == 2
    assert projects.claim_snapshot_import.call_count == 2
    assert factory.units[0].commit_count == 0
    assert factory.units[0].exit_exception_type is not None
    assert factory.units[1].commit_count == 1
    diagnostic = projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic.startswith("TEI import failed:")
    assert "invalid TEI XML" in diagnostic
    assert len(factory.units) == 2
    assert projects.claim_snapshot_import.call_count == 2
    assert factory.units[0].commit_count == 0
    assert factory.units[0].exit_exception_type is not None
    assert factory.units[1].commit_count == 1


def test_parser_version_mismatch_fails_without_opening_the_source() -> None:
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    importing = _snapshot(DatasetSnapshotStatus.importing).model_copy(
        update={"parser_version": "unsupported_parser"}
    )
    projects.claim_snapshot_import.side_effect = [importing, importing]
    artifacts.get_artifact.return_value = Artifact(
        id=ARTIFACT_ID,
        logical_type="source_tei",
        storage_uri="local-sha256:" + "a" * 64,
        sha256="a" * 64,
        byte_size=1,
        media_type="application/tei+xml",
        project_id=PROJECT_ID,
        created_at=NOW,
    )
    projects.fail_snapshot_import.return_value = _snapshot(
        DatasetSnapshotStatus.failed,
        diagnostic="PermanentSnapshotImportError: parser mismatch",
    )
    storage = Mock(spec=ArtifactStorage)
    factory = _UnitOfWorkFactory(projects, artifacts)

    result = _executor(factory, cast(ArtifactStorage, storage)).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.failed
    storage.open.assert_not_called()
    diagnostic = projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic == "Snapshot import provenance is invalid."
    assert [unit.commit_count for unit in factory.units] == [0, 1]


def test_unclassified_failure_retries_then_persists_only_a_generic_diagnostic() -> None:
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    projects.claim_snapshot_import.side_effect = [
        _snapshot(DatasetSnapshotStatus.importing),
        _snapshot(DatasetSnapshotStatus.importing),
        _snapshot(DatasetSnapshotStatus.importing),
    ]
    artifacts.get_artifact.return_value = Artifact(
        id=ARTIFACT_ID,
        logical_type="source_tei",
        storage_uri="local-sha256:" + "a" * 64,
        sha256="a" * 64,
        byte_size=1,
        media_type="application/tei+xml",
        project_id=PROJECT_ID,
        created_at=NOW,
    )
    projects.fail_snapshot_import.return_value = _snapshot(
        DatasetSnapshotStatus.failed,
        diagnostic="Snapshot import failed due to an internal error.",
    )
    storage = Mock(spec=ArtifactStorage)
    storage.open.side_effect = OSError(
        "artifact backend https://operator:secret@storage.internal unavailable"
    )
    factory = _UnitOfWorkFactory(projects, artifacts)
    executor = _executor(factory, cast(ArtifactStorage, storage))
    message = SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID)

    with pytest.raises(TransientSnapshotImportError):
        executor.execute(message, attempt_count=1, max_attempts=2)
    failed = executor.execute(message, attempt_count=2, max_attempts=2)

    assert failed.status is DatasetSnapshotStatus.failed
    diagnostic = projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic == "Snapshot import failed due to an internal error."
    assert "secret" not in diagnostic
    assert "storage.internal" not in diagnostic
    assert len(factory.units) == 3
    assert [unit.commit_count for unit in factory.units] == [0, 0, 1]


def test_source_read_failure_retries_then_persists_only_a_generic_diagnostic() -> None:
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    projects.claim_snapshot_import.side_effect = [
        _snapshot(DatasetSnapshotStatus.importing),
        _snapshot(DatasetSnapshotStatus.importing),
        _snapshot(DatasetSnapshotStatus.importing),
    ]
    artifacts.get_artifact.return_value = Artifact(
        id=ARTIFACT_ID,
        logical_type="source_tei",
        storage_uri="local-sha256:" + "a" * 64,
        sha256="a" * 64,
        byte_size=1,
        media_type="application/tei+xml",
        project_id=PROJECT_ID,
        created_at=NOW,
    )
    projects.fail_snapshot_import.return_value = _snapshot(
        DatasetSnapshotStatus.failed,
        diagnostic="Snapshot import failed due to an internal error.",
    )
    storage = Mock(spec=ArtifactStorage)
    storage.open.side_effect = lambda _storage_uri: _UnreadableSource(VALID_TEI)
    factory = _UnitOfWorkFactory(projects, artifacts)
    executor = _executor(factory, cast(ArtifactStorage, storage))
    message = SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID)

    with pytest.raises(TransientSnapshotImportError):
        executor.execute(message, attempt_count=1, max_attempts=2)
    failed = executor.execute(message, attempt_count=2, max_attempts=2)

    assert failed.status is DatasetSnapshotStatus.failed
    diagnostic = projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic == "Snapshot import failed due to an internal error."
    assert "operator-only" not in diagnostic
    assert projects.add_imported_person_records.call_count == 0
    assert [unit.commit_count for unit in factory.units] == [0, 0, 1]


def test_terminal_failure_persistence_error_is_retryable_while_budget_remains() -> None:
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    importing = _snapshot(DatasetSnapshotStatus.importing).model_copy(
        update={"parser_version": "unsupported_parser"}
    )
    projects.claim_snapshot_import.side_effect = [importing, importing]
    projects.fail_snapshot_import.side_effect = OSError("database temporarily unavailable")
    factory = _UnitOfWorkFactory(projects, artifacts)

    with pytest.raises(TransientSnapshotImportError, match="could not be persisted"):
        _executor(factory, cast(ArtifactStorage, Mock(spec=ArtifactStorage))).execute(
            SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
            attempt_count=1,
            max_attempts=2,
        )

    assert [unit.commit_count for unit in factory.units] == [0, 0]
    assert all(unit.exit_exception_type is not None for unit in factory.units)


@pytest.mark.parametrize(
    "import_config",
    [
        {},
        {"profile": "unsupported_profile", "source_format": "tei"},
        {"profile": "tei_p5_person_register"},
    ],
)
def test_executor_rejects_incomplete_or_invalid_import_config(
    import_config: dict[str, str],
) -> None:
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    importing = _snapshot(DatasetSnapshotStatus.importing).model_copy(
        update={"import_config": import_config}
    )
    projects.claim_snapshot_import.side_effect = [importing, importing]
    projects.fail_snapshot_import.return_value = _snapshot(
        DatasetSnapshotStatus.failed,
        diagnostic="Snapshot import provenance is invalid.",
    )
    storage = Mock(spec=ArtifactStorage)
    factory = _UnitOfWorkFactory(projects, artifacts)

    result = _executor(factory, cast(ArtifactStorage, storage)).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.failed
    artifacts.get_artifact.assert_not_called()
    storage.open.assert_not_called()
    diagnostic = projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic == "Snapshot import provenance is invalid."


@pytest.mark.parametrize("corruption", ["checksum", "byte_size"])
def test_reopened_artifact_integrity_mismatch_is_permanent_provenance_failure(
    tmp_path: Path,
    corruption: str,
) -> None:
    storage, stored_artifact = _stored_artifact(tmp_path, VALID_TEI)
    if corruption == "checksum":
        artifact = stored_artifact.model_copy(update={"sha256": "b" * 64})
    else:
        artifact = stored_artifact.model_copy(update={"byte_size": stored_artifact.byte_size + 1})
    importing = _snapshot(
        DatasetSnapshotStatus.importing,
        source_sha256=artifact.sha256,
    )
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    projects.claim_snapshot_import.side_effect = [importing, importing]
    projects.fail_snapshot_import.return_value = _snapshot(
        DatasetSnapshotStatus.failed,
        diagnostic="Snapshot import provenance is invalid.",
        source_sha256=artifact.sha256,
    )
    artifacts.get_artifact.return_value = artifact
    factory = _UnitOfWorkFactory(projects, artifacts)

    result = _executor(factory, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.failed
    projects.add_imported_person_records.assert_not_called()
    projects.complete_snapshot_import.assert_not_called()
    diagnostic = projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic == "Snapshot import provenance is invalid."
    assert [unit.commit_count for unit in factory.units] == [0, 1]


@pytest.mark.parametrize(("attempt_count", "max_attempts"), [(0, 1), (1, 0)])
def test_executor_rejects_nonpositive_attempt_limits(
    attempt_count: int,
    max_attempts: int,
) -> None:
    factory = _UnitOfWorkFactory(
        Mock(spec=ProjectRepository),
        Mock(spec=ArtifactRepository),
    )

    with pytest.raises(ValueError, match="must be positive"):
        _executor(factory, cast(ArtifactStorage, Mock(spec=ArtifactStorage))).execute(
            SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
            attempt_count=attempt_count,
            max_attempts=max_attempts,
        )
