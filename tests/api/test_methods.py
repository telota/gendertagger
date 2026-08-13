from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user
from gendertagger.api.dependencies import get_method_registry
from gendertagger.api.settings import AppSettings
from gendertagger.methods.base import MethodConfig
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.user import CurrentUser, Role
from gendertagger.services.method_registry import (
    MethodRegistration,
    MethodRegistry,
)
from gendertagger.services.unit_of_work import UnitOfWork

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64


class EmptyMethodConfig(MethodConfig):
    pass


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("dependency override must bypass persistence")


def _authenticated_user() -> CurrentUser:
    return CurrentUser(
        id=UUID("a2f03480-77a7-4f24-82cb-07604d5c2483"),
        display_name="Method viewer",
        roles={Role.viewer},
    )


def _application_client(registry: MethodRegistry | None = None) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    application.dependency_overrides[require_authenticated_user] = _authenticated_user
    if registry is not None:
        application.dependency_overrides[get_method_registry] = lambda: registry
    return TestClient(application)


def test_methods_endpoint_is_empty_before_adapters_are_runnable() -> None:
    response = _application_client().get("/api/v1/methods")

    assert response.status_code == 200
    assert response.json() == []


def test_methods_endpoint_returns_descriptors_in_stable_name_order() -> None:
    registry = MethodRegistry(
        [
            MethodRegistration(
                descriptor=MethodDescriptor(
                    name="z_method",
                    implementation_version="z_v1",
                    normalization_version="z_normalization_v1",
                ),
                config_model=EmptyMethodConfig,
            ),
            MethodRegistration(
                descriptor=MethodDescriptor(
                    name="a_method",
                    implementation_version="a_v1",
                    normalization_version="a_normalization_v1",
                ),
                config_model=EmptyMethodConfig,
            ),
        ]
    )

    response = _application_client(registry).get("/api/v1/methods")

    assert response.status_code == 200
    assert [method["name"] for method in response.json()] == ["a_method", "z_method"]
