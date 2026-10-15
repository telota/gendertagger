from collections.abc import Sequence
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import Field, SecretStr, ValidationError

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user
from gendertagger.api.dependencies import get_method_registry, get_project_access_service
from gendertagger.api.settings import AppSettings
from gendertagger.methods.base import MethodConfig
from gendertagger.models.classification import PredictionResult, PredictionStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.models.user import CurrentUser, ProjectRole
from gendertagger.services.method_registry import (
    MethodRegistration,
    MethodRegistry,
    default_method_registry,
)
from gendertagger.services.ports.project_access_repository import ProjectScope
from gendertagger.services.ports.unit_of_work import UnitOfWork

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64


class EmptyMethodConfig(MethodConfig):
    pass


class _StubMethod:
    descriptor = MethodDescriptor(
        name="stub_method",
        implementation_version="stub_v1",
        normalization_version="stub_normalization_v1",
    )
    config_model = EmptyMethodConfig

    def predict_batch(
        self, people: Sequence[PersonInput], config: EmptyMethodConfig
    ) -> list[PredictionResult]:
        del config
        return [
            PredictionResult(label=None, status=PredictionStatus.abstain, raw_label=None)
            for _ in people
        ]


_STUB = _StubMethod()


def _registration(descriptor: MethodDescriptor) -> MethodRegistration:
    return MethodRegistration(
        descriptor=descriptor,
        config_model=EmptyMethodConfig,
        adapter=_STUB,
        queue_name="cpu",
        batch_size=100,
    )


def _unused_unit_of_work_factory() -> UnitOfWork:
    raise AssertionError("dependency override must bypass persistence")


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
        display_name="Method viewer",
        roles=set(),
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
    application.dependency_overrides[get_project_access_service] = _GrantingProjectAccess
    if registry is not None:
        application.dependency_overrides[get_method_registry] = lambda: registry
    return TestClient(application)


def test_methods_endpoint_lists_registered_methods_in_name_order() -> None:
    response = _application_client().get("/api/v1/methods")

    assert response.status_code == 200
    names = [method["name"] for method in response.json()]
    assert names == [
        "gender_guesser",
        "gnd",
        "hf_distilbert",
        "hf_genderize",
        "hivoto",
        "hivoto_xgboost",
        "local_llm",
        "nomquamgender",
        "parenthetical_qualifier",
        "wiki_gendersort",
    ]


def test_default_registry_routes_every_method_to_the_expected_queue() -> None:
    registrations = default_method_registry().registrations

    assert [registration.descriptor.name for registration in registrations] == [
        "gender_guesser",
        "gnd",
        "hf_distilbert",
        "hf_genderize",
        "hivoto",
        "hivoto_xgboost",
        "local_llm",
        "nomquamgender",
        "parenthetical_qualifier",
        "wiki_gendersort",
    ]
    for registration in registrations:
        expected_queue = "llm" if registration.descriptor.name == "local_llm" else "cpu"
        assert registration.queue_name == expected_queue
        assert registration.batch_size > 0


def test_methods_endpoint_reports_available_true_for_a_config_that_validates_empty() -> None:
    registry = MethodRegistry(
        [
            _registration(
                MethodDescriptor(
                    name="stub_method",
                    implementation_version="stub_v1",
                    normalization_version="stub_normalization_v1",
                )
            ),
        ]
    )

    response = _application_client(registry).get("/api/v1/methods")

    assert response.status_code == 200
    [method] = response.json()
    assert method["available"] is True


def test_methods_endpoint_reports_available_false_when_the_config_requires_a_field() -> None:
    class RequiredFieldConfig(MethodConfig):
        lookup_sha256: str = Field(min_length=1)

    registry = MethodRegistry(
        [
            MethodRegistration(
                descriptor=MethodDescriptor(
                    name="needs_config",
                    implementation_version="v1",
                    normalization_version="normalization_v1",
                ),
                config_model=RequiredFieldConfig,
                adapter=_STUB,
                queue_name="cpu",
                batch_size=100,
            ),
        ]
    )

    response = _application_client(registry).get("/api/v1/methods")

    assert response.status_code == 200
    [method] = response.json()
    assert method["available"] is False


def test_default_registry_reports_only_the_unconfigured_methods_as_unavailable() -> None:
    # The same registry a real deployment with no lookup/model assets configured gets: exactly
    # the three methods with no required configuration are available. A snapshot of
    # *which* methods that is, so adding a new required field to one of them is a visible,
    # deliberate change here rather than a silent regression.
    registry = default_method_registry()

    availability = {
        registration.descriptor.name: _is_available_for_test(registration)
        for registration in registry.registrations
    }

    assert availability == {
        "gender_guesser": True,
        "gnd": False,
        "hf_distilbert": False,
        "hf_genderize": False,
        "hivoto": False,
        "hivoto_xgboost": False,
        "local_llm": False,
        "nomquamgender": True,
        "parenthetical_qualifier": True,
        "wiki_gendersort": False,
    }


def _is_available_for_test(registration: MethodRegistration) -> bool:
    try:
        registration.config_model.model_validate({})
    except ValidationError:
        return False
    return True


def test_methods_endpoint_returns_descriptors_in_stable_name_order() -> None:
    registry = MethodRegistry(
        [
            _registration(
                MethodDescriptor(
                    name="z_method",
                    implementation_version="z_v1",
                    normalization_version="z_normalization_v1",
                )
            ),
            _registration(
                MethodDescriptor(
                    name="a_method",
                    implementation_version="a_v1",
                    normalization_version="a_normalization_v1",
                )
            ),
        ]
    )

    response = _application_client(registry).get("/api/v1/methods")

    assert response.status_code == 200
    assert [method["name"] for method in response.json()] == ["a_method", "z_method"]
