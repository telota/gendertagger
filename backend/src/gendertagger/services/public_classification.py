"""Bounded anonymous classification using canonical adapters and durable job resources."""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import timedelta
from threading import Event, Thread
from uuid import UUID, uuid4

from pydantic import JsonValue, ValidationError

from gendertagger.config.public_classification import (
    QUICK_PUBLIC_CLASSIFICATION_METHODS,
    PublicClassificationPolicy,
)
from gendertagger.methods.base import MethodDependencyError
from gendertagger.methods.sqlite_lookup import LookupAssetResolver
from gendertagger.models.artifact import ModelManifestMetadata
from gendertagger.models.classification import PredictionResult, PredictionStatus
from gendertagger.models.common import UtcDatetime, canonical_json_sha256
from gendertagger.models.dispatch import PublicClassificationDispatchCreate
from gendertagger.models.public_classification import (
    PublicClassificationJob,
    PublicClassificationJobAccepted,
    PublicClassificationJobRecord,
    PublicClassificationMethod,
    PublicClassificationMethods,
    PublicClassificationProvenance,
    PublicClassificationResponse,
    PublicClassificationTaskMessage,
    PublicClassifyNamesRequest,
)
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.models.synchronous_classification import ClassifyNamesResponse
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.runs import RunProvenance
from gendertagger.services.runtime_provenance import installed_dependency_versions

_PRIVATE_CONFIG_FIELDS = frozenset(
    {
        "api_key",
        "base_url",
        "password",
        "token",
        "secret",
        "path",
        "cache_root",
        "model_path",
        "storage_uri",
        "lookup_path",
        "source_path",
        "model_directory",
        "cache_dir",
    }
)


class PublicMethodUnavailableError(ValueError):
    """A requested method is outside the deployment's public allowlist."""


class PublicClassificationUnavailableError(RuntimeError):
    """Deployment-owned configuration or assets cannot serve anonymous classification."""


def _public_value(value: JsonValue) -> JsonValue:
    """Remove deployment-only fields recursively from public evidence and scientific settings."""
    if isinstance(value, dict):
        return {
            key: _public_value(item)
            for key, item in value.items()
            if not _is_private_config_value(key, item)
        }
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return value


def _is_private_config_value(key: str, value: JsonValue) -> bool:
    """Recognize known deployment fields and filesystem-based model identifiers."""
    return key in _PRIVATE_CONFIG_FIELDS or (
        key == "model"
        and isinstance(value, str)
        and (value.startswith(("/", "./", "../", "~", "\\")) or ":\\" in value)
    )


def _public_config(config: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Return scientific settings without deployment endpoints, credentials, or paths."""
    return {
        key: _public_value(value)
        for key, value in config.items()
        if not _is_private_config_value(key, value)
    }


def _safe_predictions(
    predictions: list[dict[str, PredictionResult]],
) -> list[dict[str, PredictionResult]]:
    """Preserve normalization evidence while sanitizing adapter errors and deployment fields."""
    return [
        {
            name: prediction.model_copy(
                update={
                    "raw_output": {"error": "Method execution failed."}
                    if prediction.status is PredictionStatus.error
                    else _public_config(prediction.raw_output),
                    "metadata": _public_config(prediction.metadata),
                }
            )
            for name, prediction in person.items()
        }
        for person in predictions
    ]


def _safe_response(response: ClassifyNamesResponse) -> ClassifyNamesResponse:
    """Keep outcomes and raw labels while replacing internal method diagnostics."""
    return ClassifyNamesResponse(
        results=[
            result.model_copy(
                update={
                    "classifications": {
                        name: classification.model_copy(
                            update={
                                "error_message": "Method execution failed."
                                if classification.error_message
                                else None
                            }
                        )
                        for name, classification in result.classifications.items()
                    }
                }
            )
            for result in response.results
        ]
    )


class PublicClassificationService:
    """Expose selectable bounded name classification without granting project access."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        method_registry: MethodRegistry,
        direct_service: DirectClassificationService,
        policy: PublicClassificationPolicy,
        provenance: RunProvenance,
        clock: Callable[[], UtcDatetime],
        dependency_versions: dict[str, str] | None = None,
        asset_resolver: LookupAssetResolver | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._method_registry = method_registry
        self._direct_service = direct_service
        self._policy = policy
        self._provenance = provenance
        self._clock = clock
        self._dependency_versions = (
            dependency_versions
            if dependency_versions is not None
            else installed_dependency_versions()
        )
        self._asset_resolver = asset_resolver

    def list_methods(self) -> PublicClassificationMethods:
        """Return only deployment-allowlisted method descriptors and execution limits."""
        methods = []
        for name in self._policy.methods:
            registration = self._method_registry.registration_for(name)
            if registration is None:
                raise PublicClassificationUnavailableError("Public classification is unavailable.")
            methods.append(
                PublicClassificationMethod(
                    descriptor=registration.descriptor,
                    asynchronous=name not in QUICK_PUBLIC_CLASSIFICATION_METHODS,
                )
            )
        return PublicClassificationMethods(
            methods=methods, synchronous_batch_size=self._policy.synchronous_batch_size
        )

    def classify(
        self, command: PublicClassifyNamesRequest
    ) -> PublicClassificationResponse | PublicClassificationJobAccepted:
        """Return immediate results or atomically accept a reproducible asynchronous job."""
        names = command.ordered_names()
        methods = list(command.methods if command.methods is not None else self._policy.methods)
        if any(name not in self._policy.methods for name in methods):
            raise PublicMethodUnavailableError("A requested method is not publicly available.")
        configs = self._resolve_configs(methods)
        provenance = self._resolved_provenance(methods, configs)
        queue_name = self._dispatch_queue(methods)
        if len(names) <= self._policy.synchronous_batch_size and set(methods).issubset(
            QUICK_PUBLIC_CLASSIFICATION_METHODS
        ):
            response, predictions = self._direct_service.classify_names_with_evidence(
                names, methods, configs
            )
            return PublicClassificationResponse(
                **_safe_response(response).model_dump(),
                provenance=provenance,
                predictions=_safe_predictions(predictions),
            )

        token = secrets.token_urlsafe(32)
        job = PublicClassificationJobRecord(
            id=uuid4(),
            queue_name=queue_name,
            retrieval_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
            names=names,
            methods=methods,
            resolved_method_configs=configs,
            provenance=provenance,
            created_at=self._clock(),
        )
        with self._unit_of_work_factory() as unit_of_work:
            job = unit_of_work.public_classifications.add_job(job)
            unit_of_work.dispatches.ensure_dispatch(
                PublicClassificationDispatchCreate(
                    classification_job_id=job.id,
                    queue_name=queue_name,
                    payload=PublicClassificationTaskMessage(classification_job_id=job.id),
                    available_at=job.created_at,
                )
            )
            unit_of_work.commit()
        return PublicClassificationJobAccepted(
            **self._job_projection(job).model_dump(), retrieval_token=token
        )

    def _dispatch_queue(self, methods: list[str]) -> str:
        """Run combined selections on their dedicated non-CPU worker when one is required."""
        queues = {
            registration.queue_name
            for name in methods
            if (registration := self._method_registry.registration_for(name)) is not None
            and registration.queue_name != CPU_QUEUE
        }
        if len(queues) > 1:
            raise PublicClassificationUnavailableError(
                "The selected methods need incompatible workers."
            )
        return next(iter(queues), CPU_QUEUE)

    def get_job(self, job_id: UUID, retrieval_token: str | None) -> PublicClassificationJob:
        """Read one job only when its anonymous retrieval capability matches."""
        if not retrieval_token:
            raise ResourceNotFoundError("Classification job does not exist.")
        with self._unit_of_work_factory() as unit_of_work:
            job = unit_of_work.public_classifications.get_job(job_id)
        digest = hashlib.sha256(retrieval_token.encode()).hexdigest()
        if job is None or not hmac.compare_digest(job.retrieval_token_sha256, digest):
            raise ResourceNotFoundError("Classification job does not exist.")
        return self._job_projection(job)

    def execute_job(self, job_id: UUID) -> None:
        """Lease and execute one persisted job; redelivery cannot mutate terminal results."""
        now = self._clock()
        lease_id = uuid4()
        with self._unit_of_work_factory() as unit_of_work:
            job = unit_of_work.public_classifications.claim_job(
                job_id,
                now=now,
                lease_until=now + timedelta(seconds=self._policy.job_lease_seconds),
                lease_id=lease_id,
            )
            unit_of_work.commit()
        if job is None:
            return
        try:
            expected = self._resolved_provenance(job.methods, job.resolved_method_configs)
            if expected != job.provenance:
                raise PublicClassificationUnavailableError("Execution provenance changed.")
            stop_heartbeat = Event()
            heartbeat = Thread(
                target=self._renew_lease, args=(job.id, lease_id, stop_heartbeat), daemon=True
            )
            heartbeat.start()
            try:
                results = []
                raw_predictions = []
                for offset in range(0, len(job.names), 200):
                    chunk_response, chunk_predictions = (
                        self._direct_service.classify_names_with_evidence(
                            job.names[offset : offset + 200],
                            job.methods,
                            job.resolved_method_configs,
                        )
                    )
                    results.extend(chunk_response.results)
                    raw_predictions.extend(chunk_predictions)
                response = ClassifyNamesResponse(results=results)
            finally:
                stop_heartbeat.set()
                heartbeat.join(timeout=5)
        except Exception:  # noqa: BLE001 - diagnostics stay within the worker boundary.
            with self._unit_of_work_factory() as unit_of_work:
                unit_of_work.public_classifications.fail_job(
                    job_id, lease_id=lease_id, completed_at=self._clock()
                )
                unit_of_work.commit()
            return
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.public_classifications.complete_job(
                job_id,
                lease_id=lease_id,
                response=response,
                raw_predictions=raw_predictions,
                completed_at=self._clock(),
            )
            unit_of_work.commit()

    def _renew_lease(self, job_id: UUID, lease_id: UUID, stop: Event) -> None:
        """Extend a live worker's lease without permitting stale owners to change job results."""
        while not stop.wait(self._policy.job_lease_seconds / 3):
            try:
                with self._unit_of_work_factory() as unit_of_work:
                    renewed = unit_of_work.public_classifications.renew_job_lease(
                        job_id,
                        lease_id=lease_id,
                        lease_until=self._clock()
                        + timedelta(seconds=self._policy.job_lease_seconds),
                    )
                    unit_of_work.commit()
                if not renewed:
                    return
            except Exception:  # noqa: BLE001 - an expired lease can be recovered by the outbox.
                return

    def _resolve_configs(self, methods: list[str]) -> dict[str, dict[str, JsonValue]]:
        configs: dict[str, dict[str, JsonValue]] = {}
        for name in methods:
            registration = self._method_registry.registration_for(name)
            if registration is None:
                raise PublicClassificationUnavailableError("Public classification is unavailable.")
            if name == "local_llm" and not self._policy.method_revisions.get(name, "").strip():
                raise PublicClassificationUnavailableError("Public classification is unavailable.")
            raw = dict(self._policy.method_configs.get(name, {}))
            if registration.data_artifact_logical_type is not None and "lookup_sha256" not in raw:
                with self._unit_of_work_factory() as unit_of_work:
                    artifact = unit_of_work.artifacts.get_latest_artifact(
                        registration.data_artifact_logical_type
                    )
                if artifact is None:
                    raise PublicClassificationUnavailableError(
                        "Public classification is unavailable."
                    )
                raw["lookup_sha256"] = artifact.sha256
            try:
                configs[name] = registration.config_model.model_validate(raw).model_dump(
                    mode="json"
                )
                if registration.data_artifact_logical_type is not None:
                    self._validate_assets(
                        name,
                        registration.data_artifact_logical_type,
                        str(configs[name]["lookup_sha256"]),
                    )
            except ValidationError as error:
                raise PublicClassificationUnavailableError(
                    "Public classification is unavailable."
                ) from error
        return configs

    def _validate_assets(self, method_name: str, logical_type: str, sha256: str) -> None:
        """Reject missing pinned assets, corrupt bytes, and unavailable model manifest members."""
        if self._asset_resolver is None:
            raise PublicClassificationUnavailableError("Public classification is unavailable.")
        try:
            path = self._asset_resolver.materialize(logical_type, sha256)
            if logical_type.endswith("_model_manifest"):
                manifest = ModelManifestMetadata.model_validate_json(path.read_bytes())
                if manifest.method_name != method_name:
                    raise PublicClassificationUnavailableError(
                        "Public classification is unavailable."
                    )
                member_type = logical_type.removesuffix("_manifest") + "_file"
                for member in manifest.members:
                    self._asset_resolver.materialize(member_type, member.sha256)
        except (MethodDependencyError, OSError, ValidationError) as error:
            raise PublicClassificationUnavailableError(
                "Public classification is unavailable."
            ) from error

    def _resolved_provenance(
        self, methods: list[str], configs: dict[str, dict[str, JsonValue]]
    ) -> PublicClassificationProvenance:
        descriptors = []
        for name in methods:
            registration = self._method_registry.registration_for(name)
            if registration is None:
                raise PublicClassificationUnavailableError("Public classification is unavailable.")
            descriptors.append(registration.descriptor)
        return PublicClassificationProvenance(
            methods=descriptors,
            method_configs={name: _public_config(config) for name, config in configs.items()},
            method_revisions={
                name: self._policy.method_revisions[name]
                for name in methods
                if name in self._policy.method_revisions
            },
            resolved_config_sha256=canonical_json_sha256(dict(configs)),
            code_git_commit=self._provenance.code_git_commit,
            application_version=self._provenance.application_version,
            python_version=self._provenance.python_version,
            dependency_lock_sha256=self._provenance.dependency_lock_sha256,
            dependency_versions=self._dependency_versions,
            container_image_digest=self._provenance.container_image_digest,
        )

    @staticmethod
    def _job_projection(job: PublicClassificationJobRecord) -> PublicClassificationJob:
        response = None
        if job.response is not None:
            response = PublicClassificationResponse(
                **_safe_response(job.response).model_dump(),
                provenance=job.provenance,
                predictions=_safe_predictions(job.raw_predictions or []),
            )
        return PublicClassificationJob(
            id=job.id,
            status=job.status,
            name_count=len(job.names),
            provenance=job.provenance,
            response=response,
            failure_code=job.failure_code,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
