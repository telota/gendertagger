"""Celery task binding for asynchronous export execution.

The task rebuilds the identifiers-only envelope and calls the application
executor directly. FastAPI remains outside the worker dependency graph.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from celery import shared_task

from gendertagger.models.export import ExportTaskMessage
from gendertagger.services.dispatch import jittered_exponential_retry_delay
from gendertagger.services.export_execution import (
    DEFAULT_MAX_EXPORT_ATTEMPTS,
    ExportExecutor,
    TransientExportError,
)
from gendertagger.tasks.worker_resources import get_worker_resources

EXECUTE_EXPORT_TASK_NAME = "gendertagger.tasks.execute_export"
_MAX_EXPORT_OUTPUT_BYTES = 200 * 1024 * 1024


def _export_executor() -> ExportExecutor:
    """Compose export with shared artifacts and fresh transaction scopes."""
    resources = get_worker_resources()
    return ExportExecutor(
        unit_of_work_factory=resources.create_unit_of_work,
        artifact_storage=resources.artifact_storage,
        max_output_bytes=_MAX_EXPORT_OUTPUT_BYTES,
        clock=partial(datetime.now, UTC),
    )


# Celery's shared_task is untyped; the task body below is fully annotated.
@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name=EXECUTE_EXPORT_TASK_NAME,
    max_retries=DEFAULT_MAX_EXPORT_ATTEMPTS - 1,
)
def execute_export(self: Any, *, export_execution_id: str) -> None:
    """Execute one persisted export and retry transient failures."""
    message = ExportTaskMessage(export_execution_id=export_execution_id)  # type: ignore[arg-type]
    try:
        _export_executor().execute(
            message,
            attempt_count=self.request.retries + 1,
            max_attempts=DEFAULT_MAX_EXPORT_ATTEMPTS,
        )
    except TransientExportError as error:
        countdown = jittered_exponential_retry_delay(
            self.request.retries + 1,
            base=timedelta(seconds=2),
            maximum=timedelta(seconds=60),
        ).total_seconds()
        raise self.retry(exc=error, countdown=countdown) from error
