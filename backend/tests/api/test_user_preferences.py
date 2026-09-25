"""Preference routes preserve ownership, closed commands, and existing security gates."""

from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user, require_csrf_protection
from gendertagger.api.dependencies import get_user_preferences_service
from gendertagger.api.settings import AppSettings
from gendertagger.models.user import CurrentUser
from gendertagger.models.user_preferences import UserPreferences, UserPreferencesUpdate
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.user_preferences import (
    PreferencesAccountUnavailableError,
    PreferencesPasswordChangeRequiredError,
    PreferencesRevisionConflictError,
    UserPreferencesService,
)

pytestmark = pytest.mark.unit

USER_ID = UUID("10000000-0000-0000-0000-000000000001")
PREFERENCES_PATH = "/api/v1/me/preferences"


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("the route test must not open persistence")


def _client(
    service: object,
    *,
    authenticated: bool = True,
    password_change_required: bool = False,
    csrf_valid: bool = True,
) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr("postgresql+psycopg://api:secret@localhost/gendertagger"),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
        request_id_factory=lambda: "preferences-request-123",
    )
    if authenticated:

        def authenticated_user(request: Request) -> CurrentUser:
            request.state.must_change_password = password_change_required
            return CurrentUser(id=USER_ID, display_name="Account without grants", roles=set())

        application.dependency_overrides[require_authenticated_user] = authenticated_user
        if csrf_valid:
            application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_user_preferences_service] = lambda: service
    return TestClient(application)


def test_preferences_get_uses_principal_and_requires_no_role_or_csrf() -> None:
    service = Mock(spec=UserPreferencesService)
    service.get_preferences.return_value = UserPreferences()

    response = _client(service, csrf_valid=False).get(PREFERENCES_PATH)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == UserPreferences().model_dump(mode="json")
    service.get_preferences.assert_called_once_with(user_id=USER_ID)


def test_preferences_patch_forwards_only_supplied_fields_and_principal() -> None:
    service = Mock(spec=UserPreferencesService)
    saved = UserPreferences(revision=3, locale=None, theme="dark", desktop_sidebar_collapsed=True)
    service.update_preferences.return_value = saved

    response = _client(service).patch(
        PREFERENCES_PATH,
        json={"expected_revision": 2, "locale": None},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == saved.model_dump(mode="json")
    service.update_preferences.assert_called_once_with(
        UserPreferencesUpdate(expected_revision=2, locale=None),
        user_id=USER_ID,
    )
    forwarded = service.update_preferences.call_args.args[0]
    assert forwarded.model_fields_set == {"expected_revision", "locale"}


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_preferences_require_a_resolved_session(method: str) -> None:
    service = Mock(spec=UserPreferencesService)

    response = _client(service, authenticated=False).request(
        method,
        PREFERENCES_PATH,
        json={"expected_revision": 0, "theme": "dark"} if method == "PATCH" else None,
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    service.get_preferences.assert_not_called()
    service.update_preferences.assert_not_called()


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_preferences_require_a_current_password(method: str) -> None:
    service = Mock(spec=UserPreferencesService)

    response = _client(service, password_change_required=True).request(
        method,
        PREFERENCES_PATH,
        json={"expected_revision": 0, "theme": "dark"} if method == "PATCH" else None,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "password_change_required"
    service.get_preferences.assert_not_called()
    service.update_preferences.assert_not_called()


def test_preferences_patch_requires_existing_csrf_protection() -> None:
    service = Mock(spec=UserPreferencesService)

    response = _client(service, csrf_valid=False).patch(
        PREFERENCES_PATH,
        json={"expected_revision": 0, "theme": "dark"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    service.update_preferences.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_revision": 0},
        {"theme": "dark"},
        {"expected_revision": 0, "locale": "fr"},
        {"expected_revision": 0, "theme": None},
        {"expected_revision": 0, "desktop_sidebar_collapsed": "false"},
        {"expected_revision": True, "theme": "dark"},
        {"expected_revision": "0", "theme": "dark"},
        {"expected_revision": 0, "theme": "dark", "user_id": str(USER_ID)},
        {"expected_revision": 0, "revision": 1, "theme": "dark"},
    ],
)
def test_preferences_patch_rejects_invalid_commands_with_shared_envelope(
    payload: dict[str, object],
) -> None:
    service = Mock(spec=UserPreferencesService)

    response = _client(service).patch(PREFERENCES_PATH, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    service.update_preferences.assert_not_called()


def test_preferences_patch_maps_revision_conflict_to_established_error_envelope() -> None:
    service = Mock(spec=UserPreferencesService)
    service.update_preferences.side_effect = PreferencesRevisionConflictError(
        expected_revision=2,
        current_revision=3,
    )

    response = _client(service).patch(
        PREFERENCES_PATH,
        json={"expected_revision": 2, "theme": "dark"},
    )

    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    error = response.json()["error"]
    assert error["code"] == "preferences_revision_conflict"
    assert error["details"] == {"expected_revision": 2, "current_revision": 3}
    assert error["request_id"] == "preferences-request-123"
    assert isinstance(error["message"], str)


@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize(
    ("exception", "expected_status", "code"),
    [
        (PreferencesAccountUnavailableError, 401, "authentication_required"),
        (PreferencesPasswordChangeRequiredError, 403, "password_change_required"),
    ],
)
def test_preferences_apply_fresh_account_eligibility_errors(
    method: str,
    exception: type[Exception],
    expected_status: int,
    code: str,
) -> None:
    service = Mock(spec=UserPreferencesService)
    service.get_preferences.side_effect = exception
    service.update_preferences.side_effect = exception

    response = _client(service).request(
        method,
        PREFERENCES_PATH,
        json={"expected_revision": 0, "theme": "dark"} if method == "PATCH" else None,
    )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == code
