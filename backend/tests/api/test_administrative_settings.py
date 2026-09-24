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
    BrandingEditableValues,
    BrandingSettingField,
)
from gendertagger.models.branding import BrandingInfo
from gendertagger.models.user import CurrentUser, GlobalRole
from gendertagger.services.admin_settings import AdminSettingsService
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
) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    if user is not None:

        def authenticated_user(request: Request) -> CurrentUser:
            request.state.must_change_password = password_change_required
            return user

        application.dependency_overrides[require_authenticated_user] = authenticated_user
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
