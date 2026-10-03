from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.dependencies import get_public_classification_service
from gendertagger.api.settings import AppSettings
from gendertagger.config.public_classification import PublicClassificationPolicy
from gendertagger.methods.adapters.gender_guesser import GenderGuesserMethod
from gendertagger.methods.base import LookupMethodConfig, MethodConfig, MethodDependencyError
from gendertagger.methods.sqlite_lookup import LookupAssetResolver
from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.common import UtcDatetime
from gendertagger.models.public_classification import (
    PublicClassificationJobAccepted,
    PublicClassificationJobRecord,
    PublicClassificationStatus,
    PublicClassifyNamesRequest,
)
from gendertagger.models.synchronous_classification import ClassifyNamesResponse
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.method_registry import MethodRegistration, MethodRegistry
from gendertagger.services.ports.unit_of_work import UnitOfWork
from gendertagger.services.public_classification import (
    PublicClassificationService,
    PublicClassificationUnavailableError,
)
from gendertagger.services.runs import RunProvenance

NOW = datetime(2026, 10, 3, tzinfo=UTC)
pytestmark = pytest.mark.unit


class _SlowMethod:
    descriptor = GenderGuesserMethod.descriptor.model_copy(update={"name": "slow_method"})
    config_model = MethodConfig

    def predict_batch(
        self, people: Sequence[object], config: MethodConfig
    ) -> list[PredictionResult]:
        del config
        return [
            PredictionResult(
                label=CanonicalLabel.female,
                status=PredictionStatus.success,
                raw_label="female",
                raw_output={
                    "answer": "female",
                    "model": "/srv/models/private-weight-directory",
                    "nested": {"api_key": "deployment-secret", "base_url": "http://private-model"},
                },
                metadata={"normalization_version": "test_norm_v1"},
            )
            for _ in people
        ]


class _Jobs:
    def __init__(self) -> None:
        self.jobs: dict[UUID, PublicClassificationJobRecord] = {}

    def add_job(self, record: PublicClassificationJobRecord) -> PublicClassificationJobRecord:
        self.jobs[record.id] = record
        return record

    def get_job(self, job_id: UUID) -> PublicClassificationJobRecord | None:
        return self.jobs.get(job_id)

    def claim_job(
        self, job_id: UUID, *, now: UtcDatetime, lease_until: UtcDatetime, lease_id: UUID
    ) -> PublicClassificationJobRecord | None:
        job = self.jobs.get(job_id)
        if job is None or job.status in {
            PublicClassificationStatus.completed,
            PublicClassificationStatus.failed,
        }:
            return None
        if (
            job.status is PublicClassificationStatus.running
            and job.lease_until is not None
            and job.lease_until > now
        ):
            return None
        claimed = job.model_copy(
            update={
                "status": PublicClassificationStatus.running,
                "lease_id": lease_id,
                "lease_until": lease_until,
                "started_at": now,
            }
        )
        self.jobs[job_id] = claimed
        return claimed

    def complete_job(
        self,
        job_id: UUID,
        *,
        lease_id: UUID,
        response: ClassifyNamesResponse,
        raw_predictions: list[dict[str, PredictionResult]],
        completed_at: UtcDatetime,
    ) -> bool:
        job = self.jobs[job_id]
        if job.lease_id != lease_id:
            return False
        self.jobs[job_id] = job.model_copy(
            update={
                "status": PublicClassificationStatus.completed,
                "response": response,
                "raw_predictions": raw_predictions,
                "completed_at": completed_at,
                "lease_id": None,
                "lease_until": None,
            }
        )
        return True

    def fail_job(self, job_id: UUID, *, lease_id: UUID, completed_at: UtcDatetime) -> bool:
        job = self.jobs[job_id]
        if job.lease_id != lease_id:
            return False
        self.jobs[job_id] = job.model_copy(
            update={
                "status": PublicClassificationStatus.failed,
                "failure_code": "classification_failed",
                "completed_at": completed_at,
                "lease_id": None,
                "lease_until": None,
            }
        )
        return True


class _Dispatches:
    def __init__(self) -> None:
        self.intents: list[Any] = []

    def ensure_dispatch(self, dispatch: Any) -> None:
        self.intents.append(dispatch)


class _UnitOfWork:
    def __init__(self) -> None:
        self.public_classifications = _Jobs()
        self.dispatches = _Dispatches()
        self.commit_count = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        self.commit_count += 1


def _service(
    unit_of_work: _UnitOfWork,
    *,
    dependency_versions: dict[str, str] | None = None,
    queue_name: str = "cpu",
    pinned_asset: bool = False,
    asset_resolver: LookupAssetResolver | None = None,
) -> PublicClassificationService:
    registry = MethodRegistry(
        [
            MethodRegistration(
                descriptor=GenderGuesserMethod.descriptor,
                config_model=GenderGuesserMethod.config_model,
                adapter=GenderGuesserMethod(),
                queue_name="cpu",
                batch_size=200,
            ),
            MethodRegistration(
                descriptor=_SlowMethod.descriptor,
                config_model=LookupMethodConfig if pinned_asset else MethodConfig,
                adapter=cast(Any, _SlowMethod()),
                queue_name=queue_name,
                batch_size=200,
                data_artifact_logical_type="test_lookup" if pinned_asset else None,
            ),
        ]
    )
    return PublicClassificationService(
        unit_of_work_factory=lambda: cast(UnitOfWork, unit_of_work),
        method_registry=registry,
        direct_service=DirectClassificationService(method_registry=registry),
        policy=PublicClassificationPolicy(
            methods=["gender_guesser", "slow_method"],
            method_configs={"slow_method": {"lookup_sha256": "c" * 64}} if pinned_asset else {},
        ),
        provenance=RunProvenance(
            code_git_commit="a" * 40,
            application_version="1.0",
            python_version="3.11",
            dependency_lock_sha256="b" * 64,
        ),
        clock=lambda: NOW,
        dependency_versions=dependency_versions
        if dependency_versions is not None
        else {"test-library": "1.0"},
        asset_resolver=asset_resolver,
    )


@pytest.fixture
def deployment() -> tuple[TestClient, PublicClassificationService, _UnitOfWork]:
    unit_of_work = _UnitOfWork()
    service = _service(unit_of_work)
    application = create_app(
        settings=AppSettings(
            database_url=SecretStr("postgresql+psycopg://unused:unused@localhost/unused"),
            code_git_commit="a" * 40,
            dependency_lock_sha256="b" * 64,
        ),
        unit_of_work_factory=lambda: cast(UnitOfWork, unit_of_work),
    )
    application.dependency_overrides[get_public_classification_service] = lambda: service
    return TestClient(application), service, unit_of_work


def test_public_single_name_without_session_or_csrf_returns_evidence_and_provenance(
    deployment: tuple[TestClient, PublicClassificationService, _UnitOfWork],
) -> None:
    client, _, unit_of_work = deployment
    response = client.post(
        "/api/v1/public/classify", json={"name": " Maria ", "methods": ["gender_guesser"]}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["results"][0]["name"] == "Maria"
    assert body["results"][0]["classifications"]["gender_guesser"]["label"] == "female"
    assert body["predictions"][0]["gender_guesser"]["raw_label"] == "female"
    assert body["predictions"][0]["gender_guesser"]["metadata"]["normalization_version"]
    assert body["provenance"]["dependency_versions"] == {"test-library": "1.0"}
    assert body["provenance"]["methods"][0]["name"] == "gender_guesser"
    assert unit_of_work.commit_count == 0


def test_public_batch_preserves_order_and_duplicate_names(
    deployment: tuple[TestClient, PublicClassificationService, _UnitOfWork],
) -> None:
    client, _, _ = deployment
    response = client.post(
        "/api/v1/public/classify",
        json={"names": ["Maria", "Heinrich", "Maria"], "methods": ["gender_guesser"]},
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["results"]] == ["Maria", "Heinrich", "Maria"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": " "},
        {"names": []},
        {"names": ["Maria", " "]},
        {"name": "Maria", "names": ["Maria"]},
        {"name": "Maria", "methods": []},
        {"name": "Maria", "methods": ["gender_guesser", "gender_guesser"]},
        {"name": "Maria", "method_configs": {"local_llm": {"base_url": "http://private"}}},
        {"name": "Maria", "methods": ["local_llm"]},
        {"name": "x" * 513},
        {"name": "Ada\u0000X"},
        {"names": ["Ada\u0000X"]},
        {"names": ["Maria"] * 10_001},
    ],
)
def test_public_classification_rejects_invalid_or_disallowed_inputs(
    deployment: tuple[TestClient, PublicClassificationService, _UnitOfWork], body: dict[str, Any]
) -> None:
    client, _, unit_of_work = deployment
    assert client.post("/api/v1/public/classify", json=body).status_code == 422
    assert unit_of_work.commit_count == 0


@pytest.mark.parametrize("content", [b'{"name":"Ada\\ud800X"}', b'{"names":["Ada\\udfffX"]}'])
def test_public_classification_rejects_escaped_unpaired_surrogates(
    deployment: tuple[TestClient, PublicClassificationService, _UnitOfWork], content: bytes
) -> None:
    client, _, _ = deployment
    response = client.post(
        "/api/v1/public/classify", content=content, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


def test_public_job_routes_mixed_cpu_and_dedicated_methods_to_the_persisted_queue() -> None:
    unit_of_work = _UnitOfWork()
    service = _service(unit_of_work, queue_name="llm")
    accepted = service.classify(
        PublicClassifyNamesRequest(names=["Maria"], methods=["gender_guesser", "slow_method"])
    )
    assert isinstance(accepted, PublicClassificationJobAccepted)
    assert unit_of_work.public_classifications.jobs[accepted.id].queue_name == "llm"
    assert unit_of_work.dispatches.intents[0].queue_name == "llm"


def test_public_job_rejects_an_explicit_missing_artifact_before_acceptance() -> None:
    class MissingAssetResolver:
        def materialize(self, logical_type: str, sha256: str) -> Path:
            assert logical_type == "test_lookup"
            assert sha256 == "c" * 64
            raise MethodDependencyError("/srv/private-missing-file")

    unit_of_work = _UnitOfWork()
    service = _service(unit_of_work, pinned_asset=True, asset_resolver=MissingAssetResolver())
    with pytest.raises(
        PublicClassificationUnavailableError, match="Public classification is unavailable"
    ):
        service.classify(PublicClassifyNamesRequest(name="Maria", methods=["slow_method"]))
    assert unit_of_work.commit_count == 0
    assert not unit_of_work.public_classifications.jobs


@pytest.mark.parametrize(
    "body",
    [
        {"names": ["Maria"] * 21, "methods": ["gender_guesser"]},
        {"name": "Maria", "methods": ["slow_method"]},
    ],
)
def test_public_classification_accepts_durable_jobs_with_identifier_only_dispatch(
    deployment: tuple[TestClient, PublicClassificationService, _UnitOfWork], body: dict[str, Any]
) -> None:
    client, _, unit_of_work = deployment
    response = client.post("/api/v1/public/classify", json=body)
    assert response.status_code == 202
    accepted = response.json()
    job = unit_of_work.public_classifications.jobs[UUID(accepted["id"])]
    assert response.headers["location"].endswith(accepted["id"])
    assert accepted["status"] == "queued"
    assert accepted["response"] is None
    assert accepted["retrieval_token"] != job.retrieval_token_sha256
    assert unit_of_work.commit_count == 1
    assert unit_of_work.dispatches.intents[0].payload.model_dump(mode="json") == {
        "classification_job_id": accepted["id"]
    }
    assert "names" not in accepted
    assert "task_id" not in accepted


def test_public_job_requires_capability_and_retains_private_evidence_after_completion(
    deployment: tuple[TestClient, PublicClassificationService, _UnitOfWork],
) -> None:
    client, service, unit_of_work = deployment
    acceptance = client.post(
        "/api/v1/public/classify", json={"name": "Maria", "methods": ["slow_method"]}
    )
    body = acceptance.json()
    location = acceptance.headers["location"]
    assert client.get(location).status_code == 404
    assert client.get(location, headers={"X-Classification-Token": "wrong"}).status_code == 404
    headers = {"X-Classification-Token": body["retrieval_token"]}
    assert client.get(location, headers=headers).json()["status"] == "queued"
    service.execute_job(UUID(body["id"]))
    response = client.get(location, headers=headers)
    assert response.status_code == 200
    completed = response.json()
    assert completed["status"] == "completed"
    assert completed["response"]["results"][0]["name"] == "Maria"
    assert "retrieval_token" not in completed
    assert "deployment-secret" not in response.text
    assert "http://private-model" not in response.text
    assert "/srv/models/private-weight-directory" not in response.text
    assert completed["response"]["predictions"][0]["slow_method"]["raw_output"] == {
        "answer": "female",
        "nested": {},
    }
    record = unit_of_work.public_classifications.jobs[UUID(body["id"])]
    assert record.raw_predictions is not None
    assert record.raw_predictions[0]["slow_method"].raw_output["nested"] == {
        "api_key": "deployment-secret",
        "base_url": "http://private-model",
    }
    service.execute_job(record.id)
    assert unit_of_work.public_classifications.jobs[record.id] == record


def test_public_job_rejects_execution_environment_drift(
    deployment: tuple[TestClient, PublicClassificationService, _UnitOfWork],
) -> None:
    client, _, unit_of_work = deployment
    accepted = client.post(
        "/api/v1/public/classify", json={"name": "Maria", "methods": ["slow_method"]}
    ).json()
    changed_worker = _service(unit_of_work, dependency_versions={"test-library": "2.0"})
    changed_worker.execute_job(UUID(accepted["id"]))
    record = unit_of_work.public_classifications.jobs[UUID(accepted["id"])]
    assert record.status is PublicClassificationStatus.failed
    assert record.response is None
    assert record.raw_predictions is None


def test_public_routes_do_not_open_workbench_or_administration(
    deployment: tuple[TestClient, PublicClassificationService, _UnitOfWork],
) -> None:
    client, _, _ = deployment
    discovery = client.get("/api/v1/public/methods")
    assert discovery.status_code == 200
    assert [item["descriptor"]["name"] for item in discovery.json()["methods"]] == [
        "gender_guesser",
        "slow_method",
    ]
    for path in ["/api/v1/projects", "/api/v1/admin/users", "/api/v1/methods"]:
        assert client.get(path).status_code == 401
    assert client.post("/api/v1/classify", json={"name": "Maria"}).status_code == 401


def test_public_acceptance_contract_contains_single_and_batch_names(
    deployment: tuple[TestClient, PublicClassificationService, _UnitOfWork],
) -> None:
    client, _, _ = deployment
    schema = cast(FastAPI, client.app).openapi()
    request = schema["components"]["schemas"]["PublicClassifyNamesRequest"]
    assert {"name", "names", "methods"} == set(request["properties"])
    assert request["additionalProperties"] is False
    assert "202" in schema["paths"]["/api/v1/public/classify"]["post"]["responses"]
    responses = schema["paths"]["/api/v1/public/classify"]["post"]["responses"]
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicClassificationResponse"
    }
    assert responses["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicClassificationJobAccepted"
    }
