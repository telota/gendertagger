from collections.abc import Sequence
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Self, cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.config.run import RunConfig
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
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    DatasetSnapshotStatus,
    RunStatus,
)
from gendertagger.models.person import PersonInput, PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
    SnapshotImportRequest,
)
from gendertagger.models.review import (
    Annotation,
    AnnotationCreate,
    ReviewAction,
    ReviewItem,
    ReviewItemQuery,
    ReviewWorkflowState,
)
from gendertagger.models.run import Run, RunCreate, RunCreateRequest
from gendertagger.services.aggregation_repository import AggregationRepository
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.artifact_repository import ArtifactRepository
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.project_repository import ProjectRepository
from gendertagger.services.projects import ProjectService
from gendertagger.services.review_items import ReviewItemService
from gendertagger.services.review_repository import ReviewRepository
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
        reviews: object | None = None,
    ) -> None:
        self._projects = projects if projects is not None else Mock(spec=ProjectRepository)
        self._artifacts = artifacts if artifacts is not None else Mock(spec=ArtifactRepository)
        self._runs = runs if runs is not None else Mock(spec=RunRepository)
        self._aggregations = (
            aggregations if aggregations is not None else Mock(spec=AggregationRepository)
        )
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
    import_batch_record_count: int = 2,
) -> ProjectService:
    return ProjectService(
        unit_of_work_factory=unit_of_work.factory,
        artifact_storage=LocalArtifactStorage(artifact_root),
        parser=TeiPersonParser(),
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
        max_upload_bytes=max_upload_bytes,
        import_batch_record_count=import_batch_record_count,
    )


def _configure_import_repositories(
    project_repository: Mock,
    artifact_repository: Mock,
    *,
    terminal_status: DatasetSnapshotStatus,
) -> None:
    project_repository.get_project.return_value = _project()
    snapshot_commands: list[DatasetSnapshotCreate] = []

    def add_artifact(command: ArtifactCreate) -> Artifact:
        return Artifact(id=ARTIFACT_ID, created_at=NOW, **command.model_dump())

    def snapshot_with_status(
        status: DatasetSnapshotStatus,
        *,
        failure_diagnostic: str | None = None,
    ) -> DatasetSnapshot:
        command = snapshot_commands[0]
        record_count = 3 if status is DatasetSnapshotStatus.ready else None
        ready_at = NOW if status is DatasetSnapshotStatus.ready else None
        stored_failure_diagnostic = (
            failure_diagnostic or "invalid TEI" if status is DatasetSnapshotStatus.failed else None
        )
        return DatasetSnapshot(
            id=SNAPSHOT_ID,
            status=status,
            created_at=NOW,
            **command.model_dump(),
            record_count=record_count,
            ready_at=ready_at,
            failure_diagnostic=stored_failure_diagnostic,
        )

    def add_snapshot(command: DatasetSnapshotCreate) -> DatasetSnapshot:
        snapshot_commands.append(command)
        return snapshot_with_status(DatasetSnapshotStatus.pending)

    def begin_snapshot_import(snapshot_id: UUID) -> DatasetSnapshot:
        assert snapshot_id == SNAPSHOT_ID
        return snapshot_with_status(DatasetSnapshotStatus.importing)

    def complete_snapshot_import(
        snapshot_id: UUID,
        *,
        ready_at: datetime,
    ) -> DatasetSnapshot:
        assert snapshot_id == SNAPSHOT_ID
        assert ready_at == NOW
        return snapshot_with_status(DatasetSnapshotStatus.ready)

    def fail_snapshot_import(
        snapshot_id: UUID,
        *,
        failure_diagnostic: str,
    ) -> DatasetSnapshot:
        assert snapshot_id == SNAPSHOT_ID
        return snapshot_with_status(
            DatasetSnapshotStatus.failed,
            failure_diagnostic=failure_diagnostic,
        )

    artifact_repository.add_artifact.side_effect = add_artifact
    project_repository.add_snapshot.side_effect = add_snapshot
    project_repository.begin_snapshot_import.side_effect = begin_snapshot_import
    project_repository.complete_snapshot_import.side_effect = complete_snapshot_import
    project_repository.fail_snapshot_import.side_effect = fail_snapshot_import
    if terminal_status is DatasetSnapshotStatus.ready:
        project_repository.fail_snapshot_import.side_effect = AssertionError(
            "valid TEI must not fail"
        )
    else:
        project_repository.complete_snapshot_import.side_effect = AssertionError(
            "invalid TEI must not become ready"
        )


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
    with pytest.raises(ValueError, match="import_batch_record_count must be positive"):
        _project_service(
            unit_of_work=unit_of_work,
            artifact_root=tmp_path,
            import_batch_record_count=0,
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


def test_project_service_imports_valid_tei_in_bounded_batches(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    artifact_repository = Mock(spec=ArtifactRepository)
    _configure_import_repositories(
        project_repository,
        artifact_repository,
        terminal_status=DatasetSnapshotStatus.ready,
    )
    persisted_batches: list[list[str]] = []

    def persist_batch(
        snapshot_id: UUID,
        batch: Sequence[PersonInput],
    ) -> int:
        assert snapshot_id == SNAPSHOT_ID
        persisted_batches.append([person.tei_id for person in batch])
        return len(batch)

    project_repository.add_person_records.side_effect = persist_batch
    unit_of_work = StubUnitOfWork(
        projects=project_repository,
        artifacts=artifact_repository,
    )
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    snapshot = service.import_snapshot(
        project_id=PROJECT_ID,
        source=BytesIO(VALID_TEI),
        command=SnapshotImportRequest(),
    )

    assert snapshot.status is DatasetSnapshotStatus.ready
    assert persisted_batches == [["p3", "p1"], ["p2"]]
    artifact_command = artifact_repository.add_artifact.call_args.args[0]
    assert artifact_command.project_id == PROJECT_ID
    assert artifact_command.sha256 == snapshot.source_sha256
    assert unit_of_work.commit_count == 5


def test_project_service_persists_failed_snapshot_for_invalid_tei(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    artifact_repository = Mock(spec=ArtifactRepository)
    _configure_import_repositories(
        project_repository,
        artifact_repository,
        terminal_status=DatasetSnapshotStatus.failed,
    )
    unit_of_work = StubUnitOfWork(
        projects=project_repository,
        artifacts=artifact_repository,
    )
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    snapshot = service.import_snapshot(
        project_id=PROJECT_ID,
        source=BytesIO(b"<not-tei/>"),
        command=SnapshotImportRequest(),
    )

    assert snapshot.status is DatasetSnapshotStatus.failed
    diagnostic = project_repository.fail_snapshot_import.call_args.kwargs["failure_diagnostic"]
    assert diagnostic
    assert unit_of_work.commit_count == 3


def _run(command: RunCreate) -> Run:
    return Run(
        id=RUN_ID,
        status=RunStatus.created,
        config_sha256=command.resolved_config.canonical_sha256(),
        created_at=NOW,
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
    unit_of_work = StubUnitOfWork(aggregations=aggregation_repository)
    service = AggregationService(
        unit_of_work_factory=unit_of_work.factory,
        cursor_codec=CursorCodec(),
    )
    command = AggregationCreateRequest(method_execution_ids=(EXECUTION_ID,))

    created = service.create_aggregation(run_id=RUN_ID, command=command)
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
    assert unit_of_work.commit_count == 1


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
        sort_value="not-a-uuid",
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
