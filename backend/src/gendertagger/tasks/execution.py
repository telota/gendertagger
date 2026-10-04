"""Celery task binding for asynchronous classification-batch execution.

The task is a thin wrapper: it rebuilds the small envelope and delegates to the
application :class:`~gendertagger.services.execution.BatchExecutor`. It never
imports the FastAPI layer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from celery import shared_task

from gendertagger.models.run import TaskBatchMessage
from gendertagger.services.dispatch import jittered_exponential_retry_delay
from gendertagger.services.execution import (
    DEFAULT_MAX_BATCH_ATTEMPTS,
    BatchExecutor,
    TransientBatchError,
)
from gendertagger.tasks.worker_resources import get_worker_resources

EXECUTE_BATCH_TASK_NAME = "gendertagger.tasks.execute_batch"


def _batch_executor() -> BatchExecutor:
    """Compose the batch executor from the executing process's shared resources."""
    resources = get_worker_resources()
    classification = resources.classification
    return BatchExecutor(
        unit_of_work_factory=resources.create_unit_of_work,
        method_registry=classification.method_registry,
        clock=partial(datetime.now, UTC),
        worker_provenance=classification.worker_provenance,
        lookup_asset_resolver=classification.lookup_resolver,
        model_directory_resolver=classification.model_resolver,
    )


# Celery's shared_task is untyped; the task body below is fully annotated.
@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name=EXECUTE_BATCH_TASK_NAME,
    max_retries=DEFAULT_MAX_BATCH_ATTEMPTS - 1,
)
def execute_batch(self: Any, *, method_execution_id: str, task_batch_id: str) -> None:
    """Execute one persisted batch; retry transient failures with backoff."""
    message = TaskBatchMessage(
        method_execution_id=method_execution_id,  # type: ignore[arg-type]  # Pydantic coerces str.
        task_batch_id=task_batch_id,  # type: ignore[arg-type]  # Pydantic coerces str.
    )
    try:
        _batch_executor().execute(
            message,
            worker_task_id=self.request.id or "unknown",
            attempt_count=self.request.retries + 1,
            max_attempts=DEFAULT_MAX_BATCH_ATTEMPTS,
        )
    except TransientBatchError as error:
        countdown = jittered_exponential_retry_delay(
            self.request.retries + 1,
            base=timedelta(seconds=2),
            maximum=timedelta(seconds=60),
        ).total_seconds()
        raise self.retry(exc=error, countdown=countdown) from error
