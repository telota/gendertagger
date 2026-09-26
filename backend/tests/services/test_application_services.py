import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Self, cast
from unittest.mock import Mock
from uuid import UUID, uuid4

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
from gendertagger.models.auth import LocalCredential, UserSession
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
)
from gendertagger.models.common import canonical_json_sha256
from gendertagger.models.dispatch import AggregationDispatchCreate, SnapshotDispatchCreate
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    DatasetSnapshotStatus,
    MethodExecutionStatus,
    RunStatus,
)
from gendertagger.models.person import PersonRecord
from gendertagger.models.project import (
    AccessibleProject,
    DatasetSnapshot,
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
    ProjectDataAvailability,
    SnapshotImportConfig,
    SnapshotImportRequest,
    SnapshotImportTaskMessage,
    SnapshotSourceMember,
    SourceFormat,
    SourceManifestV1,
    SourcePackaging,
)
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.models.review import (
    Annotation,
    AnnotationCreate,
    ReviewAction,
    ReviewItem,
    ReviewItemQuery,
    ReviewItemSort,
    ReviewSummary,
    ReviewSummaryGroup,
    ReviewWorkflowState,
)
from gendertagger.models.run import (
    MethodExecution,
    MethodExecutionResult,
    MethodExecutionResultQuery,
    MethodExecutionResultState,
    Progress,
    Run,
    RunCreate,
    RunCreateRequest,
)
from gendertagger.models.task import ProjectReviewResult
from gendertagger.models.team import TeamMember, TeamSummary
from gendertagger.models.user import CurrentUser, GlobalRole, ProjectRole, User, UserCreate
from gendertagger.services.aggregations import AggregationCreation, AggregationService
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.authentication import (
    AuthenticationService,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    SessionLifetimePolicy,
)
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.password_hashing import PasswordHasherProtocol
from gendertagger.services.ports.aggregation_repository import AggregationRepository
from gendertagger.services.ports.artifact_repository import ArtifactRepository
from gendertagger.services.ports.auth_repository import AuthRepository
from gendertagger.services.ports.dispatch_repository import DispatchRepository
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.project_access_repository import ProjectAccessRepository
from gendertagger.services.ports.project_repository import ProjectRepository
from gendertagger.services.ports.review_repository import (
    ReviewItemCursor,
    ReviewRepository,
    ReviewSummaryData,
)
from gendertagger.services.ports.run_repository import (
    MethodExecutionResultCursor,
    RunRepository,
)
from gendertagger.services.ports.team_repository import TeamRepository
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.ports.user_repository import UserRepository
from gendertagger.services.projects import (
    InvalidSnapshotSourceError,
    ProjectService,
    SnapshotUpload,
    SnapshotUploadTooLargeError,
)
from gendertagger.services.review_items import ReviewItemService
from gendertagger.services.runs import RunProvenance, RunService
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
        users: object | None = None,
        auth: object | None = None,
        access: object | None = None,
        teams: object | None = None,
    ) -> None:
        self._projects = projects if projects is not None else Mock(spec=ProjectRepository)
        self._artifacts = artifacts if artifacts is not None else Mock(spec=ArtifactRepository)
        self._runs = runs if runs is not None else Mock(spec=RunRepository)
        self._aggregations = (
            aggregations if aggregations is not None else Mock(spec=AggregationRepository)
        )
        self._dispatches = dispatches if dispatches is not None else Mock(spec=DispatchRepository)
        self._reviews = reviews if reviews is not None else Mock(spec=ReviewRepository)
        self._users = users if users is not None else Mock(spec=UserRepository)
        self._auth = auth if auth is not None else Mock(spec=AuthRepository)
        self._access = access if access is not None else Mock(spec=ProjectAccessRepository)
        self._teams = teams if teams is not None else Mock(spec=TeamRepository)
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

    @property
    def users(self) -> UserRepository:
        return cast(UserRepository, self._users)

    @property
    def auth(self) -> AuthRepository:
        return cast(AuthRepository, self._auth)

    @property
    def access(self) -> ProjectAccessRepository:
        return cast(ProjectAccessRepository, self._access)

    @property
    def teams(self) -> TeamRepository:
        return cast(TeamRepository, self._teams)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def factory(self) -> UnitOfWork:
        return cast(UnitOfWork, self)


def _project() -> Project:
    team = TeamSummary(
        id=UUID("10000000-0000-0000-0000-000000000004"),
        slug="service-team",
        display_name="Service team",
        created_at=NOW,
        updated_at=NOW,
    )
    return Project(
        id=PROJECT_ID,
        slug="service-project",
        display_name="Service project",
        team=team,
        manager_user_id=AUTH_USER_ID,
        created_by_user_id=AUTH_USER_ID,
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
        parser_version="tei_parser_v3",
        import_config={"profile": "tei_p5_person_register"},
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
    access_repository = Mock(spec=ProjectAccessRepository)
    user_repository = Mock(spec=UserRepository)
    team_repository = Mock(spec=TeamRepository)
    unit_of_work = StubUnitOfWork(
        projects=project_repository,
        access=access_repository,
        users=user_repository,
        teams=team_repository,
    )
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)
    creator = User(
        id=AUTH_USER_ID,
        display_name="Operator",
        roles={GlobalRole.operator},
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    team_repository.get_team_for_update.return_value = _project().team
    team_repository.get_member.return_value = TeamMember(
        team_id=_project().team.id,
        user_id=AUTH_USER_ID,
        display_name="Operator",
        is_active=True,
        created_at=NOW,
    )
    user_repository.get_user_for_update.return_value = creator

    created = service.create_project(
        ProjectCreate(
            slug="service-project",
            display_name="Service project",
            team_id=_project().team.id,
        ),
        creator=CurrentUser(
            id=AUTH_USER_ID,
            display_name="Operator",
            roles={GlobalRole.operator},
        ),
    )
    assert created == AccessibleProject(
        **_project().model_dump(),
        current_user_role=ProjectRole.operator,
        current_user_can_manage_members=True,
    )
    access_repository.set_member_role.assert_called_once_with(
        PROJECT_ID, AUTH_USER_ID, ProjectRole.operator
    )
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


def _method_execution(*, run_id: UUID = RUN_ID) -> MethodExecution:
    return MethodExecution(
        id=EXECUTION_ID,
        run_id=run_id,
        method_name="gender_guesser",
        implementation_version="gender_guesser_v1",
        normalization_version="gender_guesser_v1",
        resolved_config={},
        config_sha256="e" * 64,
        status=MethodExecutionStatus.completed,
        queue_name="cpu",
        total_count=2,
        completed_count=2,
        failed_count=0,
        created_at=NOW,
        progress=Progress.of(total=2, completed=2, failed=0),
    )


def test_run_service_lists_execution_results_with_filter_scoped_cursor() -> None:
    run_repository = Mock(spec=RunRepository)
    run_repository.get_run.return_value = _run(
        RunCreate(
            dataset_snapshot_id=SNAPSHOT_ID,
            resolved_config=RunConfig(methods=[]),
            code_git_commit="c" * 40,
            application_version="0.0.0",
            python_version="3.13.14",
            dependency_lock_sha256="d" * 64,
        )
    )
    run_repository.get_method_execution.return_value = _method_execution()
    results = [
        MethodExecutionResult(
            method_execution_id=EXECUTION_ID,
            dataset_snapshot_id=SNAPSHOT_ID,
            person_record_id=PERSON_IDS[0],
            tei_id="p1",
            result_state=MethodExecutionResultState.missing,
        ),
        MethodExecutionResult(
            method_execution_id=EXECUTION_ID,
            dataset_snapshot_id=SNAPSHOT_ID,
            person_record_id=PERSON_IDS[1],
            tei_id="p2",
            result_state=MethodExecutionResultState.missing,
        ),
    ]
    run_repository.list_method_execution_results.side_effect = [results, [results[1]]]
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
        cursor_codec=CursorCodec(),
    )

    first = service.list_execution_results(
        run_id=RUN_ID,
        method_execution_id=EXECUTION_ID,
        query=MethodExecutionResultQuery(limit=1, result_state=MethodExecutionResultState.missing),
    )
    second = service.list_execution_results(
        run_id=RUN_ID,
        method_execution_id=EXECUTION_ID,
        query=MethodExecutionResultQuery(
            limit=1,
            result_state=MethodExecutionResultState.missing,
            cursor=first.next_cursor,
        ),
    )

    assert first.items == [results[0]]
    assert first.has_more is True
    assert second.items == [results[1]]
    assert second.has_more is False
    assert run_repository.list_method_execution_results.call_args_list[0].args == (
        SNAPSHOT_ID,
        EXECUTION_ID,
    )
    assert run_repository.list_method_execution_results.call_args_list[0].kwargs["limit"] == 2
    assert run_repository.list_method_execution_results.call_args_list[1].kwargs["after"] == (
        MethodExecutionResultCursor(tei_id="p1", person_record_id=PERSON_IDS[0])
    )


def test_run_service_hides_an_execution_outside_its_parent_run() -> None:
    run_repository = Mock(spec=RunRepository)
    run_repository.get_run.return_value = _run(
        RunCreate(
            dataset_snapshot_id=SNAPSHOT_ID,
            resolved_config=RunConfig(methods=[]),
            code_git_commit="c" * 40,
            application_version="0.0.0",
            python_version="3.13.14",
            dependency_lock_sha256="d" * 64,
        )
    )
    run_repository.get_method_execution.return_value = _method_execution(run_id=uuid4())
    service = RunService(
        unit_of_work_factory=StubUnitOfWork(runs=run_repository).factory,
        method_registry=MethodRegistry([]),
        provenance=RunProvenance(
            code_git_commit="c" * 40,
            application_version="0.0.0",
            python_version="3.13.14",
            dependency_lock_sha256="d" * 64,
        ),
        cursor_codec=CursorCodec(),
    )

    with pytest.raises(ResourceNotFoundError, match=str(EXECUTION_ID)):
        service.list_execution_results(
            run_id=RUN_ID,
            method_execution_id=EXECUTION_ID,
            query=MethodExecutionResultQuery(),
        )
    run_repository.list_method_execution_results.assert_not_called()


def test_project_service_reads_availability_without_selecting_or_mutating_data(
    tmp_path: Path,
) -> None:
    project_repository = Mock(spec=ProjectRepository)
    availability = ProjectDataAvailability(
        project_id=PROJECT_ID,
        has_ready_snapshots=True,
        has_completed_aggregations=True,
    )
    project_repository.get_data_availability.side_effect = [availability, None]
    unit_of_work = StubUnitOfWork(projects=project_repository)
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    assert service.get_data_availability(PROJECT_ID) == availability
    with pytest.raises(ResourceNotFoundError, match=str(PROJECT_ID)):
        service.get_data_availability(PROJECT_ID)

    assert project_repository.get_data_availability.call_count == 2
    project_repository.get_data_availability.assert_called_with(PROJECT_ID)
    project_repository.list_snapshots.assert_not_called()
    project_repository.set_working_aggregation.assert_not_called()
    assert unit_of_work.commit_count == 0


def test_project_service_lists_review_results_as_project_scoped_pages(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    review_result = ProjectReviewResult(
        id=AGGREGATION_ID,
        created_at=NOW,
        aggregation=_aggregation(
            AggregationExecutionCreate(
                run_id=RUN_ID,
                method_execution_ids=(EXECUTION_ID,),
            ),
            status=AggregationExecutionStatus.completed,
        ),
        run=_run(
            RunCreate(
                dataset_snapshot_id=SNAPSHOT_ID,
                resolved_config=RunConfig(methods=[]),
                code_git_commit="c" * 40,
                application_version="0.0.0",
                python_version="3.13.14",
            )
        ).model_copy(update={"status": RunStatus.completed, "started_at": NOW, "finished_at": NOW}),
        snapshot=_snapshot(DatasetSnapshotStatus.ready),
    )
    project_repository.get_project.side_effect = [_project(), _project(), None]
    project_repository.list_review_results.side_effect = [[review_result, review_result], []]
    unit_of_work = StubUnitOfWork(projects=project_repository)
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    first = service.list_review_results(PROJECT_ID, limit=1, cursor=None)
    second = service.list_review_results(PROJECT_ID, limit=1, cursor=first.next_cursor)

    assert first.items == [review_result]
    assert first.has_more is True
    assert second.items == []
    assert project_repository.list_review_results.call_args_list[0].kwargs["limit"] == 2
    assert project_repository.list_review_results.call_args_list[1].kwargs["after"].id == (
        review_result.aggregation.id
    )
    with pytest.raises(ResourceNotFoundError, match=str(PROJECT_ID)):
        service.list_review_results(PROJECT_ID, limit=1, cursor=None)


def test_project_service_sets_working_aggregation_atomically(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    pointed_project = _project().model_copy(
        update={"working_aggregation_execution_id": AGGREGATION_ID}
    )
    project_repository.set_working_aggregation.return_value = pointed_project
    unit_of_work = StubUnitOfWork(projects=project_repository)
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    updated = service.set_working_aggregation(PROJECT_ID, aggregation_execution_id=AGGREGATION_ID)

    assert updated == pointed_project
    project_repository.set_working_aggregation.assert_called_once_with(
        PROJECT_ID,
        aggregation_execution_id=AGGREGATION_ID,
    )
    assert unit_of_work.commit_count == 1


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


def test_project_service_reads_one_ready_snapshot_person(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    person = _people()[0]
    project_repository.get_snapshot.return_value = _snapshot(DatasetSnapshotStatus.ready)
    project_repository.get_person_record_by_tei_id.return_value = person
    unit_of_work = StubUnitOfWork(projects=project_repository)
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    assert service.get_person(SNAPSHOT_ID, "p1") == person
    project_repository.get_person_record_by_tei_id.assert_called_once_with(SNAPSHOT_ID, "p1")

    project_repository.get_person_record_by_tei_id.return_value = None
    with pytest.raises(ResourceNotFoundError, match="'missing'"):
        service.get_person(SNAPSHOT_ID, "missing")

    project_repository.get_snapshot.return_value = _snapshot(DatasetSnapshotStatus.failed)
    with pytest.raises(InvalidResourceStateError, match="is not ready"):
        service.get_person(SNAPSHOT_ID, "p1")


def test_project_service_lists_snapshot_source_members(tmp_path: Path) -> None:
    project_repository = Mock(spec=ProjectRepository)
    snapshot = _snapshot(DatasetSnapshotStatus.ready)
    members = (
        SnapshotSourceMember(
            id=uuid4(),
            dataset_snapshot_id=SNAPSHOT_ID,
            artifact_id=uuid4(),
            logical_name="a.xml",
            sha256="a" * 64,
            byte_size=10,
            media_type="application/xml",
            ordinal=0,
            created_at=NOW,
        ),
        SnapshotSourceMember(
            id=uuid4(),
            dataset_snapshot_id=SNAPSHOT_ID,
            artifact_id=uuid4(),
            logical_name="b.xml",
            sha256="b" * 64,
            byte_size=20,
            media_type="application/xml",
            ordinal=1,
            created_at=NOW,
        ),
    )
    project_repository.get_snapshot.return_value = snapshot
    project_repository.list_snapshot_source_members.return_value = members
    unit_of_work = StubUnitOfWork(projects=project_repository)
    service = _project_service(unit_of_work=unit_of_work, artifact_root=tmp_path)

    assert service.list_snapshot_source_members(SNAPSHOT_ID) == members
    project_repository.list_snapshot_source_members.assert_called_once_with(SNAPSHOT_ID)

    project_repository.get_snapshot.return_value = None
    with pytest.raises(ResourceNotFoundError, match=str(SNAPSHOT_ID)):
        service.list_snapshot_source_members(SNAPSHOT_ID)


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
    project_repository.add_imported_person_records.assert_not_called()
    project_repository.claim_snapshot_import.assert_not_called()
    artifact_command = artifact_repository.add_artifact.call_args.args[0]
    assert artifact_command.project_id == PROJECT_ID
    assert artifact_command.sha256 == snapshot.source_sha256
    with LocalArtifactStorage(tmp_path).open(artifact_command.storage_uri) as stored_source:
        assert stored_source.read() == VALID_TEI
    snapshot_command = project_repository.add_snapshot.call_args.args[0]
    assert snapshot_command.parser_version == (
        "tei_parser_v4+tei_collection_v1+tei_single_source_v1"
    )
    import_config = SnapshotImportConfig.model_validate(snapshot_command.import_config)
    assert import_config.profile.value == "tei_p5_person_register"
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
        cursor_codec=CursorCodec(),
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
    aggregation_repository.find_reusable_aggregation.return_value = None
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

    creation = service.create_aggregation(run_id=RUN_ID, command=command)
    created = creation.aggregation
    assert creation.created is True
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


def test_aggregation_service_returns_a_matching_aggregation_without_queueing() -> None:
    command = AggregationExecutionCreate(run_id=RUN_ID, method_execution_ids=(EXECUTION_ID,))
    existing = _aggregation(command, status=AggregationExecutionStatus.completed)
    aggregation_repository = Mock(spec=AggregationRepository)
    aggregation_repository.find_reusable_aggregation.return_value = existing
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

    creation = service.create_aggregation(
        run_id=RUN_ID,
        command=AggregationCreateRequest(method_execution_ids=(EXECUTION_ID,)),
    )

    assert creation == AggregationCreation(aggregation=existing, created=False)
    aggregation_repository.find_reusable_aggregation.assert_called_once_with(command)
    aggregation_repository.add_aggregation.assert_not_called()
    dispatch_repository.ensure_dispatch.assert_not_called()
    assert unit_of_work.commit_count == 0


def test_aggregation_service_reads_predictions_only_for_a_result_it_owns() -> None:
    aggregation_repository = Mock(spec=AggregationRepository)
    aggregation_repository.get_result.return_value = _aggregation_result(0)
    aggregation_repository.list_result_predictions.return_value = ()
    service = AggregationService(
        unit_of_work_factory=StubUnitOfWork(aggregations=aggregation_repository).factory,
        cursor_codec=CursorCodec(),
        clock=lambda: NOW,
    )

    predictions = service.list_result_predictions(
        aggregation_id=AGGREGATION_ID, result_id=RESULT_IDS[0]
    )
    aggregation_repository.get_result.return_value = _aggregation_result(
        0, aggregation_id=OTHER_AGGREGATION_ID
    )
    with pytest.raises(ResourceNotFoundError, match=str(RESULT_IDS[0])):
        service.list_result_predictions(aggregation_id=AGGREGATION_ID, result_id=RESULT_IDS[0])

    assert predictions == ()
    aggregation_repository.list_result_predictions.assert_called_once_with(
        AGGREGATION_ID, PERSON_IDS[0]
    )


def test_aggregation_service_does_not_queue_or_commit_without_durable_dispatch() -> None:
    aggregation_repository = Mock(spec=AggregationRepository)
    aggregation_repository.find_reusable_aggregation.return_value = None
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

    old_filters = ReviewItemQuery(aggregation_id=AGGREGATION_ID).model_dump(
        mode="json", exclude={"cursor", "limit", "tei_id"}
    )
    CursorCodec().decode(
        first_page.next_cursor,
        expected_resource=f"review_items:{AGGREGATION_ID}:{canonical_json_sha256(old_filters)}",
        expected_sort_value_count=2,
    )
    with pytest.raises(InvalidCursorError, match="different resource"):
        service.list_review_items(
            ReviewItemQuery(
                aggregation_id=AGGREGATION_ID, tei_id="p2", cursor=first_page.next_cursor
            )
        )

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


def test_review_item_service_summarizes_only_a_completed_aggregation() -> None:
    aggregation_repository = Mock(spec=AggregationRepository)
    review_repository = Mock(spec=ReviewRepository)
    command = AggregationExecutionCreate(run_id=RUN_ID, method_execution_ids=(EXECUTION_ID,))
    aggregation_repository.get_aggregation.return_value = _aggregation(
        command,
        status=AggregationExecutionStatus.completed,
    )
    groups = (
        ReviewSummaryGroup(
            certainty_tier=CertaintyTier.high,
            agreement_tier=AgreementTier.unanimous,
            workflow_state=ReviewWorkflowState.unreviewed,
            result_count=5,
        ),
        ReviewSummaryGroup(
            certainty_tier=CertaintyTier.uncertain,
            agreement_tier=AgreementTier.single_rater,
            workflow_state=ReviewWorkflowState.reviewed,
            final_label=CanonicalLabel.female,
            review_action=ReviewAction.correct,
            result_count=2,
        ),
    )
    review_repository.count_review_groups.return_value = ReviewSummaryData(
        groups=groups,
        last_annotated_at=NOW,
    )
    service = ReviewItemService(
        unit_of_work_factory=StubUnitOfWork(
            aggregations=aggregation_repository,
            reviews=review_repository,
        ).factory,
        cursor_codec=CursorCodec(),
    )

    summary = service.summarize_review(AGGREGATION_ID)

    assert summary == ReviewSummary(
        aggregation_execution_id=AGGREGATION_ID,
        result_count=7,
        last_annotated_at=NOW,
        groups=list(groups),
    )
    review_repository.count_review_groups.assert_called_once_with(AGGREGATION_ID)
    aggregation_repository.get_aggregation.return_value = _aggregation(command)
    with pytest.raises(InvalidResourceStateError, match="is not completed"):
        service.summarize_review(AGGREGATION_ID)
    aggregation_repository.get_aggregation.return_value = None
    with pytest.raises(ResourceNotFoundError, match=str(AGGREGATION_ID)):
        service.summarize_review(AGGREGATION_ID)


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


class FakePasswordHasher:
    """Deterministic, non-cryptographic stand-in so authentication tests stay fast."""

    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hashed:{password}"


AUTH_USER_ID = UUID("c0000000-0000-0000-0000-000000000001")
AUTH_USERNAME = "reviewer.one"
SESSION_LIFETIME = SessionLifetimePolicy(
    idle=timedelta(hours=24),
    keep_signed_in_idle=timedelta(days=7),
    max_lifetime=timedelta(days=30),
)


def _user_session(
    *,
    expires_at: datetime,
    absolute_expires_at: datetime | None = None,
    keep_signed_in: bool = False,
    revoked_at: datetime | None = None,
) -> UserSession:
    return UserSession(
        user_id=AUTH_USER_ID,
        csrf_secret="csrf-secret",
        keep_signed_in=keep_signed_in,
        expires_at=expires_at,
        absolute_expires_at=absolute_expires_at or NOW + timedelta(days=30),
        revoked_at=revoked_at,
    )


def _local_user(*, is_active: bool = True) -> User:
    return User(
        id=AUTH_USER_ID,
        display_name="Reviewer One",
        roles={GlobalRole.operator},
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def _local_credential(*, must_change_password: bool = False) -> LocalCredential:
    return LocalCredential(
        user_id=AUTH_USER_ID,
        username=AUTH_USERNAME,
        password_hash="hashed:correct-horse-battery",
        must_change_password=must_change_password,
        updated_at=NOW,
    )


def _authentication_service(
    *,
    unit_of_work: StubUnitOfWork,
    password_hasher: PasswordHasherProtocol | None = None,
    clock: object = lambda: NOW,
    session_lifetime: SessionLifetimePolicy = SESSION_LIFETIME,
) -> AuthenticationService:
    return AuthenticationService(
        unit_of_work_factory=unit_of_work.factory,
        password_hasher=password_hasher or FakePasswordHasher(),
        clock=clock,  # type: ignore[arg-type]  # A fixed-time lambda satisfies the Clock protocol.
        session_lifetime=session_lifetime,
    )


def test_annotation_service_reports_an_absent_person_history_as_not_found() -> None:
    review_repository = Mock(spec=ReviewRepository)
    review_repository.get_annotation_history.return_value = None
    service = AnnotationService(StubUnitOfWork(reviews=review_repository).factory)

    with pytest.raises(ResourceNotFoundError, match="'p9'"):
        service.get_history(snapshot_id=SNAPSHOT_ID, tei_id="p9")

    review_repository.get_annotation_history.assert_called_once_with(SNAPSHOT_ID, "p9")


def test_authentication_service_login_issues_session_for_verified_credentials() -> None:
    users_repository = Mock(spec=UserRepository)
    users_repository.get_user.return_value = _local_user()
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_credential_by_username.return_value = _local_credential()
    unit_of_work = StubUnitOfWork(users=users_repository, auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    issued = service.login(username=AUTH_USERNAME, password="correct-horse-battery")

    assert issued.user == CurrentUser(
        id=AUTH_USER_ID, display_name="Reviewer One", roles={GlobalRole.operator}
    )
    create_session_kwargs = auth_repository.create_session.call_args.kwargs
    assert create_session_kwargs["user_id"] == AUTH_USER_ID
    assert create_session_kwargs["csrf_secret"] == issued.csrf_secret
    assert (
        create_session_kwargs["session_id"]
        == hashlib.sha256(issued.token.encode("ascii")).hexdigest()
    )
    assert create_session_kwargs["keep_signed_in"] is False
    assert create_session_kwargs["expires_at"] == NOW + timedelta(hours=24)
    assert create_session_kwargs["absolute_expires_at"] == NOW + timedelta(days=30)
    assert issued.keep_signed_in is False
    assert issued.absolute_expires_at == NOW + timedelta(days=30)
    assert unit_of_work.commit_count == 1


def test_authentication_service_login_keep_signed_in_uses_the_longer_idle_limit() -> None:
    users_repository = Mock(spec=UserRepository)
    users_repository.get_user.return_value = _local_user()
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_credential_by_username.return_value = _local_credential()
    unit_of_work = StubUnitOfWork(users=users_repository, auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    issued = service.login(
        username=AUTH_USERNAME, password="correct-horse-battery", keep_signed_in=True
    )

    create_session_kwargs = auth_repository.create_session.call_args.kwargs
    assert create_session_kwargs["keep_signed_in"] is True
    assert create_session_kwargs["expires_at"] == NOW + timedelta(days=7)
    assert create_session_kwargs["absolute_expires_at"] == NOW + timedelta(days=30)
    assert issued.keep_signed_in is True


def test_authentication_service_login_caps_the_idle_limit_at_the_absolute_limit() -> None:
    users_repository = Mock(spec=UserRepository)
    users_repository.get_user.return_value = _local_user()
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_credential_by_username.return_value = _local_credential()
    unit_of_work = StubUnitOfWork(users=users_repository, auth=auth_repository)
    service = _authentication_service(
        unit_of_work=unit_of_work,
        session_lifetime=SessionLifetimePolicy(
            idle=timedelta(hours=24),
            keep_signed_in_idle=timedelta(days=7),
            max_lifetime=timedelta(days=2),
        ),
    )

    service.login(username=AUTH_USERNAME, password="correct-horse-battery", keep_signed_in=True)

    create_session_kwargs = auth_repository.create_session.call_args.kwargs
    assert create_session_kwargs["expires_at"] == NOW + timedelta(days=2)
    assert create_session_kwargs["absolute_expires_at"] == NOW + timedelta(days=2)


def test_authentication_service_login_rejects_unknown_username_without_revealing_it() -> None:
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_credential_by_username.return_value = None
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    with pytest.raises(InvalidCredentialsError):
        service.login(username="nobody", password="whatever-they-tried")

    assert auth_repository.create_session.call_count == 0
    assert unit_of_work.commit_count == 0


@pytest.mark.parametrize(
    ("credential", "user", "password"),
    [
        (_local_credential(), _local_user(is_active=False), "correct-horse-battery"),
        (_local_credential(), _local_user(), "wrong-password"),
    ],
)
def test_authentication_service_login_rejects_inactive_user_or_wrong_password(
    credential: LocalCredential, user: User, password: str
) -> None:
    users_repository = Mock(spec=UserRepository)
    users_repository.get_user.return_value = user
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_credential_by_username.return_value = credential
    unit_of_work = StubUnitOfWork(users=users_repository, auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    with pytest.raises(InvalidCredentialsError):
        service.login(username=AUTH_USERNAME, password=password)

    assert auth_repository.create_session.call_count == 0
    assert unit_of_work.commit_count == 0


def test_authentication_service_resolve_session_returns_state_for_valid_session() -> None:
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_session.return_value = _user_session(expires_at=NOW + timedelta(hours=1))
    auth_repository.get_credential.return_value = _local_credential(must_change_password=True)
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    resolved = service.resolve_session(session_token="raw-session-token")

    assert resolved is not None
    assert resolved.user_id == AUTH_USER_ID
    assert resolved.csrf_secret == "csrf-secret"
    assert resolved.must_change_password is True
    assert resolved.keep_signed_in is False
    assert (
        auth_repository.get_session.call_args.args[0]
        == hashlib.sha256(b"raw-session-token").hexdigest()
    )


def test_authentication_service_resolve_session_tolerates_missing_local_credential() -> None:
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_session.return_value = _user_session(expires_at=NOW + timedelta(hours=1))
    auth_repository.get_credential.return_value = None
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    resolved = service.resolve_session(session_token="raw-session-token")

    assert resolved is not None
    assert resolved.must_change_password is False


@pytest.mark.parametrize(
    "session",
    [
        None,
        _user_session(expires_at=NOW + timedelta(hours=1), revoked_at=NOW),
        _user_session(expires_at=NOW - timedelta(seconds=1)),
        _user_session(expires_at=NOW),
    ],
)
def test_authentication_service_resolve_session_rejects_missing_revoked_or_expired(
    session: UserSession | None,
) -> None:
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_session.return_value = session
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    assert service.resolve_session(session_token="raw-session-token") is None
    assert auth_repository.get_credential.call_count == 0
    assert auth_repository.renew_session.call_count == 0
    assert unit_of_work.commit_count == 0


@pytest.mark.parametrize(
    ("session", "renewed_expires_at"),
    [
        # An hour into a browser-session login, use slides the idle expiry to a full 24 hours.
        (_user_session(expires_at=NOW + timedelta(hours=23)), NOW + timedelta(hours=24)),
        # A kept-signed-in session slides by its own, longer idle limit.
        (
            _user_session(expires_at=NOW + timedelta(days=6), keep_signed_in=True),
            NOW + timedelta(days=7),
        ),
        # Near the absolute limit, the idle expiry stops at it rather than passing it.
        (
            _user_session(
                expires_at=NOW + timedelta(hours=1),
                absolute_expires_at=NOW + timedelta(hours=2),
            ),
            NOW + timedelta(hours=2),
        ),
    ],
)
def test_authentication_service_resolve_session_slides_the_idle_expiry(
    session: UserSession, renewed_expires_at: datetime
) -> None:
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_session.return_value = session
    auth_repository.get_credential.return_value = _local_credential()
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    resolved = service.resolve_session(session_token="raw-session-token")

    assert resolved is not None
    assert resolved.keep_signed_in is session.keep_signed_in
    auth_repository.renew_session.assert_called_once_with(
        hashlib.sha256(b"raw-session-token").hexdigest(), expires_at=renewed_expires_at
    )
    assert unit_of_work.commit_count == 1


@pytest.mark.parametrize(
    "session",
    [
        # Renewed moments ago: the next move would be under five minutes, so nothing is written.
        _user_session(expires_at=NOW + timedelta(hours=24) - timedelta(minutes=4)),
        # Already at the absolute limit: there is nowhere left to slide.
        _user_session(
            expires_at=NOW + timedelta(hours=2), absolute_expires_at=NOW + timedelta(hours=2)
        ),
    ],
)
def test_authentication_service_resolve_session_skips_small_or_capped_renewals(
    session: UserSession,
) -> None:
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_session.return_value = session
    auth_repository.get_credential.return_value = _local_credential()
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    assert service.resolve_session(session_token="raw-session-token") is not None
    assert auth_repository.renew_session.call_count == 0
    assert unit_of_work.commit_count == 0


def test_authentication_service_logout_revokes_hashed_session_and_commits() -> None:
    auth_repository = Mock(spec=AuthRepository)
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    service.logout(session_token="raw-session-token")

    assert (
        auth_repository.revoke_session.call_args.args[0]
        == hashlib.sha256(b"raw-session-token").hexdigest()
    )
    assert unit_of_work.commit_count == 1


def test_authentication_service_change_password_verifies_current_and_clears_flag() -> None:
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_credential.return_value = _local_credential(must_change_password=True)
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    service.change_password(
        user_id=AUTH_USER_ID,
        current_password="correct-horse-battery",
        new_password="a-brand-new-passphrase",
    )

    auth_repository.set_password.assert_called_once_with(
        user_id=AUTH_USER_ID,
        password_hash="hashed:a-brand-new-passphrase",
        must_change_password=False,
    )
    assert unit_of_work.commit_count == 1


def test_authentication_service_change_password_rejects_wrong_current_password() -> None:
    auth_repository = Mock(spec=AuthRepository)
    auth_repository.get_credential.return_value = _local_credential()
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    with pytest.raises(InvalidCurrentPasswordError):
        service.change_password(
            user_id=AUTH_USER_ID,
            current_password="not-the-current-password",
            new_password="a-brand-new-passphrase",
        )

    assert auth_repository.set_password.call_count == 0
    assert unit_of_work.commit_count == 0


def test_authentication_service_create_local_account_persists_user_and_credential() -> None:
    users_repository = Mock(spec=UserRepository)
    users_repository.add_user.return_value = _local_user()
    auth_repository = Mock(spec=AuthRepository)
    unit_of_work = StubUnitOfWork(users=users_repository, auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    created = service.create_local_account(
        display_name="Reviewer One",
        roles={GlobalRole.operator},
        username=AUTH_USERNAME,
        password="an-initial-passphrase",
    )

    assert created == _local_user()
    users_repository.add_user.assert_called_once_with(
        UserCreate(display_name="Reviewer One", roles={GlobalRole.operator}, is_active=True)
    )
    auth_repository.add_credential.assert_called_once_with(
        user_id=AUTH_USER_ID,
        username=AUTH_USERNAME,
        password_hash="hashed:an-initial-passphrase",
    )
    assert unit_of_work.commit_count == 1


def test_authentication_service_reset_password_revokes_every_session() -> None:
    auth_repository = Mock(spec=AuthRepository)
    unit_of_work = StubUnitOfWork(auth=auth_repository)
    service = _authentication_service(unit_of_work=unit_of_work)

    service.reset_password(user_id=AUTH_USER_ID, new_password="a-forced-new-passphrase")

    auth_repository.set_password.assert_called_once_with(
        user_id=AUTH_USER_ID,
        password_hash="hashed:a-forced-new-passphrase",
        must_change_password=True,
    )
    auth_repository.revoke_all_sessions.assert_called_once_with(AUTH_USER_ID)
    assert unit_of_work.commit_count == 1
