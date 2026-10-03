from collections.abc import Generator
from contextlib import contextmanager
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


@pytest.fixture(scope="module")
def teams_application() -> FastAPI:
    """Compose fixed team routes once while each client supplies fresh dependencies."""
    return create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
        request_id_factory=lambda: "request-123",
    )


@contextmanager
def _client(
    application: FastAPI, service: object, user: CurrentUser | None = None
) -> Generator[TestClient, None, None]:
    previous_overrides = application.dependency_overrides
    assert previous_overrides == {}, "a previous team case leaked dependency overrides"
    resolved_user = _admin() if user is None else user
    application.dependency_overrides = {
        require_authenticated_user: lambda: resolved_user,
        require_csrf_protection: lambda: None,
        get_team_service: lambda: service,
    }
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides = previous_overrides


def test_visible_teams_returns_direct_summary_page_for_an_authenticated_member(
    teams_application: FastAPI,
) -> None:
    service = Mock(spec=TeamService)
    service.list_visible_teams.return_value = CursorPage(
        items=[_team()], next_cursor=None, has_more=False
    )

    with _client(teams_application, service, _member()) as client:
        response = client.get("/api/v1/teams", params={"query": "editorial"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"] == [_team().model_dump(mode="json")]
        service.list_visible_teams.assert_called_once_with(
            _member(),
            query="editorial",
            limit=100,
            cursor=None,
        )


def test_admin_team_collection_rejects_an_authenticated_non_administrator(
    teams_application: FastAPI,
) -> None:
    with _client(teams_application, Mock(spec=TeamService), _member()) as client:
        response = client.get("/api/v1/admin/teams")

        assert response.status_code == status.HTTP_403_FORBIDDEN


def test_team_collection_maps_scope_bound_invalid_cursor(
    teams_application: FastAPI,
) -> None:
    service = Mock(spec=TeamService)
    service.list_visible_teams.side_effect = InvalidCursorError("scope")

    with _client(teams_application, service, _member()) as client:
        response = client.get("/api/v1/teams", params={"cursor": "invalid"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["error"]["details"] == {"reason": "invalid_cursor"}


def test_admin_team_create_forwards_normalized_command_and_actor(
    teams_application: FastAPI,
) -> None:
    service = Mock(spec=TeamService)
    service.create_team.return_value = _team()

    with _client(teams_application, service) as client:
        response = client.post(
            "/api/v1/admin/teams",
            json={"slug": "EDITORIAL-GROUP", "display_name": "Editorial group"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        args, kwargs = service.create_team.call_args
        assert args == (TeamCreate(slug="editorial-group", display_name="Editorial group"),)
        assert kwargs == {"actor_user_id": USER_ID, "request_id": "request-123"}


def test_admin_team_create_maps_duplicate_slug_conflict(
    teams_application: FastAPI,
) -> None:
    service = Mock(spec=TeamService)
    service.create_team.side_effect = DuplicateTeamSlugError("editorial-group")

    with _client(teams_application, service) as client:
        response = client.post(
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
    teams_application: FastAPI,
    error: Exception,
    code: str,
) -> None:
    service = Mock(spec=TeamService)
    service.delete_team.side_effect = error

    with _client(teams_application, service) as client:
        response = client.delete(f"/api/v1/admin/teams/{TEAM_ID}")

        assert response.status_code == (404 if code == "resource_not_found" else 409)
        assert response.json()["error"]["code"] == code


def test_admin_roster_add_distinguishes_created_and_idempotent_results(
    teams_application: FastAPI,
) -> None:
    service = Mock(spec=TeamService)
    service.add_member.side_effect = [(_team_member(), True), (_team_member(), False)]
    with _client(teams_application, service) as client:
        created = client.post(
            f"/api/v1/admin/teams/{TEAM_ID}/members", json={"user_id": str(USER_ID)}
        )
        repeated = client.post(
            f"/api/v1/admin/teams/{TEAM_ID}/members", json={"user_id": str(USER_ID)}
        )

        assert created.status_code == status.HTTP_201_CREATED
        assert repeated.status_code == status.HTTP_200_OK


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ResourceNotFoundError("missing"), "resource_not_found"),
        (InactiveUserError("inactive"), "inactive_user"),
    ],
)
def test_admin_roster_add_maps_target_failures(
    teams_application: FastAPI, error: Exception, code: str
) -> None:
    service = Mock(spec=TeamService)
    service.add_member.side_effect = error

    with _client(teams_application, service) as client:
        response = client.post(
            f"/api/v1/admin/teams/{TEAM_ID}/members",
            json={"user_id": str(USER_ID)},
        )

        assert response.status_code == (404 if code == "resource_not_found" else 409)
        assert response.json()["error"]["code"] == code


def test_team_unsafe_mutation_preserves_csrf_dependency(
    teams_application: FastAPI,
) -> None:
    service = Mock(spec=TeamService)
    with _client(teams_application, service) as client:
        application = cast(FastAPI, client.app)

        def reject_csrf() -> None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf")

        application.dependency_overrides[require_csrf_protection] = reject_csrf
        response = client.post(
            "/api/v1/admin/teams",
            json={"slug": "editorial-group", "display_name": "Editorial group"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        service.create_team.assert_not_called()


def test_team_routes_remain_password_current_gated(
    teams_application: FastAPI,
) -> None:
    service = Mock(spec=TeamService)
    with _client(teams_application, service) as client:
        application = cast(FastAPI, client.app)

        def reject_password_change() -> None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password")

        application.dependency_overrides[require_password_current] = reject_password_change
        response = client.get("/api/v1/teams")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        service.list_visible_teams.assert_not_called()


def test_team_clients_isolate_principals_manual_overrides_and_state_after_a_case_fails(
    teams_application: FastAPI,
) -> None:
    first_service = Mock(spec=TeamService)
    first_service.list_admin_teams.return_value = CursorPage(items=[], has_more=False)
    second_service = Mock(spec=TeamService)
    second_service.list_visible_teams.return_value = CursorPage(items=[], has_more=False)

    def reject_password_change() -> None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password")

    def fail_first_case() -> None:
        with _client(teams_application, first_service) as first:
            first.cookies.set("teams-case", "first")
            first.headers["X-Teams-Case"] = "first"
            first.app_state["teams_case"] = "first"
            assert first.get("/api/v1/admin/teams").status_code == 200
            teams_application.dependency_overrides[require_password_current] = (
                reject_password_change
            )
            assert first.get("/api/v1/teams").status_code == 403
            raise RuntimeError("team case failed")

    with pytest.raises(RuntimeError, match="team case failed"):
        fail_first_case()

    assert teams_application.dependency_overrides == {}
    member = _member()
    with _client(teams_application, second_service, member) as second:
        assert second.cookies.get("teams-case") is None
        assert second.headers.get("X-Teams-Case") is None
        assert "teams_case" not in second.app_state
        assert second.get("/api/v1/admin/teams").status_code == 403
        assert second.get("/api/v1/teams").status_code == 200

    first_service.list_admin_teams.assert_called_once_with(query=None, limit=100, cursor=None)
    first_service.list_visible_teams.assert_not_called()
    second_service.list_admin_teams.assert_not_called()
    second_service.list_visible_teams.assert_called_once_with(
        member, query=None, limit=100, cursor=None
    )
    assert teams_application.dependency_overrides == {}
