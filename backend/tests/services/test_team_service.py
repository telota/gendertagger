from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from gendertagger.models.team import TeamCreate, TeamMember, TeamMemberAdd, TeamSummary, TeamUpdate
from gendertagger.models.user import CurrentUser, GlobalRole, User
from gendertagger.services.pagination import CursorCodec, InvalidCursorError
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.ports.project_access_repository import ProjectAccessRepository
from gendertagger.services.ports.project_repository import ProjectRepository
from gendertagger.services.ports.team_repository import TeamRepository
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.ports.user_repository import UserRepository
from gendertagger.services.project_access import ManagerReplacementRequiredError
from gendertagger.services.teams import InactiveUserError, TeamNotEmptyError, TeamService

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
TEAM_ID = UUID("30000000-0000-0000-0000-000000000001")
OTHER_TEAM_ID = UUID("30000000-0000-0000-0000-000000000002")
USER_ID = UUID("30000000-0000-0000-0000-000000000003")


class StubUnitOfWork:
    """Expose only the repositories used by deterministic team-service tests."""

    def __init__(self, teams: TeamRepository, users: UserRepository) -> None:
        self.teams = teams
        self.users = users
        self.access = Mock(spec=ProjectAccessRepository)
        self.projects = Mock(spec=ProjectRepository)
        self.commit_count = 0

    def __enter__(self) -> "StubUnitOfWork":
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: object,
    ) -> None:
        return None

    def commit(self) -> None:
        self.commit_count += 1


def _team(team_id: UUID = TEAM_ID, slug: str = "editorial-group") -> TeamSummary:
    return TeamSummary(
        id=team_id,
        slug=slug,
        display_name="Editorial group",
        created_at=NOW,
        updated_at=NOW,
    )


def _user(*, is_active: bool = True) -> User:
    return User(
        id=USER_ID,
        display_name="Member",
        roles=set(),
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def _member() -> TeamMember:
    return TeamMember(
        team_id=TEAM_ID,
        user_id=USER_ID,
        display_name="Member",
        is_active=True,
        created_at=NOW,
    )


def _service(
    teams: Mock | None = None,
    users: Mock | None = None,
) -> tuple[TeamService, StubUnitOfWork, Mock, Mock]:
    team_repository = teams or Mock(spec=TeamRepository)
    user_repository = users or Mock(spec=UserRepository)
    unit_of_work = StubUnitOfWork(team_repository, user_repository)
    service = TeamService(
        unit_of_work_factory=lambda: cast(UnitOfWork, unit_of_work),
        cursor_codec=CursorCodec(),
    )
    return service, unit_of_work, team_repository, user_repository


@pytest.mark.unit
def test_create_team_commits_canonical_command() -> None:
    service, unit_of_work, teams, _ = _service()
    teams.add_team.return_value = _team()

    result = service.create_team(
        TeamCreate(slug="editorial-group", display_name="Editorial group"),
        actor_user_id=USER_ID,
        request_id="request-1",
    )

    assert result == _team()
    teams.add_team.assert_called_once()
    assert unit_of_work.commit_count == 1


@pytest.mark.unit
def test_update_team_locks_before_returning_idempotent_noop() -> None:
    service, unit_of_work, teams, _ = _service()
    teams.get_team_for_update.return_value = _team()

    result = service.update_team(
        TEAM_ID,
        TeamUpdate(display_name="Editorial group"),
        actor_user_id=USER_ID,
        request_id="request-1",
    )

    assert result == _team()
    teams.lock_team.assert_called_once_with(TEAM_ID)
    teams.update_team_display_name.assert_not_called()
    assert unit_of_work.commit_count == 0


@pytest.mark.unit
def test_delete_team_rejects_a_nonempty_roster_without_deleting() -> None:
    service, unit_of_work, teams, _ = _service()
    teams.get_team_for_update.return_value = _team()
    teams.has_members.return_value = True

    with pytest.raises(TeamNotEmptyError):
        service.delete_team(TEAM_ID, actor_user_id=USER_ID, request_id="request-1")

    teams.lock_team.assert_called_once_with(TEAM_ID)
    teams.delete_team.assert_not_called()
    assert unit_of_work.commit_count == 0


@pytest.mark.unit
def test_add_member_revalidates_target_activity_inside_locked_transaction() -> None:
    service, unit_of_work, teams, users = _service()
    teams.get_team_for_update.return_value = _team()
    users.get_user_for_update.return_value = _user(is_active=False)

    with pytest.raises(InactiveUserError):
        service.add_member(
            TEAM_ID,
            TeamMemberAdd(user_id=USER_ID),
            actor_user_id=USER_ID,
            request_id="request-1",
        )

    teams.lock_team.assert_called_once_with(TEAM_ID)
    teams.add_member.assert_not_called()
    assert unit_of_work.commit_count == 0


@pytest.mark.unit
def test_add_member_returns_existing_membership_without_a_second_write() -> None:
    service, unit_of_work, teams, users = _service()
    teams.get_team_for_update.return_value = _team()
    users.get_user_for_update.return_value = _user()
    teams.get_member.return_value = _member()

    member, created = service.add_member(
        TEAM_ID,
        TeamMemberAdd(user_id=USER_ID),
        actor_user_id=USER_ID,
        request_id="request-1",
    )

    assert member == _member()
    assert not created
    teams.add_member.assert_not_called()
    assert unit_of_work.commit_count == 0


def test_remove_member_removes_derived_project_roles_inside_team_lock() -> None:
    service, unit_of_work, teams, users = _service()
    teams.get_team_for_update.return_value = _team()
    teams.get_member.return_value = _member()
    users.get_user_for_update.return_value = _user()
    unit_of_work.access.list_managed_project_ids.return_value = ()

    service.remove_member(TEAM_ID, USER_ID, actor_user_id=USER_ID, request_id="request-1")

    users.lock_membership_updates.assert_called_once_with(USER_ID)
    teams.lock_team.assert_called_once_with(TEAM_ID)
    unit_of_work.access.remove_team_member_project_memberships.assert_called_once_with(
        TEAM_ID, USER_ID
    )
    teams.remove_member.assert_called_once_with(TEAM_ID, USER_ID)
    assert unit_of_work.commit_count == 1


@pytest.mark.unit
def test_remove_member_requires_manager_replacement_before_revoking_roles() -> None:
    service, unit_of_work, teams, users = _service()
    teams.get_team_for_update.return_value = _team()
    users.get_user_for_update.return_value = _user()
    unit_of_work.access.list_managed_project_ids.return_value = (UUID(int=99),)

    with pytest.raises(ManagerReplacementRequiredError):
        service.remove_member(TEAM_ID, USER_ID, actor_user_id=USER_ID, request_id="request-1")

    unit_of_work.projects.get_project_for_update.assert_called_once_with(UUID(int=99))
    unit_of_work.access.remove_team_member_project_memberships.assert_not_called()
    assert unit_of_work.commit_count == 0


@pytest.mark.unit
def test_missing_membership_rolls_back_without_committing() -> None:
    service, unit_of_work, teams, users = _service()
    teams.get_team_for_update.return_value = _team()
    teams.get_member.return_value = None
    users.get_user_for_update.return_value = _user()
    unit_of_work.access.list_managed_project_ids.return_value = ()

    with pytest.raises(ResourceNotFoundError):
        service.remove_member(TEAM_ID, USER_ID, actor_user_id=USER_ID, request_id="request-1")

    assert unit_of_work.commit_count == 0


@pytest.mark.unit
def test_direct_team_cursor_cannot_be_reused_by_an_administrator() -> None:
    service, _, teams, _ = _service()
    teams.list_member_teams.return_value = [_team(), _team(OTHER_TEAM_ID, "research-group")]
    caller = CurrentUser(id=USER_ID, display_name="Member", roles=set())

    first_page = service.list_visible_teams(caller, query=None, limit=1, cursor=None)

    assert first_page.next_cursor is not None
    administrator = CurrentUser(id=USER_ID, display_name="Administrator", roles={GlobalRole.admin})
    with pytest.raises(InvalidCursorError):
        service.list_visible_teams(
            administrator,
            query=None,
            limit=1,
            cursor=first_page.next_cursor,
        )


@pytest.mark.unit
def test_create_team_failure_does_not_commit() -> None:
    service, unit_of_work, teams, _ = _service()
    teams.add_team.side_effect = RuntimeError("database failed")

    with pytest.raises(RuntimeError, match="database failed"):
        service.create_team(
            TeamCreate(slug="editorial-group", display_name="Editorial group"),
            actor_user_id=USER_ID,
            request_id="request-1",
        )

    assert unit_of_work.commit_count == 0
