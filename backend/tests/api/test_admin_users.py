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
from gendertagger.models.auth import AdminUser
from gendertagger.models.user import CurrentUser, GlobalRole
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.user_administration import UserAdministrationService

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
