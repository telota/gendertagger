from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user, require_csrf_protection
from gendertagger.api.dependencies import get_user_administration_service
from gendertagger.api.settings import AppSettings
from gendertagger.models.api import CursorPage
from gendertagger.models.auth import (
    AdminUser,
    AdminUserCreate,
    AdminUserCreateResult,
    AdminUserPasswordResetResult,
    AdminUserUpdate,
)
from gendertagger.models.user import CurrentUser, GlobalRole
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    DuplicateUsernameError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.user_administration import (
    AdminUserStateConflictError,
    UserAdministrationService,
)

pytestmark = pytest.mark.unit

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
USER_ID = UUID("10000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("the route test must not open persistence")


def _admin() -> CurrentUser:
    return CurrentUser(id=USER_ID, display_name="Administrator", roles={GlobalRole.admin})


def _client(service: object) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
        request_id_factory=lambda: "request-123",
    )
    application.dependency_overrides[require_authenticated_user] = _admin
    application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_user_administration_service] = lambda: service
    return TestClient(application)


def test_admin_user_route_serializes_page_and_forwards_query() -> None:
    service = Mock(spec=UserAdministrationService)
    user = AdminUser(
        id=USER_ID,
        display_name="Administrator",
        username="admin",
        roles={GlobalRole.admin},
        is_active=True,
        must_change_password=False,
        created_at=NOW,
    )
    service.list_users.return_value = CursorPage(
        items=[user],
        next_cursor=None,
        has_more=False,
    )

    response = _client(service).get(
        "/api/v1/admin/users",
        params={"query": "admin", "limit": 25},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [user.model_dump(mode="json")],
        "next_cursor": None,
        "has_more": False,
    }
    service.list_users.assert_called_once_with(query="admin", limit=25, cursor=None)


def test_admin_user_route_normalizes_invalid_cursor_error() -> None:
    service = Mock(spec=UserAdministrationService)
    service.list_users.side_effect = InvalidCursorError("unreadable")

    response = _client(service).get("/api/v1/admin/users", params={"cursor": "invalid"})

    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"reason": "invalid_cursor"}


def test_admin_user_creation_returns_temporary_password_without_cache() -> None:
    service = Mock(spec=UserAdministrationService)
    account = AdminUser(
        id=USER_ID,
        display_name="New user",
        username="new.user",
        roles={GlobalRole.operator},
        is_active=True,
        must_change_password=True,
        created_at=NOW,
    )
    service.create_user.return_value = AdminUserCreateResult(
        account=account,
        temporary_password="temporary-password",
    )

    response = _client(service).post(
        "/api/v1/admin/users",
        json={
            "display_name": "New user",
            "username": "NEW.USER",
            "roles": ["operator"],
        },
    )

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "account": account.model_dump(mode="json"),
        "temporary_password": "temporary-password",
    }
    service.create_user.assert_called_once_with(
        AdminUserCreate(
            display_name="New user",
            username="new.user",
            roles={GlobalRole.operator},
        ),
        actor_user_id=USER_ID,
        request_id="request-123",
    )


def test_admin_user_creation_maps_duplicate_username_to_stable_conflict() -> None:
    service = Mock(spec=UserAdministrationService)
    service.create_user.side_effect = DuplicateUsernameError("existing")

    response = _client(service).post(
        "/api/v1/admin/users",
        json={"display_name": "Duplicate", "username": "existing", "roles": []},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "username_conflict"
    assert "temporary_password" not in response.text


def test_admin_user_password_reset_discloses_temporary_password_without_cache() -> None:
    service = Mock(spec=UserAdministrationService)
    service.reset_user_password.return_value = AdminUserPasswordResetResult(
        temporary_password="new-temporary-password"
    )

    response = _client(service).post(f"/api/v1/admin/users/{USER_ID}/reset-password")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"temporary_password": "new-temporary-password"}
    service.reset_user_password.assert_called_once_with(
        USER_ID,
        actor_user_id=USER_ID,
        request_id="request-123",
    )


def test_admin_user_update_forwards_patch_and_serializes_account() -> None:
    service = Mock(spec=UserAdministrationService)
    account = AdminUser(
        id=USER_ID,
        display_name="Renamed administrator",
        username="admin",
        roles={GlobalRole.admin, GlobalRole.operator},
        is_active=True,
        must_change_password=False,
        created_at=NOW,
    )
    service.update_user.return_value = account

    response = _client(service).patch(
        f"/api/v1/admin/users/{USER_ID}",
        json={"display_name": "Renamed administrator", "roles": ["admin", "operator"]},
    )

    assert response.status_code == 200
    assert response.json() == account.model_dump(mode="json")
    service.update_user.assert_called_once_with(
        USER_ID,
        AdminUserUpdate(
            display_name="Renamed administrator",
            roles={GlobalRole.admin, GlobalRole.operator},
        ),
        actor_user_id=USER_ID,
        request_id="request-123",
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": None},
        {"roles": None},
        {"is_active": None},
        {"display_name": "   "},
        {"username": "changed"},
    ],
)
def test_admin_user_update_rejects_null_blank_and_immutable_fields(
    payload: dict[str, object],
) -> None:
    response = _client(Mock(spec=UserAdministrationService)).patch(
        f"/api/v1/admin/users/{USER_ID}",
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "error",
    [
        ResourceNotFoundError("not local"),
        AdminUserStateConflictError(
            code="self_deactivation_forbidden",
            message="Administrators cannot deactivate their own account.",
        ),
    ],
)
def test_admin_user_update_maps_not_found_and_state_conflicts(error: Exception) -> None:
    service = Mock(spec=UserAdministrationService)
    service.update_user.side_effect = error

    response = _client(service).patch(
        f"/api/v1/admin/users/{USER_ID}",
        json={"display_name": "Unchanged"},
    )

    expected_status = 404 if isinstance(error, ResourceNotFoundError) else 409
    assert response.status_code == expected_status
    expected_code = (
        "resource_not_found"
        if isinstance(error, ResourceNotFoundError)
        else "self_deactivation_forbidden"
    )
    assert response.json()["error"]["code"] == expected_code
