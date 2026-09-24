"""API coverage for the ADR-0040 administrative settings read endpoint."""

from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user, require_csrf_protection
from gendertagger.api.dependencies import get_admin_settings_service
from gendertagger.api.settings import AppSettings
from gendertagger.models.admin_settings import (
    AdminSettings,
    AdminSettingsReset,
    AdminSettingsUpdate,
    BrandingEditableValues,
    BrandingOverrides,
    BrandingSettingField,
)
from gendertagger.models.branding import BrandingInfo
from gendertagger.models.user import CurrentUser, GlobalRole
from gendertagger.services.admin_settings import (
    AdminSettingsService,
    SettingsRevisionConflictError,
)
from gendertagger.services.ports.persistence_errors import SettingsUnavailableError
from gendertagger.services.ports.unit_of_work import UnitOfWork

pytestmark = pytest.mark.unit

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
USER_ID = UUID("10000000-0000-0000-0000-000000000001")


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("the route test must not open persistence")


def _admin() -> CurrentUser:
    return CurrentUser(id=USER_ID, display_name="Administrator", roles={GlobalRole.admin})


def _operator() -> CurrentUser:
    return CurrentUser(id=USER_ID, display_name="Operator", roles={GlobalRole.operator})


def _settings() -> AdminSettings:
    defaults = BrandingEditableValues(
        institution_name="Environment Institute",
        institution_url="https://environment.example",
        contact_email="environment@example.org",
        privacy_notice_url="/privacy",
        editors=["Environment Editor"],
        published_since_year=2020,
    )
    return AdminSettings(
        revision=2,
        branding=BrandingInfo(
            institution_name="Stored Institute",
            logo_url="/api/v1/branding/logo",
            editors=["Environment Editor"],
        ),
        branding_defaults=defaults,
        overridden_fields=[BrandingSettingField.institution_name],
    )


def _client(
    service: object,
    *,
    user: CurrentUser | None = None,
    password_change_required: bool = False,
    csrf_valid: bool = True,
) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
        request_id_factory=lambda: "request-123",
    )
    if user is not None:

        def authenticated_user(request: Request) -> CurrentUser:
            request.state.must_change_password = password_change_required
            return user

        application.dependency_overrides[require_authenticated_user] = authenticated_user
        if csrf_valid:
            application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_admin_settings_service] = lambda: service
    return TestClient(application)


def test_admin_settings_returns_only_approved_data_without_cache() -> None:
    service = Mock(spec=AdminSettingsService)
    settings = _settings()
    service.get_settings.return_value = settings

    response = _client(service, user=_admin()).get("/api/v1/admin/settings")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == settings.model_dump(mode="json")
    assert "database_url" not in response.text
    assert "artifact_root" not in response.text
    service.get_settings.assert_called_once_with()


def test_admin_settings_rejects_unauthenticated_requests() -> None:
    service = Mock(spec=AdminSettingsService)

    response = _client(service).get("/api/v1/admin/settings")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    service.get_settings.assert_not_called()


def test_admin_settings_rejects_non_administrators() -> None:
    service = Mock(spec=AdminSettingsService)

    response = _client(service, user=_operator()).get("/api/v1/admin/settings")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    service.get_settings.assert_not_called()


def test_admin_settings_enforces_the_existing_password_current_gate() -> None:
    service = Mock(spec=AdminSettingsService)

    response = _client(
        service,
        user=_admin(),
        password_change_required=True,
    ).get("/api/v1/admin/settings")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "password_change_required"
    service.get_settings.assert_not_called()


def test_admin_settings_maps_storage_outages_without_fallback() -> None:
    service = Mock(spec=AdminSettingsService)
    service.get_settings.side_effect = SettingsUnavailableError("primary unavailable")

    response = _client(service, user=_admin()).get("/api/v1/admin/settings")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "settings_unavailable"
    assert "primary unavailable" not in response.text


def test_admin_settings_patch_forwards_validated_command_without_cache() -> None:
    service = Mock(spec=AdminSettingsService)
    settings = _settings()
    service.update_settings.return_value = settings
    command = AdminSettingsUpdate(
        expected_revision=2,
        branding=BrandingOverrides(institution_name="Updated Institute", editors=[]),
    )

    response = _client(service, user=_admin()).patch(
        "/api/v1/admin/settings",
        json={
            "expected_revision": 2,
            "branding": {"institution_name": "Updated Institute", "editors": []},
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == settings.model_dump(mode="json")
    service.update_settings.assert_called_once_with(
        command,
        actor_user_id=USER_ID,
        request_id="request-123",
    )


def test_admin_settings_reset_forwards_validated_command_without_cache() -> None:
    service = Mock(spec=AdminSettingsService)
    settings = _settings()
    service.reset_settings.return_value = settings
    command = AdminSettingsReset(
        expected_revision=2,
        fields=[BrandingSettingField.contact_email],
    )

    response = _client(service, user=_admin()).post(
        "/api/v1/admin/settings/reset",
        json={"expected_revision": 2, "fields": ["contact_email"]},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    service.reset_settings.assert_called_once_with(
        command,
        actor_user_id=USER_ID,
        request_id="request-123",
    )


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/admin/settings", {"expected_revision": 2, "branding": {}}),
        ("/api/v1/admin/settings", {"expected_revision": 2, "branding": {"unknown": "value"}}),
        ("/api/v1/admin/settings/reset", {"expected_revision": 2, "fields": []}),
        (
            "/api/v1/admin/settings/reset",
            {"expected_revision": 2, "fields": ["contact_email", "contact_email"]},
        ),
    ],
)
def test_admin_settings_mutations_reject_invalid_commands(
    path: str,
    payload: dict[str, object],
) -> None:
    service = Mock(spec=AdminSettingsService)

    response = (
        _client(service, user=_admin()).patch(path, json=payload)
        if path.endswith("/settings")
        else _client(service, user=_admin()).post(path, json=payload)
    )

    assert response.status_code == 422
    service.update_settings.assert_not_called()
    service.reset_settings.assert_not_called()


def test_admin_settings_mutations_enforce_existing_csrf_protection() -> None:
    service = Mock(spec=AdminSettingsService)

    response = _client(service, user=_admin(), csrf_valid=False).patch(
        "/api/v1/admin/settings",
        json={"expected_revision": 2, "branding": {"editors": []}},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    service.update_settings.assert_not_called()


def test_admin_settings_mutations_map_stale_revisions() -> None:
    service = Mock(spec=AdminSettingsService)
    service.update_settings.side_effect = SettingsRevisionConflictError(
        expected_revision=2,
        current_revision=3,
    )

    response = _client(service, user=_admin()).patch(
        "/api/v1/admin/settings",
        json={"expected_revision": 2, "branding": {"editors": []}},
    )

    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"] == {
        "code": "settings_revision_conflict",
        "message": "The administrative settings have changed.",
        "details": {"expected_revision": 2, "current_revision": 3},
        "request_id": "request-123",
    }


def test_admin_settings_mutations_map_storage_outages() -> None:
    service = Mock(spec=AdminSettingsService)
    service.reset_settings.side_effect = SettingsUnavailableError("primary unavailable")

    response = _client(service, user=_admin()).post(
        "/api/v1/admin/settings/reset",
        json={"expected_revision": 2, "fields": ["contact_email"]},
    )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "settings_unavailable"
    assert "primary unavailable" not in response.text
