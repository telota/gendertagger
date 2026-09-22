from collections.abc import Sequence
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.authentication import require_authenticated_user, require_csrf_protection
from gendertagger.api.dependencies import (
    get_classification_service,
    get_method_registry,
    get_project_access_service,
)
from gendertagger.api.settings import AppSettings
from gendertagger.methods.base import MethodConfig, MethodDependencyError
from gendertagger.methods.gender_guesser import GenderGuesserMethod
from gendertagger.methods.nomquamgender import NomquamgenderMethod
from gendertagger.methods.parenthetical_qualifier import ParentheticalQualifierMethod
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.models.user import CurrentUser, ProjectRole
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.method_registry import MethodRegistration, MethodRegistry
from gendertagger.services.project_access_repository import ProjectScope
from gendertagger.services.unit_of_work import UnitOfWork

DATABASE_URL = "postgresql+psycopg://api:secret@localhost/gendertagger"
CODE_GIT_COMMIT = "a" * 40
DEPENDENCY_LOCK_SHA256 = "b" * 64


class _FakeNomquamAnnotator:
    def annotate(self, names: Sequence[str]) -> list[list[Any]]:
        return [[name, name.lower(), 0, 0, 0.95 if name == "Maria" else 0.05] for name in names]


class _StubFailingMethod:
    descriptor = MethodDescriptor(
        name="failing_method",
        implementation_version="failing_v1",
        normalization_version="failing_norm_v1",
    )
    config_model = MethodConfig

    def predict_batch(self, people: Sequence[PersonInput], config: Any) -> list[PredictionResult]:
        del people, config
        msg = "Failing adapter dependency missing"
        raise MethodDependencyError(msg)


def _build_test_registry() -> MethodRegistry:
    return MethodRegistry(
        [
            MethodRegistration(
                descriptor=ParentheticalQualifierMethod.descriptor,
                config_model=ParentheticalQualifierMethod.config_model,
                adapter=ParentheticalQualifierMethod(),
                queue_name="cpu",
                batch_size=100,
            ),
            MethodRegistration(
                descriptor=GenderGuesserMethod.descriptor,
                config_model=GenderGuesserMethod.config_model,
                adapter=GenderGuesserMethod(),
                queue_name="cpu",
                batch_size=100,
            ),
            MethodRegistration(
                descriptor=NomquamgenderMethod.descriptor,
                config_model=NomquamgenderMethod.config_model,
                adapter=NomquamgenderMethod(annotator_factory=_FakeNomquamAnnotator),
                queue_name="cpu",
                batch_size=100,
            ),
            MethodRegistration(
                descriptor=_StubFailingMethod.descriptor,
                config_model=_StubFailingMethod.config_model,
                adapter=_StubFailingMethod(),
                queue_name="cpu",
                batch_size=100,
            ),
        ]
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
        display_name="Classify user",
        roles=set(),
    )


def _application_client(
    registry: MethodRegistry | None = None,
    user: CurrentUser | None = None,
) -> TestClient:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    if user is not None:
        application.dependency_overrides[require_authenticated_user] = lambda: user
    else:
        application.dependency_overrides[require_authenticated_user] = _authenticated_user
    application.dependency_overrides[require_csrf_protection] = lambda: None
    application.dependency_overrides[get_project_access_service] = _GrantingProjectAccess
    if registry is not None:
        application.dependency_overrides[get_method_registry] = lambda: registry
        application.dependency_overrides[get_classification_service] = lambda: (
            DirectClassificationService(method_registry=registry)
        )
    return TestClient(application)


def test_classify_endpoint_requires_authentication() -> None:
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr(DATABASE_URL),
            code_git_commit=CODE_GIT_COMMIT,
            dependency_lock_sha256=DEPENDENCY_LOCK_SHA256,
        ),
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    client = TestClient(application)
    response = client.post("/api/v1/classify", json={"names": ["Maria"]})
    assert response.status_code == 401


def test_classify_endpoint_accepts_single_name_field() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post(
        "/api/v1/classify",
        json={"name": "Maria", "methods": ["gender_guesser"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["name"] == "Maria"
    classifications = data["results"][0]["classifications"]
    assert "gender_guesser" in classifications
    assert classifications["gender_guesser"]["label"] == "female"
    assert classifications["gender_guesser"]["status"] == "success"
    assert data["results"][0]["aggregated"]["label"] == "female"
    assert data["results"][0]["aggregated"]["outcome"] == "decided"


def test_classify_endpoint_accepts_names_string() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post(
        "/api/v1/classify",
        json={"names": "Maria", "methods": ["gender_guesser"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["name"] == "Maria"


def test_classify_endpoint_accepts_list_of_names_and_defaults_to_all_methods() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post(
        "/api/v1/classify",
        json={"names": ["Maria", "Heinrich", "Schmidt (Frau des Heinrich)"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 3

    # Maria
    maria = data["results"][0]
    assert maria["name"] == "Maria"
    assert maria["classifications"]["gender_guesser"]["label"] == "female"
    assert maria["classifications"]["nomquamgender"]["label"] == "female"
    assert maria["classifications"]["parenthetical_qualifier"]["status"] == "abstain"

    # Frau
    frau = data["results"][2]
    assert frau["name"] == "Schmidt (Frau des Heinrich)"
    assert frau["classifications"]["parenthetical_qualifier"]["label"] == "female"
    assert frau["classifications"]["parenthetical_qualifier"]["status"] == "success"


def test_classify_endpoint_with_custom_method_config() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post(
        "/api/v1/classify",
        json={
            "names": ["Maria"],
            "methods": ["nomquamgender"],
            "method_configs": {"nomquamgender": {"threshold": 0.2}},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["classifications"]["nomquamgender"]["label"] == "female"


def test_classify_endpoint_handles_method_error_gracefully() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post(
        "/api/v1/classify",
        json={"names": ["Maria"], "methods": ["gender_guesser", "failing_method"]},
    )
    assert response.status_code == 200
    data = response.json()
    classifications = data["results"][0]["classifications"]
    assert classifications["gender_guesser"]["status"] == "success"
    assert classifications["failing_method"]["status"] == "error"
    assert classifications["failing_method"]["label"] is None
    assert (
        "Failing adapter dependency missing" in classifications["failing_method"]["error_message"]
    )


def test_classify_endpoint_rejects_unknown_method_with_422() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post(
        "/api/v1/classify",
        json={"names": ["Maria"], "methods": ["nonexistent_method"]},
    )
    assert response.status_code == 422
    assert "nonexistent_method" in response.json()["error"]["message"]


def test_classify_endpoint_rejects_invalid_method_name_pattern() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post(
        "/api/v1/classify",
        json={"names": ["Maria"], "methods": ["INVALID-NAME!"]},
    )
    assert response.status_code == 422


def test_classify_endpoint_rejects_empty_names() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post("/api/v1/classify", json={"names": []})
    assert response.status_code == 422


def test_classify_endpoint_rejects_blank_names() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post("/api/v1/classify", json={"names": ["  "]})
    assert response.status_code == 422


def test_classify_endpoint_rejects_exceeding_max_batch_size() -> None:
    client = _application_client(registry=_build_test_registry())
    response = client.post("/api/v1/classify", json={"names": ["Maria"] * 1001})
    assert response.status_code == 422


def test_classify_endpoint_runs_full_default_method_suite() -> None:
    client = _application_client()
    response = client.post(
        "/api/v1/classify",
        json={"names": ["Maria", "Heinrich", "Schmidt (Frau des Heinrich)"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 3

    expected_methods = {
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
    }

    for result in data["results"]:
        assert set(result["classifications"].keys()) == expected_methods

    # Maria checks
    maria_classifications = data["results"][0]["classifications"]
    assert maria_classifications["gender_guesser"]["label"] == "female"
    assert maria_classifications["gender_guesser"]["status"] == "success"
    assert maria_classifications["parenthetical_qualifier"]["status"] == "abstain"

    # Heinrich checks
    heinrich_classifications = data["results"][1]["classifications"]
    assert heinrich_classifications["gender_guesser"]["label"] == "male"
    assert heinrich_classifications["gender_guesser"]["status"] == "success"

    # Frau checks
    frau_classifications = data["results"][2]["classifications"]
    assert frau_classifications["parenthetical_qualifier"]["label"] == "female"
    assert frau_classifications["parenthetical_qualifier"]["status"] == "success"

    # Aggregated results for full suite
    assert data["results"][0]["aggregated"]["label"] == "female"
    assert data["results"][0]["aggregated"]["outcome"] == "decided"
    assert data["results"][0]["aggregated"]["certainty_tier"] is not None
    assert data["results"][1]["aggregated"]["label"] == "male"
    assert data["results"][1]["aggregated"]["outcome"] == "decided"
    assert data["results"][2]["aggregated"]["label"] == "female"
    assert data["results"][2]["aggregated"]["override_source"] == "parenthetical_qualifier"
