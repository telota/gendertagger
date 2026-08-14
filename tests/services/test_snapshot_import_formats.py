"""Format-level integration tests for the asynchronous snapshot importer."""

from __future__ import annotations

import csv
import importlib
import io
import json
import tarfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO, Self, cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.ingestion.tabular import TEI_EQUIVALENT_HEADERS
from gendertagger.ingestion.tabular import version_for_profile as tabular_version_for_profile
from gendertagger.ingestion.tei import TeiPersonParser
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
    SourceManifestMember,
    SourceManifestV1,
    SourcePackaging,
    TabularImportProfile,
    TeiImportProfile,
)
from gendertagger.services.artifact_repository import ArtifactRepository
from gendertagger.services.project_repository import ProjectRepository
from gendertagger.services.snapshot_import import (
    SnapshotImportExecutor,
    TransientSnapshotImportError,
)
from gendertagger.services.unit_of_work import UnitOfWork
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 14, 19, 0, tzinfo=UTC)
PROJECT_ID = UUID("10000000-0000-0000-0000-000000000010")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000010")

LIMITS = SnapshotImportLimits(
    max_member_count=100,
    max_member_expanded_bytes=10 * 1024 * 1024,
    max_total_expanded_bytes=20 * 1024 * 1024,
    max_compression_ratio=1_000,
    max_record_count=1_000,
    max_cell_bytes=100_000,
)
TEI_PROFILE = TeiImportProfile.tei_p5_person_register_v3
TABULAR_PROFILE = TabularImportProfile.tei_equivalent_person_register_v1
TABULAR_PARSER_VERSION = tabular_version_for_profile(TABULAR_PROFILE)


class _ShortReadBytesIO(io.BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        requested = -1 if size is None else size
        return super().read(3 if requested < 0 else min(requested, 3))


class _FailingReadBytesIO(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self._read_count = 0

    def read(self, size: int | None = -1) -> bytes:
        self._read_count += 1
        if self._read_count > 1:
            raise OSError("simulated artifact backend interruption")
        requested = -1 if size is None else size
        return super().read(3 if requested < 0 else min(requested, 3))


class _StubUnitOfWork:
    def __init__(
        self,
        projects: Mock,
        artifacts: Mock,
        committed_batches: list[tuple[ImportedPerson, ...]],
    ) -> None:
        self._projects = projects
        self._artifacts = artifacts
        self._committed_batches = committed_batches
        self.staged_batches: list[tuple[ImportedPerson, ...]] = []
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
        return cast(ProjectRepository, self._projects)

    @property
    def artifacts(self) -> ArtifactRepository:
        return cast(ArtifactRepository, self._artifacts)

    def commit(self) -> None:
        self._committed_batches.extend(self.staged_batches)
        self.commit_count += 1


class _UnitOfWorkFactory:
    def __init__(self, projects: Mock, artifacts: Mock) -> None:
        self._projects = projects
        self._artifacts = artifacts
        self.units: list[_StubUnitOfWork] = []
        self.committed_batches: list[tuple[ImportedPerson, ...]] = []

    def __call__(self) -> UnitOfWork:
        unit = _StubUnitOfWork(
            self._projects,
            self._artifacts,
            self.committed_batches,
        )
        self.units.append(unit)
        return cast(UnitOfWork, unit)


@dataclass(slots=True)
class _Harness:
    projects: Mock
    artifacts: Mock
    factory: _UnitOfWorkFactory
    batches: list[tuple[ImportedPerson, ...]]

    @property
    def people(self) -> list[ImportedPerson]:
        return [person for batch in self.factory.committed_batches for person in batch]

    @property
    def attempted_people(self) -> list[ImportedPerson]:
        return [person for batch in self.batches for person in batch]


def _artifact_id(index: int) -> UUID:
    return UUID(f"30000000-0000-0000-0000-{index:012d}")


def _source_member_id(index: int) -> UUID:
    return UUID(f"40000000-0000-0000-0000-{index:012d}")


def _store_artifact(
    storage: LocalArtifactStorage,
    payload: bytes,
    *,
    artifact_id: UUID,
    logical_type: str,
    media_type: str,
) -> Artifact:
    stored = storage.store(io.BytesIO(payload), max_byte_size=max(len(payload), 1))
    return Artifact(
        id=artifact_id,
        logical_type=logical_type,
        storage_uri=stored.storage_uri,
        sha256=stored.sha256,
        byte_size=stored.byte_size,
        media_type=media_type,
        project_id=PROJECT_ID,
        created_at=NOW,
    )


def _source_member(
    artifact: Artifact,
    *,
    logical_name: str,
    ordinal: int,
) -> SnapshotSourceMember:
    return SnapshotSourceMember(
        id=_source_member_id(ordinal + 1),
        dataset_snapshot_id=SNAPSHOT_ID,
        artifact_id=artifact.id,
        ordinal=ordinal,
        logical_name=logical_name,
        sha256=artifact.sha256,
        byte_size=artifact.byte_size,
        media_type=artifact.media_type,
        created_at=NOW,
    )


def _config(
    *,
    source_format: SourceFormat,
    packaging: SourcePackaging,
    profile: TeiImportProfile | TabularImportProfile,
    limits: SnapshotImportLimits = LIMITS,
) -> SnapshotImportConfig:
    return SnapshotImportConfig(
        source_format=source_format,
        packaging=packaging,
        profile=profile,
        limits=limits,
    )


def _snapshot(
    primary: Artifact,
    *,
    config: SnapshotImportConfig,
    parser_version: str,
) -> DatasetSnapshot:
    return DatasetSnapshot(
        id=SNAPSHOT_ID,
        project_id=PROJECT_ID,
        source_artifact_id=primary.id,
        source_sha256=primary.sha256,
        parser_version=parser_version,
        import_config=config.model_dump(mode="json"),
        status=DatasetSnapshotStatus.importing,
        created_at=NOW,
    )


def _terminal_snapshot(
    snapshot: DatasetSnapshot,
    *,
    status: DatasetSnapshotStatus,
    record_count: int | None = None,
    failure_diagnostic: str | None = None,
) -> DatasetSnapshot:
    values = snapshot.model_dump()
    values.update(
        status=status,
        record_count=record_count,
        ready_at=NOW if status is DatasetSnapshotStatus.ready else None,
        failure_diagnostic=failure_diagnostic,
    )
    return DatasetSnapshot.model_validate(values)


def _harness(
    snapshot: DatasetSnapshot,
    *,
    members: Sequence[SnapshotSourceMember],
    artifacts_by_id: dict[UUID, Artifact],
) -> _Harness:
    projects = Mock(spec=ProjectRepository)
    artifacts = Mock(spec=ArtifactRepository)
    batches: list[tuple[ImportedPerson, ...]] = []
    projects.claim_snapshot_import.return_value = snapshot
    projects.list_snapshot_source_members.return_value = tuple(members)
    artifacts.get_artifact.side_effect = artifacts_by_id.get
    factory = _UnitOfWorkFactory(projects, artifacts)

    def add_people(snapshot_id: UUID, people: Sequence[ImportedPerson]) -> int:
        assert snapshot_id == SNAPSHOT_ID
        batch = tuple(people)
        batches.append(batch)
        factory.units[-1].staged_batches.append(batch)
        return len(people)

    def complete(snapshot_id: UUID, *, ready_at: datetime) -> DatasetSnapshot:
        assert snapshot_id == SNAPSHOT_ID
        assert ready_at == NOW
        return _terminal_snapshot(
            snapshot,
            status=DatasetSnapshotStatus.ready,
            record_count=sum(len(batch) for batch in batches),
        )

    def fail(snapshot_id: UUID, *, failure_diagnostic: str) -> DatasetSnapshot:
        assert snapshot_id == SNAPSHOT_ID
        return _terminal_snapshot(
            snapshot,
            status=DatasetSnapshotStatus.failed,
            failure_diagnostic=failure_diagnostic,
        )

    projects.add_imported_person_records.side_effect = add_people
    projects.complete_snapshot_import.side_effect = complete
    projects.fail_snapshot_import.side_effect = fail
    return _Harness(
        projects=projects,
        artifacts=artifacts,
        factory=factory,
        batches=batches,
    )


def _executor(
    harness: _Harness,
    storage: LocalArtifactStorage,
    *,
    batch_size: int = 2,
) -> SnapshotImportExecutor:
    return SnapshotImportExecutor(
        unit_of_work_factory=harness.factory,
        artifact_storage=storage,
        parser=TeiPersonParser(),
        clock=lambda: NOW,
        import_batch_record_count=batch_size,
    )


def _tei_person(tei_id: str, surname: str) -> bytes:
    return f"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
<person xml:id="{tei_id}"><persName type="reg"><surname>{surname}</surname>
<forename>Anna</forename></persName></person>
</listPerson></body></text></TEI>""".encode()


def _manifest_primary(
    storage: LocalArtifactStorage,
    members: Sequence[SnapshotSourceMember],
) -> Artifact:
    manifest = SourceManifestV1(
        source_format=SourceFormat.tei,
        packaging=SourcePackaging.loose,
        members=tuple(
            SourceManifestMember(
                logical_name=member.logical_name,
                sha256=member.sha256,
                byte_size=member.byte_size,
                media_type=member.media_type,
            )
            for member in members
        ),
    )
    return _store_artifact(
        storage,
        manifest.canonical_bytes(),
        artifact_id=_artifact_id(90),
        logical_type="source_manifest",
        media_type="application/json",
    )


def _loose_source(
    storage: LocalArtifactStorage,
    *,
    duplicate_ids: bool = False,
    limits: SnapshotImportLimits = LIMITS,
) -> tuple[DatasetSnapshot, tuple[SnapshotSourceMember, ...], dict[UUID, Artifact]]:
    member_b_artifact = _store_artifact(
        storage,
        _tei_person("shared" if duplicate_ids else "p2", "Second"),
        artifact_id=_artifact_id(2),
        logical_type="source_tei",
        media_type="application/tei+xml",
    )
    member_a_artifact = _store_artifact(
        storage,
        _tei_person("shared" if duplicate_ids else "p1", "First"),
        artifact_id=_artifact_id(1),
        logical_type="source_tei",
        media_type="application/tei+xml",
    )
    members = (
        _source_member(member_b_artifact, logical_name="letters/B.xml", ordinal=0),
        _source_member(member_a_artifact, logical_name="A.xml", ordinal=1),
    )
    primary = _manifest_primary(storage, members)
    config = _config(
        source_format=SourceFormat.tei,
        packaging=SourcePackaging.loose,
        profile=TEI_PROFILE,
        limits=limits,
    )
    snapshot = _snapshot(
        primary,
        config=config,
        parser_version=version_for_snapshot_import(config),
    )
    artifacts = {
        primary.id: primary,
        member_a_artifact.id: member_a_artifact,
        member_b_artifact.id: member_b_artifact,
    }
    return snapshot, members, artifacts


def _zip_bytes(entries: Sequence[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return output.getvalue()


def _tar_gz_bytes(entries: Sequence[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def _tabular_record() -> dict[str, object]:
    return {
        "xml:id": "p1",
        "persName": [
            {"type": "reg", "surname": "Example", "forename": ["Anna Maria", "Luise"]},
            {"type": "alt", "name": "A. Example"},
        ],
        "birth": "um 1810",
        "death": None,
        "event": [{"type": "wedding", "when": "1832-09-20", "note": "Berlin"}],
        "note": "Scholar and editor.",
        "idno": [
            {"type": "uri", "value": "https://d-nb.info/gnd/123456789"},
            {"type": "uri", "value": "https://viaf.org/viaf/98765"},
        ],
    }


def _csv_bytes(record: dict[str, object]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(TEI_EQUIVALENT_HEADERS)
    writer.writerow(
        [
            record["xml:id"],
            json.dumps(record["persName"], ensure_ascii=False),
            record["birth"],
            record["death"] or "",
            json.dumps(record["event"], ensure_ascii=False),
            record["note"],
            json.dumps(record["idno"], ensure_ascii=False),
        ]
    )
    return output.getvalue().encode()


def _xlsx_bytes(record: dict[str, object]) -> bytes:
    openpyxl: Any = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "persons"
    worksheet.append(list(TEI_EQUIVALENT_HEADERS))
    worksheet.append(
        [
            record["xml:id"],
            json.dumps(record["persName"], ensure_ascii=False),
            record["birth"],
            record["death"],
            json.dumps(record["event"], ensure_ascii=False),
            record["note"],
            json.dumps(record["idno"], ensure_ascii=False),
        ]
    )
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_loose_tei_import_is_deterministic_and_preserves_member_provenance(
    tmp_path: Path,
) -> None:
    storage = LocalArtifactStorage(tmp_path)
    snapshot, members, artifacts = _loose_source(storage)
    harness = _harness(snapshot, members=members, artifacts_by_id=artifacts)

    result = _executor(harness, storage, batch_size=1).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.ready
    assert [imported.person.tei_id for imported in harness.people] == ["p1", "p2"]
    assert [imported.source_member_name for imported in harness.people] == [
        "A.xml",
        "letters/B.xml",
    ]
    assert [imported.source_record_locator for imported in harness.people] == [
        "xml:id=p1",
        "xml:id=p2",
    ]
    harness.projects.add_person_records.assert_not_called()
    assert [unit.commit_count for unit in harness.factory.units] == [1]


def test_single_tei_import_does_not_require_an_xml_filename_suffix(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)
    primary = _store_artifact(
        storage,
        _tei_person("p1", "First"),
        artifact_id=_artifact_id(1),
        logical_type="source_tei",
        media_type="application/tei+xml",
    )
    member = _source_member(primary, logical_name="register.tei", ordinal=0)
    config = _config(
        source_format=SourceFormat.tei,
        packaging=SourcePackaging.single,
        profile=TEI_PROFILE,
    )
    snapshot = _snapshot(
        primary,
        config=config,
        parser_version=version_for_snapshot_import(config),
    )
    harness = _harness(snapshot, members=(member,), artifacts_by_id={primary.id: primary})

    result = _executor(harness, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.ready
    assert [person.person.tei_id for person in harness.people] == ["p1"]
    assert harness.people[0].source_member_name == "register.tei"


@pytest.mark.parametrize(
    ("packaging", "logical_type", "container_name", "media_type"),
    [
        (SourcePackaging.zip, "source_zip", "register.zip", "application/zip"),
        (
            SourcePackaging.tar_gz,
            "source_tar_gz",
            "register.tar.gz",
            "application/gzip",
        ),
    ],
)
def test_archive_tei_imports_internal_members(
    tmp_path: Path,
    packaging: SourcePackaging,
    logical_type: str,
    container_name: str,
    media_type: str,
) -> None:
    entries = [
        ("letters/B.xml", _tei_person("p2", "Second")),
        ("A.xml", _tei_person("p1", "First")),
    ]
    payload = _zip_bytes(entries) if packaging is SourcePackaging.zip else _tar_gz_bytes(entries)
    storage = LocalArtifactStorage(tmp_path)
    primary = _store_artifact(
        storage,
        payload,
        artifact_id=_artifact_id(1),
        logical_type=logical_type,
        media_type=media_type,
    )
    members = (_source_member(primary, logical_name=container_name, ordinal=0),)
    config = _config(
        source_format=SourceFormat.tei,
        packaging=packaging,
        profile=TEI_PROFILE,
    )
    snapshot = _snapshot(
        primary,
        config=config,
        parser_version=version_for_snapshot_import(config),
    )
    harness = _harness(snapshot, members=members, artifacts_by_id={primary.id: primary})

    result = _executor(harness, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.ready
    assert [imported.person.tei_id for imported in harness.people] == ["p1", "p2"]
    assert [imported.source_member_name for imported in harness.people] == [
        "A.xml",
        "letters/B.xml",
    ]
    assert [imported.source_record_locator for imported in harness.people] == [
        "xml:id=p1",
        "xml:id=p2",
    ]


def test_cross_file_duplicate_tei_id_rolls_back_people_before_terminal_failure(
    tmp_path: Path,
) -> None:
    storage = LocalArtifactStorage(tmp_path)
    snapshot, members, artifacts = _loose_source(storage, duplicate_ids=True)
    harness = _harness(snapshot, members=members, artifacts_by_id=artifacts)

    result = _executor(harness, storage, batch_size=1).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.failed
    assert [imported.person.tei_id for imported in harness.attempted_people] == ["shared"]
    assert harness.people == []
    assert [unit.commit_count for unit in harness.factory.units] == [0, 1]
    assert harness.factory.units[0].exit_exception_type is not None
    harness.projects.complete_snapshot_import.assert_not_called()
    diagnostic = harness.projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic.startswith("TEI import failed: duplicate TEI xml:id")


def test_json_csv_and_xlsx_imports_have_equivalent_person_projections_and_row_provenance(
    tmp_path: Path,
) -> None:
    record = _tabular_record()
    cases = [
        (SourceFormat.json, "register.json", "application/json", json.dumps([record]).encode()),
        (SourceFormat.csv, "register.csv", "text/csv", _csv_bytes(record)),
        (
            SourceFormat.xlsx,
            "register.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _xlsx_bytes(record),
        ),
    ]
    imported_by_format: dict[SourceFormat, ImportedPerson] = {}

    for source_format, logical_name, media_type, payload in cases:
        storage = LocalArtifactStorage(tmp_path / source_format.value)
        primary = _store_artifact(
            storage,
            payload,
            artifact_id=_artifact_id(1),
            logical_type=f"source_{source_format.value}",
            media_type=media_type,
        )
        members = (_source_member(primary, logical_name=logical_name, ordinal=0),)
        config = _config(
            source_format=source_format,
            packaging=SourcePackaging.single,
            profile=TABULAR_PROFILE,
        )
        snapshot = _snapshot(
            primary,
            config=config,
            parser_version=TABULAR_PARSER_VERSION,
        )
        harness = _harness(snapshot, members=members, artifacts_by_id={primary.id: primary})

        result = _executor(harness, storage).execute(
            SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
            attempt_count=1,
        )

        assert result.status is DatasetSnapshotStatus.ready
        [imported_by_format[source_format]] = harness.people

    assert (
        imported_by_format[SourceFormat.json].person
        == imported_by_format[SourceFormat.csv].person
        == imported_by_format[SourceFormat.xlsx].person
    )
    assert imported_by_format[SourceFormat.json].source_record_locator == "row:1"
    assert imported_by_format[SourceFormat.csv].source_record_locator == "row:2"
    assert imported_by_format[SourceFormat.xlsx].source_record_locator == "row:2"
    assert {
        source_format: imported.source_member_name
        for source_format, imported in imported_by_format.items()
    } == {
        SourceFormat.json: "register.json",
        SourceFormat.csv: "register.csv",
        SourceFormat.xlsx: "register.xlsx",
    }


def test_persisted_member_limit_mismatch_fails_without_importing_people(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)
    strict_limits = LIMITS.model_copy(update={"max_member_count": 1})
    snapshot, members, artifacts = _loose_source(storage, limits=strict_limits)
    harness = _harness(snapshot, members=members, artifacts_by_id=artifacts)

    result = _executor(harness, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.failed
    harness.projects.add_imported_person_records.assert_not_called()
    diagnostic = harness.projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic == "Snapshot import provenance is invalid."
    assert [unit.commit_count for unit in harness.factory.units] == [0, 1]


def test_persisted_parser_version_mismatch_fails_before_source_resolution(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)
    primary = _store_artifact(
        storage,
        json.dumps([_tabular_record()]).encode(),
        artifact_id=_artifact_id(1),
        logical_type="source_json",
        media_type="application/json",
    )
    member = _source_member(primary, logical_name="register.json", ordinal=0)
    config = _config(
        source_format=SourceFormat.json,
        packaging=SourcePackaging.single,
        profile=TABULAR_PROFILE,
    )
    private_version = "private/operator/path/parser-v0"
    snapshot = _snapshot(primary, config=config, parser_version=private_version)
    harness = _harness(snapshot, members=(member,), artifacts_by_id={primary.id: primary})

    result = _executor(harness, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.failed
    harness.artifacts.get_artifact.assert_not_called()
    harness.projects.list_snapshot_source_members.assert_not_called()
    diagnostic = harness.projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic == "Snapshot import provenance is invalid."
    assert private_version not in diagnostic
    assert [unit.commit_count for unit in harness.factory.units] == [0, 1]


def test_manifest_validation_supports_bounded_short_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = LocalArtifactStorage(tmp_path)
    snapshot, members, artifacts = _loose_source(storage)
    harness = _harness(snapshot, members=members, artifacts_by_id=artifacts)
    manifest_uri = artifacts[snapshot.source_artifact_id].storage_uri
    real_open = storage.open

    def open_with_short_manifest_reads(storage_uri: str) -> BinaryIO:
        if storage_uri != manifest_uri:
            return real_open(storage_uri)
        with real_open(storage_uri) as source:
            return _ShortReadBytesIO(source.read())

    monkeypatch.setattr(storage, "open", open_with_short_manifest_reads)

    result = _executor(harness, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.ready
    assert [person.person.tei_id for person in harness.people] == ["p1", "p2"]


def test_manifest_io_failure_is_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = LocalArtifactStorage(tmp_path)
    snapshot, members, artifacts = _loose_source(storage)
    harness = _harness(snapshot, members=members, artifacts_by_id=artifacts)
    manifest_uri = artifacts[snapshot.source_artifact_id].storage_uri
    real_open = storage.open

    def open_with_failing_manifest_read(storage_uri: str) -> BinaryIO:
        if storage_uri != manifest_uri:
            return real_open(storage_uri)
        with real_open(storage_uri) as source:
            return _FailingReadBytesIO(source.read())

    monkeypatch.setattr(storage, "open", open_with_failing_manifest_read)

    with pytest.raises(TransientSnapshotImportError):
        _executor(harness, storage).execute(
            SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
            attempt_count=1,
            max_attempts=2,
        )

    harness.projects.fail_snapshot_import.assert_not_called()
    assert [unit.commit_count for unit in harness.factory.units] == [0]


def test_single_tabular_source_uses_the_smaller_member_and_total_byte_limit(
    tmp_path: Path,
) -> None:
    payload = json.dumps([_tabular_record()]).encode()
    limits = LIMITS.model_copy(
        update={
            "max_member_expanded_bytes": len(payload) + 100,
            "max_total_expanded_bytes": len(payload) - 1,
        }
    )
    storage = LocalArtifactStorage(tmp_path)
    primary = _store_artifact(
        storage,
        payload,
        artifact_id=_artifact_id(1),
        logical_type="source_json",
        media_type="application/json",
    )
    member = _source_member(primary, logical_name="register.json", ordinal=0)
    config = _config(
        source_format=SourceFormat.json,
        packaging=SourcePackaging.single,
        profile=TABULAR_PROFILE,
        limits=limits,
    )
    snapshot = _snapshot(primary, config=config, parser_version=TABULAR_PARSER_VERSION)
    harness = _harness(snapshot, members=(member,), artifacts_by_id={primary.id: primary})

    result = _executor(harness, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.failed
    diagnostic = harness.projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic == "Tabular import failed: tabular source exceeds the byte-size limit"


def test_persisted_cell_limit_is_enforced_as_utf8_bytes(tmp_path: Path) -> None:
    record = {
        "xml:id": "p1",
        "persName": [{"type": "reg", "surname": "A", "forename": []}],
        "birth": None,
        "death": None,
        "event": [],
        "note": "äääää",
        "idno": [],
    }
    payload = json.dumps([record], ensure_ascii=False).encode()
    limits = LIMITS.model_copy(update={"max_cell_bytes": 9})
    storage = LocalArtifactStorage(tmp_path)
    primary = _store_artifact(
        storage,
        payload,
        artifact_id=_artifact_id(1),
        logical_type="source_json",
        media_type="application/json",
    )
    member = _source_member(primary, logical_name="register.json", ordinal=0)
    config = _config(
        source_format=SourceFormat.json,
        packaging=SourcePackaging.single,
        profile=TABULAR_PROFILE,
        limits=limits,
    )
    snapshot = _snapshot(primary, config=config, parser_version=TABULAR_PARSER_VERSION)
    harness = _harness(snapshot, members=(member,), artifacts_by_id={primary.id: primary})

    result = _executor(harness, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        attempt_count=1,
    )

    assert result.status is DatasetSnapshotStatus.failed
    diagnostic = harness.projects.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert "column 'note': exceeds the byte limit" in diagnostic


def test_missing_xlsx_dependency_is_retryable_infrastructure_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _xlsx_bytes(_tabular_record())
    storage = LocalArtifactStorage(tmp_path)
    primary = _store_artifact(
        storage,
        payload,
        artifact_id=_artifact_id(1),
        logical_type="source_xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    member = _source_member(primary, logical_name="register.xlsx", ordinal=0)
    config = _config(
        source_format=SourceFormat.xlsx,
        packaging=SourcePackaging.single,
        profile=TABULAR_PROFILE,
    )
    snapshot = _snapshot(primary, config=config, parser_version=TABULAR_PARSER_VERSION)
    harness = _harness(snapshot, members=(member,), artifacts_by_id={primary.id: primary})
    real_import_module = importlib.import_module

    def fail_openpyxl(name: str, package: str | None = None) -> object:
        if name == "openpyxl":
            raise ImportError("simulated missing dependency")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fail_openpyxl)

    with pytest.raises(TransientSnapshotImportError):
        _executor(harness, storage).execute(
            SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
            attempt_count=1,
            max_attempts=2,
        )

    harness.projects.fail_snapshot_import.assert_not_called()
    assert [unit.commit_count for unit in harness.factory.units] == [0]
