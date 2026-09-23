from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user
from gendertagger.api.dependencies import get_project_access_service
from gendertagger.api.settings import AppSettings
from gendertagger.models.api import ApiErrorEnvelope
from gendertagger.models.user import CurrentUser, ProjectRole
from gendertagger.services.ports.project_access_repository import ProjectScope
from gendertagger.services.ports.unit_of_work import UnitOfWork

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("the request must not open persistence")


class _GrantingProjectAccess:
    """Grant the caller operator in every project without persistence."""

    def effective_role(
        self, user: CurrentUser, scope: ProjectScope, resource_id: UUID
    ) -> ProjectRole:
        return ProjectRole.operator

    def has_any_grant(self, user: CurrentUser) -> bool:
        return True


def _authenticated_user() -> CurrentUser:
    return CurrentUser(
        id=UUID("a2f03480-77a7-4f24-82cb-07604d5c2483"),
        display_name="Error contract viewer",
        roles=set(),
    )


def _application() -> FastAPI:
    return create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )


def test_authentication_error_uses_envelope_and_server_request_id() -> None:
    client = TestClient(_application())

    response = client.get(
        "/api/v1/methods",
        headers={"x-request-id": "client-controlled"},
    )

    assert response.status_code == 401
    body = ApiErrorEnvelope.model_validate(response.json())
    assert body.error.code == "authentication_required"
    assert body.error.details == {}
    assert body.error.request_id == response.headers["x-request-id"]
    assert body.error.request_id != "client-controlled"
    UUID(body.error.request_id or "")
    assert response.headers["www-authenticate"] == "Session"


def test_success_response_uses_fresh_server_request_id() -> None:
    application = _application()
    application.dependency_overrides[require_authenticated_user] = _authenticated_user
    application.dependency_overrides[get_project_access_service] = _GrantingProjectAccess
    client = TestClient(application)

    response = client.get(
        "/api/v1/methods",
        headers={"x-request-id": "client-controlled"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "client-controlled"
    UUID(response.headers["x-request-id"])


def test_framework_not_found_uses_resource_error_code() -> None:
    response = TestClient(_application()).get("/api/v1/not-a-resource")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_validation_error_omits_raw_input_and_uses_stable_issues() -> None:
    application = _application()
    application.dependency_overrides[require_authenticated_user] = _authenticated_user
    client = TestClient(application)

    response = client.get("/api/v1/runs/not-a-uuid")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["issues"] == [
        {
            "location": ["path", "run_id"],
            "message": "Input should be a valid UUID, invalid character: found `n` at 1",
            "type": "uuid_parsing",
        }
    ]
    assert "input" not in response.text
    assert body["error"]["request_id"] == response.headers["x-request-id"]


def test_unexpected_exception_hides_diagnostic_and_keeps_request_id() -> None:
    application = _application()

    @application.get("/explode")
    def _explode() -> None:
        raise RuntimeError("sensitive internal diagnostic")

    client = TestClient(application, raise_server_exceptions=False)
    response = client.get("/explode")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "sensitive" not in response.text
    assert body["error"]["request_id"] == response.headers["x-request-id"]
