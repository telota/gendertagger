"""Preference routes preserve ownership, closed commands, and existing security gates."""

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
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


@pytest.fixture(scope="module")
def preferences_application() -> FastAPI:
    """Compose fixed preference routes once without sharing service or request state."""
    return create_app(
        settings=AppSettings(
            database_url=SecretStr("postgresql+psycopg://api:secret@localhost/gendertagger"),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
        request_id_factory=lambda: "preferences-request-123",
    )


@contextmanager
def _client(
    application: FastAPI,
    service: object,
    *,
    authenticated: bool = True,
    password_change_required: bool = False,
    csrf_valid: bool = True,
) -> Generator[TestClient, None, None]:
    previous_overrides = application.dependency_overrides
    assert previous_overrides == {}, "a previous preference case leaked dependency overrides"
    application.dependency_overrides = {}
    if authenticated:

        def authenticated_user(request: Request) -> CurrentUser:
            request.state.must_change_password = password_change_required
            return CurrentUser(id=USER_ID, display_name="Account without grants", roles=set())

        application.dependency_overrides[require_authenticated_user] = authenticated_user
        if csrf_valid:
            application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_user_preferences_service] = lambda: service
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides = previous_overrides


def test_preferences_get_uses_principal_and_requires_no_role_or_csrf(
    preferences_application: FastAPI,
) -> None:
    service = Mock(spec=UserPreferencesService)
    service.get_preferences.return_value = UserPreferences()

    with _client(preferences_application, service, csrf_valid=False) as client:
        response = client.get(PREFERENCES_PATH)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == UserPreferences().model_dump(mode="json")
    service.get_preferences.assert_called_once_with(user_id=USER_ID)


def test_preferences_patch_forwards_only_supplied_fields_and_principal(
    preferences_application: FastAPI,
) -> None:
    service = Mock(spec=UserPreferencesService)
    saved = UserPreferences(revision=3, locale=None, theme="dark", desktop_sidebar_collapsed=True)
    service.update_preferences.return_value = saved

    with _client(preferences_application, service) as client:
        response = client.patch(
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
def test_preferences_require_a_resolved_session(
    preferences_application: FastAPI, method: str
) -> None:
    service = Mock(spec=UserPreferencesService)

    with _client(preferences_application, service, authenticated=False) as client:
        response = client.request(
            method,
            PREFERENCES_PATH,
            json={"expected_revision": 0, "theme": "dark"} if method == "PATCH" else None,
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    service.get_preferences.assert_not_called()
    service.update_preferences.assert_not_called()


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_preferences_require_a_current_password(
    preferences_application: FastAPI, method: str
) -> None:
    service = Mock(spec=UserPreferencesService)

    with _client(preferences_application, service, password_change_required=True) as client:
        response = client.request(
            method,
            PREFERENCES_PATH,
            json={"expected_revision": 0, "theme": "dark"} if method == "PATCH" else None,
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "password_change_required"
    service.get_preferences.assert_not_called()
    service.update_preferences.assert_not_called()


def test_preferences_patch_requires_existing_csrf_protection(
    preferences_application: FastAPI,
) -> None:
    service = Mock(spec=UserPreferencesService)

    with _client(preferences_application, service, csrf_valid=False) as client:
        response = client.patch(
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
    preferences_application: FastAPI,
    payload: dict[str, object],
) -> None:
    service = Mock(spec=UserPreferencesService)

    with _client(preferences_application, service) as client:
        response = client.patch(PREFERENCES_PATH, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    service.update_preferences.assert_not_called()


def test_preferences_patch_maps_revision_conflict_to_established_error_envelope(
    preferences_application: FastAPI,
) -> None:
    service = Mock(spec=UserPreferencesService)
    service.update_preferences.side_effect = PreferencesRevisionConflictError(
        expected_revision=2,
        current_revision=3,
    )

    with _client(preferences_application, service) as client:
        response = client.patch(
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
    preferences_application: FastAPI,
    method: str,
    exception: type[Exception],
    expected_status: int,
    code: str,
) -> None:
    service = Mock(spec=UserPreferencesService)
    service.get_preferences.side_effect = exception
    service.update_preferences.side_effect = exception

    with _client(preferences_application, service) as client:
        response = client.request(
            method,
            PREFERENCES_PATH,
            json={"expected_revision": 0, "theme": "dark"} if method == "PATCH" else None,
        )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == code


def test_preferences_clients_isolate_security_and_client_state_after_a_case_fails(
    preferences_application: FastAPI,
) -> None:
    first_service = Mock(spec=UserPreferencesService)
    second_service = Mock(spec=UserPreferencesService)
    second_service.get_preferences.return_value = UserPreferences()

    def fail_first_case() -> None:
        with _client(
            preferences_application, first_service, password_change_required=True
        ) as first:
            first.cookies.set("preferences-case", "first")
            first.headers["X-Preferences-Case"] = "first"
            first.app_state["preferences_case"] = "first"
            assert first.get(PREFERENCES_PATH).status_code == 403
            raise RuntimeError("preference case failed")

    with pytest.raises(RuntimeError, match="preference case failed"):
        fail_first_case()

    assert preferences_application.dependency_overrides == {}
    with _client(preferences_application, second_service, csrf_valid=False) as second:
        assert second.cookies.get("preferences-case") is None
        assert second.headers.get("X-Preferences-Case") is None
        assert "preferences_case" not in second.app_state
        assert second.get(PREFERENCES_PATH).status_code == 200
        rejected = second.patch(PREFERENCES_PATH, json={"expected_revision": 0, "theme": "dark"})
        assert rejected.status_code == 403

    with _client(preferences_application, first_service, authenticated=False) as anonymous:
        assert anonymous.get(PREFERENCES_PATH).status_code == 401

    first_service.get_preferences.assert_not_called()
    first_service.update_preferences.assert_not_called()
    second_service.get_preferences.assert_called_once_with(user_id=USER_ID)
    second_service.update_preferences.assert_not_called()
    assert preferences_application.dependency_overrides == {}
