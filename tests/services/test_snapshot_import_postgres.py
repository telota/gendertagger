import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from io import BytesIO
from pathlib import Path
from threading import Event, Lock, current_thread
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, func, select, text

from gendertagger.db.artifacts import ArtifactRow
from gendertagger.db.dispatch_repository import SqlAlchemyDispatchRepository
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.projects import DatasetSnapshotRow
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.dispatch import SnapshotDispatch, SnapshotDispatchCreate
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.person import ImportedPerson
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotImportRequest,
    SnapshotImportTaskMessage,
    SnapshotSourceMemberCreate,
    SourceFormat,
    SourcePackaging,
    TabularImportProfile,
    TeiImportProfile,
)
from gendertagger.models.user import UserCreate
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.projects import ProjectService, SnapshotUpload
from gendertagger.services.snapshot_import import SnapshotImportExecutor
from gendertagger.services.unit_of_work import UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
VALID_TEI = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<text><body><listPerson>
<person xml:id="p1"><persName type="reg"><surname>First</surname></persName></person>
<person xml:id="p2"><persName type="reg"><surname>Second</surname></persName></person>
</listPerson></body></text></TEI>"""
INVALID_TEI_AFTER_PERSON = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<person xml:id="p1"><persName type="reg"><surname>First</surname></persName></person>
<broken></TEI>"""


@dataclass
class _FlushedAcceptance:
    artifact_id: UUID | None = None
    snapshot_id: UUID | None = None
    dispatch_id: UUID | None = None
    storage_uri: str | None = None


def _seed_snapshot(
    unit_of_work_factory: UnitOfWorkFactory,
    storage: LocalArtifactStorage,
    source: bytes,
    *,
    profile: TeiImportProfile = TeiImportProfile.tei_p5_person_register_v2,
) -> UUID:
    stored = storage.store(BytesIO(source), max_byte_size=len(source))
    with unit_of_work_factory() as unit_of_work:
        project = unit_of_work.projects.add_project(
            ProjectCreate(
                slug=f"snapshot-worker-{uuid4().hex}",
                display_name="Snapshot worker fixture",
            )
        )
        artifact = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="source_tei",
                storage_uri=stored.storage_uri,
                sha256=stored.sha256,
                byte_size=stored.byte_size,
                media_type="application/tei+xml",
                project_id=project.id,
            )
        )
        import_config = SnapshotImportConfig(profile=profile, limits=SnapshotImportLimits())
        snapshot = unit_of_work.projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=artifact.id,
                source_sha256=artifact.sha256,
                parser_version=version_for_snapshot_import(import_config),
                import_config=import_config.model_dump(mode="json"),
            )
        )
        unit_of_work.projects.add_snapshot_source_members(
            snapshot.id,
            [
                SnapshotSourceMemberCreate(
                    artifact_id=artifact.id,
                    ordinal=0,
                    logical_name="register.xml",
                    sha256=artifact.sha256,
                    byte_size=artifact.byte_size,
                    media_type=artifact.media_type,
                )
            ],
        )
        unit_of_work.commit()
    return snapshot.id


def _executor(
    unit_of_work_factory: UnitOfWorkFactory,
    storage: LocalArtifactStorage,
) -> SnapshotImportExecutor:
    return SnapshotImportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        parser=TeiPersonParser(),
        clock=lambda: NOW,
        import_batch_record_count=1,
    )


def _creator_id(unit_of_work_factory: UnitOfWorkFactory) -> UUID:
    with unit_of_work_factory() as unit_of_work:
        creator = unit_of_work.users.add_user(UserCreate(display_name="Project creator"))
        unit_of_work.commit()
    return creator.id


def test_snapshot_acceptance_rolls_back_every_flushed_database_row(
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = create_session_factory(postgres_engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    storage = LocalArtifactStorage(tmp_path)
    service = ProjectService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        parser=TeiPersonParser(),
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
        max_upload_bytes=len(VALID_TEI),
    )
    project = service.create_project(
        ProjectCreate(
            slug=f"snapshot-acceptance-{uuid4().hex}",
            display_name="Snapshot acceptance fixture",
        ),
        creator_user_id=_creator_id(unit_of_work_factory),
    )

    flushed = _FlushedAcceptance()
    ensure_snapshot_dispatch = SqlAlchemyDispatchRepository._ensure_snapshot_dispatch

    def fail_after_outbox_flush(
        repository: SqlAlchemyDispatchRepository,
        command: SnapshotDispatchCreate,
    ) -> SnapshotDispatch:
        dispatch = ensure_snapshot_dispatch(repository, command)
        snapshot_row = repository._session.get(DatasetSnapshotRow, command.dataset_snapshot_id)
        assert snapshot_row is not None
        artifact_row = repository._session.get(ArtifactRow, snapshot_row.source_artifact_id)
        assert artifact_row is not None
        flushed.artifact_id = artifact_row.id
        flushed.snapshot_id = snapshot_row.id
        flushed.dispatch_id = dispatch.id
        flushed.storage_uri = artifact_row.storage_uri
        raise RuntimeError("injected failure after snapshot dispatch flush")

    monkeypatch.setattr(
        SqlAlchemyDispatchRepository,
        "_ensure_snapshot_dispatch",
        fail_after_outbox_flush,
    )

    with pytest.raises(RuntimeError, match="injected failure after snapshot dispatch flush"):
        service.import_snapshot(
            project_id=project.id,
            source=BytesIO(VALID_TEI),
            command=SnapshotImportRequest(),
        )

    assert flushed.artifact_id is not None
    assert flushed.snapshot_id is not None
    assert flushed.dispatch_id is not None
    assert flushed.storage_uri is not None
    with unit_of_work_factory() as unit_of_work:
        assert unit_of_work.projects.get_project(project.id) is not None
        assert unit_of_work.artifacts.get_artifact(flushed.artifact_id) is None
        assert unit_of_work.projects.get_snapshot(flushed.snapshot_id) is None
        assert unit_of_work.dispatches.get_dispatch(flushed.dispatch_id) is None

    # Storage and PostgreSQL have separate transaction boundaries. The exact
    # staged bytes remain as an unreferenced content-addressed blob for GC.
    with storage.open(flushed.storage_uri) as orphaned_source:
        assert orphaned_source.read() == VALID_TEI


@pytest.mark.parametrize(
    "legacy_profile",
    [
        TeiImportProfile.tei_p5_person_register_v1,
        TeiImportProfile.tei_p5_person_register_v2,
    ],
)
def test_snapshot_import_is_atomic_and_duplicate_delivery_is_a_noop(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
    tmp_path: Path,
    legacy_profile: TeiImportProfile,
) -> None:
    unit_of_work_factory, _ = postgres_unit_of_work
    storage = LocalArtifactStorage(tmp_path)
    snapshot_id = _seed_snapshot(
        unit_of_work_factory,
        storage,
        VALID_TEI,
        profile=legacy_profile,
    )
    executor = _executor(unit_of_work_factory, storage)
    message = SnapshotImportTaskMessage(dataset_snapshot_id=snapshot_id)

    completed = executor.execute(message, attempt_count=1)
    duplicate = executor.execute(message, attempt_count=2)

    assert completed.status is DatasetSnapshotStatus.ready
    assert completed.record_count == 2
    assert duplicate == completed
    with unit_of_work_factory() as unit_of_work:
        people = unit_of_work.projects.list_person_records(snapshot_id, limit=10)
    assert [person.tei_id for person in people] == ["p1", "p2"]
    assert all(person.source_member_name == "register.xml" for person in people)
    assert [person.source_record_locator for person in people] == ["xml:id=p1", "xml:id=p2"]


def test_loose_tei_acceptance_and_import_round_trip_source_provenance(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
    tmp_path: Path,
) -> None:
    unit_of_work_factory, _ = postgres_unit_of_work
    storage = LocalArtifactStorage(tmp_path)
    service = ProjectService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        parser=TeiPersonParser(),
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
        max_upload_bytes=100_000,
        max_total_upload_bytes=200_000,
    )
    project = service.create_project(
        ProjectCreate(
            slug=f"loose-snapshot-{uuid4().hex}",
            display_name="Loose snapshot fixture",
        ),
        creator_user_id=_creator_id(unit_of_work_factory),
    )
    a_source = VALID_TEI.replace(b'xml:id="p2"', b'xml:id="a2"')
    b_source = VALID_TEI.replace(b'xml:id="p1"', b'xml:id="b1"')
    snapshot = service.import_snapshot(
        project_id=project.id,
        command=SnapshotImportRequest(packaging=SourcePackaging.loose),
        sources=[
            SnapshotUpload(source=BytesIO(b_source), filename="B.xml"),
            SnapshotUpload(source=BytesIO(a_source), filename="A.xml"),
        ],
    )

    completed = _executor(unit_of_work_factory, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=snapshot.id),
        attempt_count=1,
    )

    assert completed.status is DatasetSnapshotStatus.ready
    assert completed.record_count == 4
    with unit_of_work_factory() as unit_of_work:
        members = unit_of_work.projects.list_snapshot_source_members(snapshot.id)
        people = unit_of_work.projects.list_person_records(snapshot.id, limit=10)
    assert [member.logical_name for member in members] == ["A.xml", "B.xml"]
    assert [(person.tei_id, person.source_member_name) for person in people] == [
        ("a2", "A.xml"),
        ("b1", "B.xml"),
        ("p1", "A.xml"),
        ("p2", "B.xml"),
    ]
    assert [person.source_record_locator for person in people] == [
        "xml:id=a2",
        "xml:id=b1",
        "xml:id=p1",
        "xml:id=p2",
    ]


def test_json_acceptance_and_import_round_trip_tei_equivalent_fields(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
    tmp_path: Path,
) -> None:
    unit_of_work_factory, _ = postgres_unit_of_work
    storage = LocalArtifactStorage(tmp_path)
    service = ProjectService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        parser=TeiPersonParser(),
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
        max_upload_bytes=100_000,
    )
    project = service.create_project(
        ProjectCreate(
            slug=f"json-snapshot-{uuid4().hex}",
            display_name="JSON snapshot fixture",
        ),
        creator_user_id=_creator_id(unit_of_work_factory),
    )
    payload = json.dumps(
        [
            {
                "xml:id": "json-p1",
                "persName": [
                    {
                        "type": "reg",
                        "surname": "Example",
                        "forename": ["Anna", "Maria"],
                    },
                    {"type": "alt", "name": "A. Example"},
                ],
                "birth": "um 1810",
                "death": None,
                "event": [{"type": "wedding", "when": "1832-09-20"}],
                "note": "Scholar",
                "idno": [
                    {"type": "uri", "value": "https://d-nb.info/gnd/123456789"},
                    {"type": "uri", "value": "https://viaf.org/viaf/98765"},
                ],
            }
        ]
    ).encode()
    snapshot = service.import_snapshot(
        project_id=project.id,
        command=SnapshotImportRequest(
            source_format=SourceFormat.json,
            profile=TabularImportProfile.tei_equivalent_person_register_v1,
        ),
        sources=[SnapshotUpload(source=BytesIO(payload), filename="people.json")],
    )

    completed = _executor(unit_of_work_factory, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=snapshot.id),
        attempt_count=1,
    )

    assert completed.status is DatasetSnapshotStatus.ready
    with unit_of_work_factory() as unit_of_work:
        [person] = unit_of_work.projects.list_person_records(snapshot.id, limit=10)
    assert person.forenames == ["Anna", "Maria"]
    assert person.alt_names == ["A. Example"]
    assert person.gnd_id == "123456789"
    assert person.external_ids == {"viaf": "98765"}
    assert [event.model_dump(mode="json") for event in person.events] == [
        {"type": "wedding", "when": "1832-09-20", "note": None}
    ]
    assert person.source_member_name == "people.json"
    assert person.source_record_locator == "row:1"


def test_concurrent_snapshot_import_deliveries_claim_and_write_exactly_once(
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit_of_work_factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    storage = LocalArtifactStorage(tmp_path)
    snapshot_id = _seed_snapshot(unit_of_work_factory, storage, VALID_TEI)
    executor = _executor(unit_of_work_factory, storage)
    message = SnapshotImportTaskMessage(dataset_snapshot_id=snapshot_id)

    winner_flushed_person = Event()
    release_winner = Event()
    competitor_entered_claim = Event()
    observation_lock = Lock()
    claim_outcomes: list[tuple[str, bool]] = []
    person_write_calls: list[tuple[str, tuple[str, ...]]] = []
    competitor_backend_pids: list[int] = []
    original_claim = SqlAlchemyProjectRepository.claim_snapshot_import
    original_add_people = SqlAlchemyProjectRepository.add_imported_person_records

    def observed_claim(
        repository: SqlAlchemyProjectRepository,
        requested_snapshot_id: UUID,
    ) -> DatasetSnapshot | None:
        if winner_flushed_person.is_set() and not release_winner.is_set():
            backend_pid = repository._session.scalar(select(func.pg_backend_pid()))
            assert isinstance(backend_pid, int)
            with observation_lock:
                competitor_backend_pids.append(backend_pid)
            competitor_entered_claim.set()
        claimed = original_claim(repository, requested_snapshot_id)
        with observation_lock:
            claim_outcomes.append((current_thread().name, claimed is not None))
        return claimed

    def pause_after_first_person_write(
        repository: SqlAlchemyProjectRepository,
        requested_snapshot_id: UUID,
        people: Sequence[ImportedPerson],
    ) -> int:
        added = original_add_people(repository, requested_snapshot_id, people)
        with observation_lock:
            person_write_calls.append(
                (
                    current_thread().name,
                    tuple(imported.person.tei_id for imported in people),
                )
            )
            is_first_write = len(person_write_calls) == 1
        if is_first_write:
            winner_flushed_person.set()
            if not release_winner.wait(timeout=10):
                msg = "test did not release the winning snapshot-import transaction"
                raise TimeoutError(msg)
        return added

    monkeypatch.setattr(
        SqlAlchemyProjectRepository,
        "claim_snapshot_import",
        observed_claim,
    )
    monkeypatch.setattr(
        SqlAlchemyProjectRepository,
        "add_imported_person_records",
        pause_after_first_person_write,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(executor.execute, message, attempt_count=1)
        try:
            assert winner_flushed_person.wait(timeout=10)
            competitor = pool.submit(executor.execute, message, attempt_count=1)
            assert competitor_entered_claim.wait(timeout=10)
            with observation_lock:
                assert len(competitor_backend_pids) == 1
                competitor_backend_pid = competitor_backend_pids[0]
            observed_lock_wait = False
            deadline = monotonic() + 10
            while monotonic() < deadline:
                with postgres_engine.connect() as observer:
                    wait_event_type = observer.execute(
                        text(
                            "SELECT wait_event_type FROM pg_stat_activity WHERE pid = :backend_pid"
                        ),
                        {"backend_pid": competitor_backend_pid},
                    ).scalar_one_or_none()
                if wait_event_type == "Lock":
                    observed_lock_wait = True
                    break
                sleep(0.01)
            assert observed_lock_wait
        finally:
            release_winner.set()
        winner_result = winner.result(timeout=10)
        competitor_result = competitor.result(timeout=10)

    assert winner_result.status is DatasetSnapshotStatus.ready
    assert winner_result.record_count == 2
    assert competitor_result == winner_result
    assert sorted(claimed for _thread, claimed in claim_outcomes) == [False, True]
    successful_claim_threads = {thread_name for thread_name, claimed in claim_outcomes if claimed}
    assert len(successful_claim_threads) == 1
    (writer_thread,) = successful_claim_threads
    assert person_write_calls == [
        (writer_thread, ("p1",)),
        (writer_thread, ("p2",)),
    ]

    with unit_of_work_factory() as unit_of_work:
        persisted = unit_of_work.projects.get_snapshot(snapshot_id)
        people = unit_of_work.projects.list_person_records(snapshot_id, limit=10)
    assert persisted == winner_result
    assert [person.tei_id for person in people] == ["p1", "p2"]


def test_permanent_parse_failure_rolls_back_already_flushed_people(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, Connection],
    tmp_path: Path,
) -> None:
    unit_of_work_factory, _ = postgres_unit_of_work
    storage = LocalArtifactStorage(tmp_path)
    snapshot_id = _seed_snapshot(
        unit_of_work_factory,
        storage,
        INVALID_TEI_AFTER_PERSON,
    )

    failed = _executor(unit_of_work_factory, storage).execute(
        SnapshotImportTaskMessage(dataset_snapshot_id=snapshot_id),
        attempt_count=1,
    )

    assert failed.status is DatasetSnapshotStatus.failed
    assert failed.record_count is None
    assert failed.failure_diagnostic is not None
    assert "invalid TEI XML" in failed.failure_diagnostic
    with unit_of_work_factory() as unit_of_work:
        people = unit_of_work.projects.list_person_records(snapshot_id, limit=10)
    assert people == ()
