from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Self, cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.config.run import RunConfig
from gendertagger.domain.review_triage import CERTAINTY_TIER_TRIAGE_RANKS
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.aggregation import (
    AggregatedResult,
    AggregationCreateRequest,
    AggregationExecution,
    AggregationExecutionCreate,
    AggregationOutcome,
    ReferenceAggregationResult,
    VoteCounts,
)
from gendertagger.models.artifact import Artifact, ArtifactCreate
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
)
from gendertagger.models.dispatch import AggregationDispatchCreate, SnapshotDispatchCreate
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    DatasetSnapshotStatus,
    RunStatus,
)
from gendertagger.models.person import PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportRequest,
    SnapshotImportTaskMessage,
    SourceFormat,
    SourceManifestV1,
    SourcePackaging,
    TabularImportProfile,
)
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.models.review import (
    Annotation,
    AnnotationCreate,
    ReviewAction,
    ReviewItem,
    ReviewItemQuery,
    ReviewItemSort,
    ReviewWorkflowState,
)
from gendertagger.models.run import Progress, Run, RunCreate, RunCreateRequest
from gendertagger.services.aggregation_repository import AggregationRepository
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.artifact_repository import ArtifactRepository
from gendertagger.services.dispatch_repository import DispatchRepository
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.project_repository import ProjectRepository
from gendertagger.services.projects import (
    InvalidSnapshotSourceError,
    ProjectService,
    SnapshotUpload,
    SnapshotUploadTooLargeError,
)
from gendertagger.services.review_items import ReviewItemService
from gendertagger.services.review_repository import ReviewItemCursor, ReviewRepository
from gendertagger.services.run_repository import RunRepository
from gendertagger.services.runs import RunProvenance, RunService
from gendertagger.services.unit_of_work import UnitOfWork
from gendertagger.storage.local import LocalArtifactStorage

NOW = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)
PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-0000-0000-000000000001")
PERSON_IDS = (
    UUID("40000000-0000-0000-0000-000000000001"),
    UUID("40000000-0000-0000-0000-000000000002"),
    UUID("40000000-0000-0000-0000-000000000003"),
)
RUN_ID = UUID("50000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("60000000-0000-0000-0000-000000000001")
AGGREGATION_ID = UUID("80000000-0000-0000-0000-000000000001")
OTHER_AGGREGATION_ID = UUID("80000000-0000-0000-0000-000000000002")
RESULT_IDS = (
    UUID("90000000-0000-0000-0000-000000000001"),
    UUID("90000000-0000-0000-0000-000000000002"),
    UUID("90000000-0000-0000-0000-000000000003"),
)
ANNOTATION_ID = UUID("a0000000-0000-0000-0000-000000000001")
REVIEWER_ID = UUID("b0000000-0000-0000-0000-000000000001")

VALID_TEI = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0">
<text><body><listPerson>
<person xml:id="p3"><persName type="reg"><surname>Third</surname></persName></person>
<person xml:id="p1"><persName type="reg"><surname>First</surname></persName></person>
<person xml:id="p2"><persName type="reg"><surname>Second</surname></persName></person>
</listPerson></body></text></TEI>"""


class StubUnitOfWork:
    def __init__(
        self,
        *,
        projects: object | None = None,
        artifacts: object | None = None,
        runs: object | None = None,
        aggregations: object | None = None,
        dispatches: object | None = None,
        reviews: object | None = None,
    ) -> None:
        self._projects = projects if projects is not None else Mock(spec=ProjectRepository)
        self._artifacts = artifacts if artifacts is not None else Mock(spec=ArtifactRepository)
        self._runs = runs if runs is not None else Mock(spec=RunRepository)
        self._aggregations = (
            aggregations if aggregations is not None else Mock(spec=AggregationRepository)
        )
        self._dispatches = dispatches if dispatches is not None else Mock(spec=DispatchRepository)
        self._reviews = reviews if reviews is not None else Mock(spec=ReviewRepository)
        self.commit_count = 0
        self.rollback_count = 0

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
    def projects(self) -> ProjectRepository:
        return cast(ProjectRepository, self._projects)

    @property
    def artifacts(self) -> ArtifactRepository:
        return cast(ArtifactRepository, self._artifacts)

    @property
    def runs(self) -> RunRepository:
        return cast(RunRepository, self._runs)

    @property
    def aggregations(self) -> AggregationRepository:
        return cast(AggregationRepository, self._aggregations)

    @property
    def dispatches(self) -> DispatchRepository:
        return cast(DispatchRepository, self._dispatches)

    @property
    def reviews(self) -> ReviewRepository:
        return cast(ReviewRepository, self._reviews)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def factory(self) -> UnitOfWork:
        return cast(UnitOfWork, self)


def _project() -> Project:
    return Project(
        id=PROJECT_ID,
        slug="service-project",
        display_name="Service project",
        created_at=NOW,
    )


def _snapshot(status: DatasetSnapshotStatus) -> DatasetSnapshot:
    record_count = 3 if status is DatasetSnapshotStatus.ready else None
    ready_at = NOW if status is DatasetSnapshotStatus.ready else None
    failure_diagnostic = "invalid TEI" if status is DatasetSnapshotStatus.failed else None
    return DatasetSnapshot(
        id=SNAPSHOT_ID,
        project_id=PROJECT_ID,
        source_artifact_id=ARTIFACT_ID,
        source_sha256="a" * 64,
        parser_version="tei_parser_v1",
        import_config={"profile": "tei_p5_person_register_v1"},
        status=status,
        created_at=NOW,
        record_count=record_count,
        ready_at=ready_at,
        failure_diagnostic=failure_diagnostic,
    )


def _people() -> list[PersonRecord]:
    return [
        PersonRecord(
            id=person_id,
            dataset_snapshot_id=SNAPSHOT_ID,
            tei_id=f"p{index}",
            surname=f"Person {index}",
            created_at=NOW,
        )
        for index, person_id in enumerate(PERSON_IDS, start=1)
    ]


def _project_service(
    *,
    unit_of_work: StubUnitOfWork,
    artifact_root: Path,
    max_upload_bytes: int = 100_000,
    max_total_upload_bytes: int | None = None,
) -> ProjectService:
    return ProjectService(
        unit_of_work_factory=unit_of_work.factory,
        artifact_storage=LocalArtifactStorage(artifact_root),
        parser=TeiPersonParser(),
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
        max_upload_bytes=max_upload_bytes,
        max_total_upload_bytes=max_total_upload_bytes,
    )


def _configure_import_repositories(
    project_repository: Mock,
    artifact_repository: Mock,
) -> None:
    project_repository.get_project.return_value = _project()
    snapshot_commands: list[DatasetSnapshotCreate] = []

    def add_artifact(command: ArtifactCreate) -> Artifact:
        return Artifact(id=ARTIFACT_ID, created_at=NOW, **command.model_dump())

    def pending_snapshot() -> DatasetSnapshot:
        command = snapshot_commands[0]
        return DatasetSnapshot(
            id=SNAPSHOT_ID,
            status=DatasetSnapshotStatus.pending,
            created_at=NOW,
            **command.model_dump(),
        )

    def add_snapshot(command: DatasetSnapshotCreate) -> DatasetSnapshot:
        snapshot_commands.append(command)
        return pending_snapshot()

    artifact_repository.add_artifact.side_effect = add_artifact
    project_repository.add_snapshot.side_effect = add_snapshot


def test_project_service_validates_limits_and_project_resources(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    project_repository.add_project.return_value = _project()
    project_repository.get_project.side_effect = [_project(), None]
    unit_of_work = StubUnitOfWork(projects=project_repository)
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    created = service.create_project(
        ProjectCreate(slug="service-project", display_name="Service project")
    )
    assert created == _project()
    assert service.get_project(PROJECT_ID) == _project()
    with pytest.raises(ResourceNotFoundError, match=str(PROJECT_ID)):
        service.get_project(PROJECT_ID)
    assert unit_of_work.commit_count == 1

    with pytest.raises(ValueError, match="max_upload_bytes must be positive"):
        _project_service(
            unit_of_work=unit_of_work,
            artifact_root=tmp_path,
            max_upload_bytes=0,
        )
    with pytest.raises(ValueError, match="max_total_upload_bytes must be positive"):
        _project_service(
            unit_of_work=unit_of_work,
            artifact_root=tmp_path,
            max_total_upload_bytes=0,
        )


def test_project_service_reads_snapshots_and_paginates_ready_people(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    project_repository.get_snapshot.return_value = _snapshot(DatasetSnapshotStatus.ready)
    project_repository.list_person_records.side_effect = [_people(), [_people()[2]]]
    unit_of_work = StubUnitOfWork(projects=project_repository)
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    assert service.get_snapshot(SNAPSHOT_ID).status is DatasetSnapshotStatus.ready
    first_page = service.list_people(SNAPSHOT_ID, limit=2, cursor=None)
    second_page = service.list_people(
        SNAPSHOT_ID,
        limit=2,
        cursor=first_page.next_cursor,
    )

    assert [person.tei_id for person in first_page.items] == ["p1", "p2"]
    assert first_page.has_more is True
    assert first_page.next_cursor is not None
    assert [person.tei_id for person in second_page.items] == ["p3"]
    assert second_page.has_more is False
    assert second_page.next_cursor is None
    with pytest.raises(ValueError, match="limit must be positive"):
        service.list_people(SNAPSHOT_ID, limit=0, cursor=None)

    project_repository.get_snapshot.return_value = _snapshot(DatasetSnapshotStatus.pending)
    with pytest.raises(InvalidResourceStateError, match="is not ready"):
        service.list_people(SNAPSHOT_ID, limit=1, cursor=None)
    project_repository.get_snapshot.return_value = None
    with pytest.raises(ResourceNotFoundError, match=str(SNAPSHOT_ID)):
        service.get_snapshot(SNAPSHOT_ID)


def test_project_service_stages_upload_and_atomically_queues_snapshot(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    artifact_repository = Mock(spec=ArtifactRepository)
    dispatch_repository = Mock(spec=DispatchRepository)
    _configure_import_repositories(project_repository, artifact_repository)
    project_repository.get_project.return_value = _project()
    unit_of_work = StubUnitOfWork(
        projects=project_repository,
        artifacts=artifact_repository,
        dispatches=dispatch_repository,
    )
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    snapshot = service.import_snapshot(
        project_id=PROJECT_ID,
        source=BytesIO(VALID_TEI),
        command=SnapshotImportRequest(),
    )

    assert snapshot.status is DatasetSnapshotStatus.pending
    project_repository.add_person_records.assert_not_called()
    project_repository.begin_snapshot_import.assert_not_called()
    artifact_command = artifact_repository.add_artifact.call_args.args[0]
    assert artifact_command.project_id == PROJECT_ID
    assert artifact_command.sha256 == snapshot.source_sha256
    with LocalArtifactStorage(tmp_path).open(artifact_command.storage_uri) as stored_source:
        assert stored_source.read() == VALID_TEI
    snapshot_command = project_repository.add_snapshot.call_args.args[0]
    assert snapshot_command.parser_version == (
        "tei_parser_v3+tei_collection_v1+tei_single_source_v1"
    )
    import_config = SnapshotImportConfig.model_validate(snapshot_command.import_config)
    assert import_config.profile.value == "tei_p5_person_register_v3"
    assert import_config.source_format.value == "tei"
    assert import_config.packaging.value == "single"
    assert import_config.limits.max_member_expanded_bytes == 100_000
    source_member_command = project_repository.add_snapshot_source_members.call_args.args
    assert source_member_command[0] == SNAPSHOT_ID
    assert [member.logical_name for member in source_member_command[1]] == ["source.xml"]
    dispatch_command = dispatch_repository.ensure_dispatch.call_args.args[0]
    assert dispatch_command == SnapshotDispatchCreate(
        dataset_snapshot_id=SNAPSHOT_ID,
        queue_name=CPU_QUEUE,
        payload=SnapshotImportTaskMessage(dataset_snapshot_id=SNAPSHOT_ID),
        available_at=NOW,
    )
    assert unit_of_work.commit_count == 1


def test_project_service_does_not_parse_invalid_tei_before_acceptance(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    artifact_repository = Mock(spec=ArtifactRepository)
    dispatch_repository = Mock(spec=DispatchRepository)
    _configure_import_repositories(project_repository, artifact_repository)
    project_repository.get_project.return_value = _project()
    unit_of_work = StubUnitOfWork(
        projects=project_repository,
        artifacts=artifact_repository,
        dispatches=dispatch_repository,
    )
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    snapshot = service.import_snapshot(
        project_id=PROJECT_ID,
        source=BytesIO(b"<not-tei/>"),
        command=SnapshotImportRequest(),
    )

    assert snapshot.status is DatasetSnapshotStatus.pending
    project_repository.fail_snapshot_import.assert_not_called()
    assert unit_of_work.commit_count == 1


def test_project_service_does_not_commit_without_durable_dispatch(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    artifact_repository = Mock(spec=ArtifactRepository)
    dispatch_repository = Mock(spec=DispatchRepository)
    _configure_import_repositories(project_repository, artifact_repository)
    project_repository.get_project.return_value = _project()
    dispatch_repository.ensure_dispatch.side_effect = RuntimeError("outbox unavailable")
    unit_of_work = StubUnitOfWork(
        projects=project_repository,
        artifacts=artifact_repository,
        dispatches=dispatch_repository,
    )
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        service.import_snapshot(
            project_id=PROJECT_ID,
            source=BytesIO(VALID_TEI),
            command=SnapshotImportRequest(),
        )

    assert unit_of_work.commit_count == 0


def test_project_service_builds_deterministic_loose_source_manifest(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    artifact_repository = Mock(spec=ArtifactRepository)
    dispatch_repository = Mock(spec=DispatchRepository)
    _configure_import_repositories(project_repository, artifact_repository)
    project_repository.get_project.return_value = _project()
    unit_of_work = StubUnitOfWork(
        projects=project_repository,
        artifacts=artifact_repository,
        dispatches=dispatch_repository,
    )
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    service.import_snapshot(
        project_id=PROJECT_ID,
        sources=[
            SnapshotUpload(source=BytesIO(b"letter B"), filename="B.xml"),
            SnapshotUpload(source=BytesIO(b"letter A"), filename="A.xml"),
        ],
        command=SnapshotImportRequest(packaging=SourcePackaging.loose),
    )

    artifact_commands = [call.args[0] for call in artifact_repository.add_artifact.call_args_list]
    assert [command.metadata["logical_name"] for command in artifact_commands[:2]] == [
        "A.xml",
        "B.xml",
    ]
    assert artifact_commands[2].logical_type == "source_manifest"
    with LocalArtifactStorage(tmp_path).open(artifact_commands[2].storage_uri) as stored_manifest:
        manifest_bytes = stored_manifest.read()
    manifest = SourceManifestV1.model_validate_json(manifest_bytes)
    assert [member.logical_name for member in manifest.members] == ["A.xml", "B.xml"]
    assert manifest.canonical_bytes() == manifest_bytes
    source_member_commands = project_repository.add_snapshot_source_members.call_args.args[1]
    assert [member.logical_name for member in source_member_commands] == [
        "A.xml",
        "B.xml",
    ]


def test_project_service_uses_snapshot_import_version_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_repository = Mock(spec=ProjectRepository)
    artifact_repository = Mock(spec=ArtifactRepository)
    dispatch_repository = Mock(spec=DispatchRepository)
    _configure_import_repositories(project_repository, artifact_repository)
    project_repository.get_project.return_value = _project()
    unit_of_work = StubUnitOfWork(
        projects=project_repository,
        artifacts=artifact_repository,
        dispatches=dispatch_repository,
    )
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)
    resolved_version = "tabular-test-version"

    def resolve_version(command: SnapshotImportRequest) -> str:
        del command
        return resolved_version

    monkeypatch.setattr(
        "gendertagger.services.projects.version_for_snapshot_import",
        resolve_version,
    )

    service.import_snapshot(
        project_id=PROJECT_ID,
        sources=[SnapshotUpload(source=BytesIO(b"[]"), filename="people.json")],
        command=SnapshotImportRequest(
            source_format=SourceFormat.json,
            profile=TabularImportProfile.tei_equivalent_person_register_v1,
        ),
    )

    snapshot_command = project_repository.add_snapshot.call_args.args[0]
    assert snapshot_command.parser_version == resolved_version


def test_project_service_distinguishes_malformed_sources_from_aggregate_overflow(
    tmp_path: Path,
) -> None:
    project_repository = Mock(spec=ProjectRepository)
    project_repository.get_project.return_value = _project()
    unit_of_work = StubUnitOfWork(projects=project_repository)
    service = _project_service(
        unit_of_work=unit_of_work,
        artifact_root=tmp_path,
        max_upload_bytes=10,
        max_total_upload_bytes=10,
    )

    with pytest.raises(InvalidSnapshotSourceError, match="collide"):
        service.import_snapshot(
            project_id=PROJECT_ID,
            sources=[
                SnapshotUpload(source=BytesIO(b"one"), filename="A.xml"),
                SnapshotUpload(source=BytesIO(b"two"), filename="a.XML"),
            ],
            command=SnapshotImportRequest(packaging=SourcePackaging.loose),
        )

    with pytest.raises(InvalidSnapshotSourceError, match="basenames collide"):
        service.import_snapshot(
            project_id=PROJECT_ID,
            sources=[
                SnapshotUpload(source=BytesIO(b"one"), filename="one/A.xml"),
                SnapshotUpload(source=BytesIO(b"two"), filename="two/a.XML"),
            ],
            command=SnapshotImportRequest(packaging=SourcePackaging.loose),
        )

    with pytest.raises(InvalidSnapshotSourceError, match="control character"):
        service.import_snapshot(
            project_id=PROJECT_ID,
            sources=[
                SnapshotUpload(source=BytesIO(b"one"), filename="A\u202e.xml"),
            ],
            command=SnapshotImportRequest(packaging=SourcePackaging.loose),
        )

    with pytest.raises(SnapshotUploadTooLargeError, match="aggregate upload limit"):
        service.import_snapshot(
            project_id=PROJECT_ID,
            sources=[
                SnapshotUpload(source=BytesIO(b"123456"), filename="A.xml"),
                SnapshotUpload(source=BytesIO(b"abcdef"), filename="B.xml"),
            ],
            command=SnapshotImportRequest(packaging=SourcePackaging.loose),
        )


def _run(command: RunCreate) -> Run:
    return Run(
        id=RUN_ID,
        status=RunStatus.created,
        config_sha256=command.resolved_config.canonical_sha256(),
        created_at=NOW,
        progress=Progress(),
        **command.model_dump(),
    )


def test_run_service_resolves_server_provenance_and_reads_resources() -> None:
    run_repository = Mock(spec=RunRepository)
    run_repository.add_run.side_effect = _run
    unit_of_work = StubUnitOfWork(runs=run_repository)
    service = RunService(
        unit_of_work_factory=unit_of_work.factory,
        method_registry=MethodRegistry([]),
        provenance=RunProvenance(
            code_git_commit="c" * 40,
            application_version="0.0.0",
            python_version="3.13.14",
            dependency_lock_sha256="d" * 64,
        ),
    )

    created = service.create_run(
        RunCreateRequest(dataset_snapshot_id=SNAPSHOT_ID, config=RunConfig(methods=[]))
    )
    run_repository.get_run.side_effect = [created, None]

    assert created.code_git_commit == "c" * 40
    assert created.resolved_config.methods == []
    assert service.get_run(RUN_ID) == created
    with pytest.raises(ResourceNotFoundError, match=str(RUN_ID)):
        service.get_run(RUN_ID)
    assert unit_of_work.commit_count == 1


def _aggregation(
    command: AggregationExecutionCreate,
    *,
    status: AggregationExecutionStatus = AggregationExecutionStatus.pending,
) -> AggregationExecution:
    started_at = NOW if status is AggregationExecutionStatus.completed else None
    finished_at = NOW if status is AggregationExecutionStatus.completed else None
    return AggregationExecution(
        id=AGGREGATION_ID,
        status=status,
        config_sha256=command.canonical_config_sha256(),
        created_at=NOW,
        **command.model_dump(),
        started_at=started_at,
        finished_at=finished_at,
    )


def _aggregation_result(
    index: int,
    *,
    aggregation_id: UUID = AGGREGATION_ID,
) -> AggregatedResult:
    scientific_result = ReferenceAggregationResult(
        outcome=AggregationOutcome.decided,
        label=CanonicalLabel.female,
        pooled_vote_counts=VoteCounts(female=1),
        agreement_score=1.0,
        agreement_tier=AgreementTier.single_rater,
        certainty_tier=CertaintyTier.uncertain,
    )
    return AggregatedResult(
        id=RESULT_IDS[index],
        aggregation_execution_id=aggregation_id,
        person_record_id=PERSON_IDS[index],
        created_at=NOW,
        **scientific_result.model_dump(),
    )


def test_aggregation_service_creates_and_scopes_resources() -> None:
    aggregation_repository = Mock(spec=AggregationRepository)
    aggregation_repository.add_aggregation.side_effect = _aggregation
    aggregation_repository.mark_aggregation_queued.side_effect = lambda _aggregation_id: (
        _aggregation(
            AggregationExecutionCreate(
                run_id=RUN_ID,
                method_execution_ids=(EXECUTION_ID,),
            ),
            status=AggregationExecutionStatus.queued,
        )
    )
    dispatch_repository = Mock(spec=DispatchRepository)
    unit_of_work = StubUnitOfWork(
        aggregations=aggregation_repository,
        dispatches=dispatch_repository,
    )
    service = AggregationService(
        unit_of_work_factory=unit_of_work.factory,
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
    )
    command = AggregationCreateRequest(method_execution_ids=(EXECUTION_ID,))

    created = service.create_aggregation(run_id=RUN_ID, command=command)
    assert created.status is AggregationExecutionStatus.queued
    aggregation_repository.get_aggregation.side_effect = [created, None]
    assert service.get_aggregation(AGGREGATION_ID) == created
    with pytest.raises(ResourceNotFoundError, match=str(AGGREGATION_ID)):
        service.get_aggregation(AGGREGATION_ID)

    aggregation_repository.get_result.return_value = _aggregation_result(0)
    assert (
        service.get_result(aggregation_id=AGGREGATION_ID, result_id=RESULT_IDS[0]).id
        == RESULT_IDS[0]
    )
    aggregation_repository.get_result.return_value = _aggregation_result(
        0,
        aggregation_id=OTHER_AGGREGATION_ID,
    )
    with pytest.raises(ResourceNotFoundError, match=str(RESULT_IDS[0])):
        service.get_result(aggregation_id=AGGREGATION_ID, result_id=RESULT_IDS[0])
    aggregation_repository.get_result.return_value = None
    with pytest.raises(ResourceNotFoundError, match=str(RESULT_IDS[0])):
        service.get_result(aggregation_id=AGGREGATION_ID, result_id=RESULT_IDS[0])
    dispatch_repository.ensure_dispatch.assert_called_once()
    dispatch_command = cast(
        AggregationDispatchCreate,
        dispatch_repository.ensure_dispatch.call_args.args[0],
    )
    assert dispatch_command.aggregation_execution_id == AGGREGATION_ID
    assert dispatch_command.payload.aggregation_execution_id == AGGREGATION_ID
    assert dispatch_command.queue_name == "cpu"
    assert dispatch_command.available_at == NOW
    assert unit_of_work.commit_count == 1


def test_aggregation_service_does_not_queue_or_commit_without_durable_dispatch() -> None:
    aggregation_repository = Mock(spec=AggregationRepository)
    aggregation_repository.add_aggregation.side_effect = _aggregation
    dispatch_repository = Mock(spec=DispatchRepository)
    dispatch_repository.ensure_dispatch.side_effect = RuntimeError("dispatch persistence failed")
    unit_of_work = StubUnitOfWork(
        aggregations=aggregation_repository,
        dispatches=dispatch_repository,
    )
    service = AggregationService(
        unit_of_work_factory=unit_of_work.factory,
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="dispatch persistence failed"):
        service.create_aggregation(
            run_id=RUN_ID,
            command=AggregationCreateRequest(method_execution_ids=(EXECUTION_ID,)),
        )

    aggregation_repository.mark_aggregation_queued.assert_not_called()
    assert unit_of_work.commit_count == 0


def test_aggregation_service_paginates_and_rejects_malformed_cursor_position() -> None:
    aggregation_repository = Mock(spec=AggregationRepository)
    command = AggregationExecutionCreate(
        run_id=RUN_ID,
        method_execution_ids=(EXECUTION_ID,),
    )
    aggregation_repository.get_aggregation.return_value = _aggregation(command)
    results = [_aggregation_result(index) for index in range(3)]
    aggregation_repository.list_results.side_effect = [results, [results[2]]]
    unit_of_work = StubUnitOfWork(aggregations=aggregation_repository)
    cursor_codec = CursorCodec()
    service = AggregationService(
        unit_of_work_factory=unit_of_work.factory,
        cursor_codec=cursor_codec,
        clock=lambda: NOW,
    )

    first_page = service.list_results(AGGREGATION_ID, limit=2, cursor=None)
    second_page = service.list_results(
        AGGREGATION_ID,
        limit=2,
        cursor=first_page.next_cursor,
    )

    assert [result.id for result in first_page.items] == list(RESULT_IDS[:2])
    assert first_page.has_more is True
    assert first_page.next_cursor is not None
    assert [result.id for result in second_page.items] == [RESULT_IDS[2]]
    assert second_page.has_more is False
    with pytest.raises(ValueError, match="limit must be positive"):
        service.list_results(AGGREGATION_ID, limit=0, cursor=None)

    invalid_position = cursor_codec.encode(
        resource=f"aggregation_results:{AGGREGATION_ID}",
        sort_values=("not-a-uuid",),
        resource_id=RESULT_IDS[0],
    )
    with pytest.raises(InvalidCursorError, match="sort value is invalid"):
        service.list_results(
            AGGREGATION_ID,
            limit=1,
            cursor=invalid_position,
        )


def _review_item(index: int) -> ReviewItem:
    return ReviewItem(
        aggregation_execution_id=AGGREGATION_ID,
        aggregated_result_id=RESULT_IDS[index],
        snapshot_id=SNAPSHOT_ID,
        person_record_id=PERSON_IDS[index],
        tei_id=f"p{index + 1}",
        surname=f"Person {index + 1}",
        aggregation_outcome=AggregationOutcome.decided,
        machine_label=CanonicalLabel.female,
        final_label=CanonicalLabel.female,
        agreement_tier=AgreementTier.single_rater,
        certainty_tier=CertaintyTier.uncertain,
        has_authority_conflict=False,
        has_prediction_error=False,
        workflow_state=ReviewWorkflowState.unreviewed,
        review_revision=0,
    )


def test_review_item_service_requires_completed_aggregation_and_paginates() -> None:
    aggregation_repository = Mock(spec=AggregationRepository)
    review_repository = Mock(spec=ReviewRepository)
    command = AggregationExecutionCreate(
        run_id=RUN_ID,
        method_execution_ids=(EXECUTION_ID,),
    )
    aggregation_repository.get_aggregation.return_value = _aggregation(
        command,
        status=AggregationExecutionStatus.completed,
    )
    items = [_review_item(index) for index in range(3)]
    review_repository.list_review_items.side_effect = [items, [items[2]]]
    unit_of_work = StubUnitOfWork(
        aggregations=aggregation_repository,
        reviews=review_repository,
    )
    service = ReviewItemService(
        unit_of_work_factory=unit_of_work.factory,
        cursor_codec=CursorCodec(),
    )

    first_page = service.list_review_items(ReviewItemQuery(aggregation_id=AGGREGATION_ID, limit=2))
    second_page = service.list_review_items(
        ReviewItemQuery(
            aggregation_id=AGGREGATION_ID,
            limit=2,
            cursor=first_page.next_cursor,
        )
    )

    assert [item.tei_id for item in first_page.items] == ["p1", "p2"]
    assert first_page.has_more is True
    assert first_page.next_cursor is not None
    assert [item.tei_id for item in second_page.items] == ["p3"]
    assert second_page.has_more is False
    assert second_page.next_cursor is None

    continuation = review_repository.list_review_items.call_args_list[1].kwargs["after"]
    assert continuation == ReviewItemCursor(
        tei_id="p2",
        person_record_id=PERSON_IDS[1],
        triage_rank=CERTAINTY_TIER_TRIAGE_RANKS[CertaintyTier.uncertain],
    )
    with pytest.raises(InvalidCursorError):
        service.list_review_items(
            ReviewItemQuery(
                aggregation_id=AGGREGATION_ID,
                sort=ReviewItemSort.tei_id,
                cursor=first_page.next_cursor,
            )
        )

    aggregation_repository.get_aggregation.return_value = None
    with pytest.raises(ResourceNotFoundError, match=str(AGGREGATION_ID)):
        service.list_review_items(ReviewItemQuery(aggregation_id=AGGREGATION_ID))
    aggregation_repository.get_aggregation.return_value = _aggregation(command)
    with pytest.raises(InvalidResourceStateError, match="is not completed"):
        service.list_review_items(ReviewItemQuery(aggregation_id=AGGREGATION_ID))


def test_annotation_service_commits_attributable_append_only_decision() -> None:
    review_repository = Mock(spec=ReviewRepository)
    command = AnnotationCreate(
        snapshot_id=SNAPSHOT_ID,
        tei_id="p1",
        action=ReviewAction.correct,
        label=CanonicalLabel.female,
        aggregated_result_id=RESULT_IDS[0],
        expected_revision=0,
    )
    annotation = Annotation(
        id=ANNOTATION_ID,
        snapshot_id=SNAPSHOT_ID,
        person_record_id=PERSON_IDS[0],
        tei_id="p1",
        action=ReviewAction.correct,
        label=CanonicalLabel.female,
        reviewer_user_id=REVIEWER_ID,
        aggregated_result_id=RESULT_IDS[0],
        resulting_revision=1,
        created_at=NOW,
    )
    review_repository.add_annotation.return_value = annotation
    unit_of_work = StubUnitOfWork(reviews=review_repository)
    service = AnnotationService(unit_of_work.factory)

    created = service.create_annotation(command, reviewer_user_id=REVIEWER_ID)

    assert created == annotation
    assert review_repository.add_annotation.call_args.kwargs == {"reviewer_user_id": REVIEWER_ID}
    assert unit_of_work.commit_count == 1
