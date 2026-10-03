import pytest
from sqlalchemy.orm import Session

from gendertagger.db.repositories.team_repository import SqlAlchemyTeamRepository
from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
from gendertagger.models.team import TeamCreate
from gendertagger.models.user import UserCreate
from gendertagger.services.ports.persistence_errors import DuplicateTeamSlugError

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


@pytest.mark.postgres_rollback
def test_team_repository_creates_lists_and_renames_a_team(db_session: Session) -> None:
    repository = SqlAlchemyTeamRepository(db_session)
    created = repository.add_team(
        TeamCreate(slug="editorial-group", display_name="Editorial group")
    )

    listed = repository.list_teams(search="editorial", limit=10, after=None)
    updated = repository.update_team_display_name(created.id, "Renamed editorial group")

    assert listed == (created,)
    assert updated.slug == "editorial-group"
    assert updated.display_name == "Renamed editorial group"


@pytest.mark.postgres_rollback
def test_team_repository_enforces_canonical_slug_uniqueness(db_session: Session) -> None:
    repository = SqlAlchemyTeamRepository(db_session)
    repository.add_team(TeamCreate(slug="editorial-group", display_name="Editorial group"))

    with pytest.raises(DuplicateTeamSlugError, match="editorial-group"):
        repository.add_team(TeamCreate(slug="editorial-group", display_name="Duplicate"))


@pytest.mark.postgres_rollback
def test_team_repository_keys_direct_memberships_by_team_and_user(db_session: Session) -> None:
    users = SqlAlchemyUserRepository(db_session)
    user = users.add_user(UserCreate(display_name="Synthetic member"))
    repository = SqlAlchemyTeamRepository(db_session)
    team = repository.add_team(TeamCreate(slug="editorial-group", display_name="Editorial group"))

    member = repository.add_member(team.id, user.id)

    assert repository.get_member(team.id, user.id) == member
    assert repository.list_member_teams(user.id, search=None, limit=10, after=None) == (team,)
    assert repository.list_members(team.id, search=None, limit=10, after=None) == (member,)
    assert repository.remove_member(team.id, user.id)
    assert not repository.remove_member(team.id, user.id)
