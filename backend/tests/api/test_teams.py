from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import (
    require_authenticated_user,
    require_csrf_protection,
    require_password_current,
)
from gendertagger.api.dependencies import get_team_service
from gendertagger.api.settings import AppSettings
from gendertagger.models.api import CursorPage
from gendertagger.models.team import TeamCreate, TeamMember, TeamSummary
from gendertagger.models.user import CurrentUser, GlobalRole
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    DuplicateTeamSlugError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.teams import InactiveUserError, TeamNotEmptyError, TeamService

pytestmark = pytest.mark.unit

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
TEAM_ID = UUID("40000000-0000-0000-0000-000000000001")
USER_ID = UUID("40000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("the route test must not open persistence")


def _admin() -> CurrentUser:
    return CurrentUser(id=USER_ID, display_name="Administrator", roles={GlobalRole.admin})


def _member() -> CurrentUser:
    return CurrentUser(id=USER_ID, display_name="Member", roles=set())


def _team() -> TeamSummary:
    return TeamSummary(
        id=TEAM_ID,
        slug="editorial-group",
        display_name="Editorial group",
        created_at=NOW,
        updated_at=NOW,
    )


def _team_member() -> TeamMember:
    return TeamMember(
        team_id=TEAM_ID,
        user_id=USER_ID,
        display_name="Member",
        is_active=True,
        created_at=NOW,
    )


def _client(service: object, user: CurrentUser | None = None) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
        request_id_factory=lambda: "request-123",
    )
    resolved_user = _admin() if user is None else user
    application.dependency_overrides[require_authenticated_user] = lambda: resolved_user
    application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_team_service] = lambda: service
    return TestClient(application)


def test_visible_teams_returns_direct_summary_page_for_an_authenticated_member() -> None:
    service = Mock(spec=TeamService)
    service.list_visible_teams.return_value = CursorPage(
        items=[_team()], next_cursor=None, has_more=False
    )

    response = _client(service, _member()).get("/api/v1/teams", params={"query": "editorial"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"] == [_team().model_dump(mode="json")]
    service.list_visible_teams.assert_called_once_with(
        _member(),
        query="editorial",
        limit=100,
        cursor=None,
    )


def test_admin_team_collection_rejects_an_authenticated_non_administrator() -> None:
    response = _client(Mock(spec=TeamService), _member()).get("/api/v1/admin/teams")

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_team_collection_maps_scope_bound_invalid_cursor() -> None:
    service = Mock(spec=TeamService)
    service.list_visible_teams.side_effect = InvalidCursorError("scope")

    response = _client(service, _member()).get("/api/v1/teams", params={"cursor": "invalid"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["details"] == {"reason": "invalid_cursor"}


def test_admin_team_create_forwards_normalized_command_and_actor() -> None:
    service = Mock(spec=TeamService)
    service.create_team.return_value = _team()

    response = _client(service).post(
        "/api/v1/admin/teams",
        json={"slug": "EDITORIAL-GROUP", "display_name": "Editorial group"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    args, kwargs = service.create_team.call_args
    assert args == (TeamCreate(slug="editorial-group", display_name="Editorial group"),)
    assert kwargs == {"actor_user_id": USER_ID, "request_id": "request-123"}


def test_admin_team_create_maps_duplicate_slug_conflict() -> None:
    service = Mock(spec=TeamService)
    service.create_team.side_effect = DuplicateTeamSlugError("editorial-group")

    response = _client(service).post(
        "/api/v1/admin/teams",
        json={"slug": "editorial-group", "display_name": "Editorial group"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "team_slug_conflict"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ResourceNotFoundError("missing"), "resource_not_found"),
        (TeamNotEmptyError("members"), "team_not_empty"),
    ],
)
def test_admin_team_delete_maps_missing_and_nonempty_failures(
    error: Exception,
    code: str,
) -> None:
    service = Mock(spec=TeamService)
    service.delete_team.side_effect = error

    response = _client(service).delete(f"/api/v1/admin/teams/{TEAM_ID}")

    assert response.status_code == (404 if code == "resource_not_found" else 409)
    assert response.json()["error"]["code"] == code


def test_admin_roster_add_distinguishes_created_and_idempotent_results() -> None:
    service = Mock(spec=TeamService)
    service.add_member.side_effect = [(_team_member(), True), (_team_member(), False)]
    client = _client(service)

    created = client.post(f"/api/v1/admin/teams/{TEAM_ID}/members", json={"user_id": str(USER_ID)})
    repeated = client.post(f"/api/v1/admin/teams/{TEAM_ID}/members", json={"user_id": str(USER_ID)})

    assert created.status_code == status.HTTP_201_CREATED
    assert repeated.status_code == status.HTTP_200_OK


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ResourceNotFoundError("missing"), "resource_not_found"),
        (InactiveUserError("inactive"), "inactive_user"),
    ],
)
def test_admin_roster_add_maps_target_failures(error: Exception, code: str) -> None:
    service = Mock(spec=TeamService)
    service.add_member.side_effect = error

    response = _client(service).post(
        f"/api/v1/admin/teams/{TEAM_ID}/members",
        json={"user_id": str(USER_ID)},
    )

    assert response.status_code == (404 if code == "resource_not_found" else 409)
    assert response.json()["error"]["code"] == code


def test_team_unsafe_mutation_preserves_csrf_dependency() -> None:
    service = Mock(spec=TeamService)
    application = cast(FastAPI, _client(service).app)

    def reject_csrf() -> None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf")

    application.dependency_overrides[require_csrf_protection] = reject_csrf
    response = TestClient(application).post(
        "/api/v1/admin/teams",
        json={"slug": "editorial-group", "display_name": "Editorial group"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    service.create_team.assert_not_called()


def test_team_routes_remain_password_current_gated() -> None:
    service = Mock(spec=TeamService)
    application = cast(FastAPI, _client(service).app)

    def reject_password_change() -> None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password")

    application.dependency_overrides[require_password_current] = reject_password_change
    response = TestClient(application).get("/api/v1/teams")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    service.list_visible_teams.assert_not_called()
