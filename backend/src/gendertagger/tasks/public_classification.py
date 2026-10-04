"""Celery binding for persisted anonymous classification jobs.

The identifier-only envelope delegates to the application service directly;
worker crashes recover through persisted leases and outbox reconciliation.
"""

from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any
from uuid import UUID

from celery import shared_task
from sqlalchemy.exc import OperationalError

from gendertagger.models.public_classification import PublicClassificationTaskMessage
from gendertagger.services.dispatch import jittered_exponential_retry_delay
from gendertagger.services.public_classification import PublicClassificationService
from gendertagger.services.runs import RunProvenance
from gendertagger.tasks.worker_resources import get_worker_resources

EXECUTE_PUBLIC_CLASSIFICATION_TASK_NAME = "gendertagger.tasks.execute_public_classification"
_MAX_DATABASE_RETRIES = 5


def _public_classification_service() -> PublicClassificationService:
    """Compose classification lazily from this worker's resources and build evidence."""
    resources = get_worker_resources()
    classification = resources.classification
    provenance = classification.worker_provenance
    return PublicClassificationService(
        unit_of_work_factory=resources.create_unit_of_work,
        method_registry=classification.method_registry,
        direct_service=resources.direct_classification_service,
        policy=classification.settings.public_classification,
        asset_resolver=classification.lookup_resolver,
        provenance=RunProvenance(
            code_git_commit=provenance.code_git_commit,
            application_version=provenance.application_version,
            python_version=provenance.python_version,
            dependency_lock_sha256=provenance.dependency_lock_sha256,
            container_image_digest=provenance.container_image_digest,
        ),
        dependency_versions=provenance.dependency_versions,
        clock=partial(datetime.now, UTC),
    )


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
        countdown = jittered_exponential_retry_delay(
            self.request.retries + 1,
            base=timedelta(seconds=2),
            maximum=timedelta(seconds=60),
        ).total_seconds()
        raise self.retry(exc=error, countdown=countdown) from error
