"""API coverage for the ADR-0040 administrative settings read endpoint."""

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
from gendertagger.api.dependencies import get_admin_settings_service
from gendertagger.api.settings import AppSettings
from gendertagger.models.admin_settings import (
    AdminSettings,
    AdminSettingsReset,
    AdminSettingsUpdate,
    AggregationSettingsUpdate,
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
        allow_partial_reference_aggregation=True,
    )


@pytest.fixture(scope="module")
def administrative_settings_application() -> FastAPI:
    """Compose fixed routes while each test supplies fresh settings responses and principals."""
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
    application: FastAPI,
    service: object,
    *,
    user: CurrentUser | None = None,
    password_change_required: bool = False,
    csrf_valid: bool = True,
) -> Generator[TestClient, None, None]:
    previous_overrides = application.dependency_overrides
    assert previous_overrides == {}, "a previous administrative settings case leaked overrides"
    application.dependency_overrides = {}
    if user is not None:

        def authenticated_user(request: Request) -> CurrentUser:
            request.state.must_change_password = password_change_required
            return user

        application.dependency_overrides[require_authenticated_user] = authenticated_user
        if csrf_valid:
            application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_admin_settings_service] = lambda: service
    try:
        with TestClient(application) as client:
            yield client
    finally:
        application.dependency_overrides = previous_overrides


def test_admin_settings_returns_only_approved_data_without_cache(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)
    settings = _settings()
    service.get_settings.return_value = settings

    with _client(administrative_settings_application, service, user=_admin()) as client:
        response = client.get("/api/v1/admin/settings")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == settings.model_dump(mode="json")
    assert "database_url" not in response.text
    assert "artifact_root" not in response.text
    service.get_settings.assert_called_once_with()


def test_admin_settings_rejects_unauthenticated_requests(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)

    with _client(administrative_settings_application, service) as client:
        response = client.get("/api/v1/admin/settings")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    service.get_settings.assert_not_called()


def test_admin_settings_rejects_non_administrators(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)

    with _client(administrative_settings_application, service, user=_operator()) as client:
        response = client.get("/api/v1/admin/settings")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    service.get_settings.assert_not_called()


def test_admin_settings_enforces_the_existing_password_current_gate(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)

    with _client(
        administrative_settings_application,
        service,
        user=_admin(),
        password_change_required=True,
    ) as client:
        response = client.get("/api/v1/admin/settings")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "password_change_required"
    service.get_settings.assert_not_called()


def test_admin_settings_maps_storage_outages_without_fallback(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)
    service.get_settings.side_effect = SettingsUnavailableError("primary unavailable")

    with _client(administrative_settings_application, service, user=_admin()) as client:
        response = client.get("/api/v1/admin/settings")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "settings_unavailable"
    assert "primary unavailable" not in response.text


def test_admin_settings_patch_forwards_validated_command_without_cache(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)
    settings = _settings()
    service.update_settings.return_value = settings
    command = AdminSettingsUpdate(
        expected_revision=2,
        branding=BrandingOverrides(institution_name="Updated Institute", editors=[]),
    )

    with _client(administrative_settings_application, service, user=_admin()) as client:
        response = client.patch(
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


def test_admin_settings_reset_forwards_validated_command_without_cache(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)
    settings = _settings()
    service.reset_settings.return_value = settings
    command = AdminSettingsReset(
        expected_revision=2,
        fields=[BrandingSettingField.contact_email],
    )

    with _client(administrative_settings_application, service, user=_admin()) as client:
        response = client.post(
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


def test_admin_settings_aggregation_patch_forwards_validated_command_without_cache(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)
    settings = _settings()
    service.update_aggregation_settings.return_value = settings
    command = AggregationSettingsUpdate(expected_revision=2, allow_partial_reference_aggregation=False)

    with _client(administrative_settings_application, service, user=_admin()) as client:
        response = client.patch(
            "/api/v1/admin/settings/aggregation",
            json={"expected_revision": 2, "allow_partial_reference_aggregation": False},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == settings.model_dump(mode="json")
    service.update_aggregation_settings.assert_called_once_with(
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
        ("/api/v1/admin/settings/aggregation", {"expected_revision": 2}),
        (
            "/api/v1/admin/settings/aggregation",
            {"expected_revision": 2, "allow_partial_reference_aggregation": "not-a-bool"},
        ),
    ],
)
def test_admin_settings_mutations_reject_invalid_commands(
    administrative_settings_application: FastAPI,
    path: str,
    payload: dict[str, object],
) -> None:
    service = Mock(spec=AdminSettingsService)

    with _client(administrative_settings_application, service, user=_admin()) as client:
        response = (
            client.post(path, json=payload)
            if path.endswith("/reset")
            else client.patch(path, json=payload)
        )

    assert response.status_code == 422
    service.update_settings.assert_not_called()
    service.reset_settings.assert_not_called()
    service.update_aggregation_settings.assert_not_called()


def test_admin_settings_mutations_enforce_existing_csrf_protection(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)

    with _client(
        administrative_settings_application, service, user=_admin(), csrf_valid=False
    ) as client:
        response = client.patch(
            "/api/v1/admin/settings",
            json={"expected_revision": 2, "branding": {"editors": []}},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    service.update_settings.assert_not_called()


def test_admin_settings_mutations_map_stale_revisions(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)
    service.update_settings.side_effect = SettingsRevisionConflictError(
        expected_revision=2,
        current_revision=3,
    )

    with _client(administrative_settings_application, service, user=_admin()) as client:
        response = client.patch(
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


def test_admin_settings_mutations_map_storage_outages(
    administrative_settings_application: FastAPI,
) -> None:
    service = Mock(spec=AdminSettingsService)
    service.reset_settings.side_effect = SettingsUnavailableError("primary unavailable")

    with _client(administrative_settings_application, service, user=_admin()) as client:
        response = client.post(
            "/api/v1/admin/settings/reset",
            json={"expected_revision": 2, "fields": ["contact_email"]},
        )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "settings_unavailable"
    assert "primary unavailable" not in response.text


def test_admin_settings_clients_isolate_security_services_and_state_after_a_case_fails(
    administrative_settings_application: FastAPI,
) -> None:
    first_service = Mock(spec=AdminSettingsService)
    second_service = Mock(spec=AdminSettingsService)
    settings = _settings()
    second_service.get_settings.return_value = settings

    def fail_first_case() -> None:
        with _client(
            administrative_settings_application,
            first_service,
            user=_admin(),
            password_change_required=True,
        ) as first:
            first.cookies.set("settings-case", "first")
            first.headers["X-Settings-Case"] = "first"
            first.app_state["settings_case"] = "first"
            assert first.get("/api/v1/admin/settings").status_code == 403
            raise RuntimeError("settings case failed")

    with pytest.raises(RuntimeError, match="settings case failed"):
        fail_first_case()

    assert administrative_settings_application.dependency_overrides == {}
    with _client(
        administrative_settings_application, second_service, user=_admin(), csrf_valid=False
    ) as second:
        assert second.cookies.get("settings-case") is None
        assert second.headers.get("X-Settings-Case") is None
        assert "settings_case" not in second.app_state
        response = second.get("/api/v1/admin/settings")
        assert response.status_code == 200
        assert response.json() == settings.model_dump(mode="json")
        assert (
            second.patch(
                "/api/v1/admin/settings", json={"expected_revision": 2, "branding": {"editors": []}}
            ).status_code
            == 403
        )

    with _client(administrative_settings_application, first_service, user=_operator()) as operator:
        assert operator.get("/api/v1/admin/settings").status_code == 403
    with _client(administrative_settings_application, first_service) as anonymous:
        assert anonymous.get("/api/v1/admin/settings").status_code == 401

    first_service.get_settings.assert_not_called()
    second_service.get_settings.assert_called_once_with()
    second_service.update_settings.assert_not_called()
    assert administrative_settings_application.dependency_overrides == {}
