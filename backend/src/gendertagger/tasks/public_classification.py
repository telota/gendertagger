"""Celery binding for persisted anonymous classification jobs.

The identifier-only envelope delegates to the application service directly;
worker crashes recover through persisted leases and outbox reconciliation.
"""

import random
from datetime import UTC, datetime
from functools import lru_cache, partial
from importlib.metadata import version
from platform import python_version
from typing import Any
from uuid import UUID
from weakref import finalize

from celery import shared_task
from sqlalchemy.exc import OperationalError

from gendertagger.config.settings import ClassificationRuntimeSettings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.public_classification import PublicClassificationTaskMessage
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.lookup_assets import RegisteredLookupAssetResolver
from gendertagger.services.method_registry import default_method_registry
from gendertagger.services.model_assets import RegisteredModelDirectoryResolver
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.public_classification import PublicClassificationService
from gendertagger.services.runs import RunProvenance
from gendertagger.storage.local import LocalArtifactStorage

EXECUTE_PUBLIC_CLASSIFICATION_TASK_NAME = "gendertagger.tasks.execute_public_classification"
_MAX_DATABASE_RETRIES = 5


@lru_cache(maxsize=1)
def _public_classification_service() -> PublicClassificationService:
    """Compose the process-scoped worker service with local model and lookup assets."""
    settings = ClassificationRuntimeSettings()  # type: ignore[call-arg]  # Environment sources.
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    lookup_resolver = RegisteredLookupAssetResolver(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(settings.artifact_root),
    )
    model_resolver = RegisteredModelDirectoryResolver(
        lookup_asset_resolver=lookup_resolver,
        cache_root=settings.model_cache_root,
    )
    registry = default_method_registry(lookup_resolver, model_resolver)
    service = PublicClassificationService(
        unit_of_work_factory=unit_of_work_factory,
        method_registry=registry,
        direct_service=DirectClassificationService(
            method_registry=registry,
            unit_of_work_factory=unit_of_work_factory,
        ),
        policy=settings.public_classification,
        asset_resolver=lookup_resolver,
        provenance=RunProvenance(
            code_git_commit=settings.code_git_commit,
            application_version=version("gendertagger"),
            python_version=python_version(),
            dependency_lock_sha256=settings.dependency_lock_sha256,
            container_image_digest=settings.container_image_digest,
        ),
        clock=partial(datetime.now, UTC),
    )
    finalize(service, engine.dispose)
    return service


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name=EXECUTE_PUBLIC_CLASSIFICATION_TASK_NAME,
    max_retries=_MAX_DATABASE_RETRIES,
)
def execute_public_classification(self: Any, *, classification_job_id: str) -> None:
    """Validate the small broker envelope and execute the leased application job."""
    message = PublicClassificationTaskMessage(classification_job_id=UUID(classification_job_id))
    try:
        _public_classification_service().execute_job(message.classification_job_id)
    except OperationalError as error:
        ceiling = min(2.0 * 2**self.request.retries, 60.0)
        countdown = random.uniform(0.0, ceiling)  # noqa: S311 - Operational retry jitter.
        raise self.retry(exc=error, countdown=countdown) from error
