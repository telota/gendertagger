"""Celery task binding for asynchronous dataset-snapshot imports."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from celery import shared_task

from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.project import SnapshotImportTaskMessage
from gendertagger.services.dispatch import jittered_exponential_retry_delay
from gendertagger.services.snapshot_import import (
    DEFAULT_MAX_SNAPSHOT_IMPORT_ATTEMPTS,
    SnapshotImportExecutor,
    TransientSnapshotImportError,
)
from gendertagger.tasks.worker_resources import get_worker_resources

EXECUTE_SNAPSHOT_IMPORT_TASK_NAME = "gendertagger.tasks.execute_snapshot_import"


def _snapshot_import_executor() -> SnapshotImportExecutor:
    """Compose import with shared artifacts and fresh transaction scopes."""
    resources = get_worker_resources()
    return SnapshotImportExecutor(
        unit_of_work_factory=resources.create_unit_of_work,
        artifact_storage=resources.artifact_storage,
        parser=TeiPersonParser(),
        clock=partial(datetime.now, UTC),
        import_batch_record_count=resources.settings.tei_import_batch_record_count,
    )


# Celery's shared_task is untyped; the task body below is fully annotated.
@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name=EXECUTE_SNAPSHOT_IMPORT_TASK_NAME,
    max_retries=DEFAULT_MAX_SNAPSHOT_IMPORT_ATTEMPTS - 1,
)
def execute_snapshot_import(self: Any, *, dataset_snapshot_id: str) -> None:
    """Import one persisted snapshot and retry transient failures."""
    message = SnapshotImportTaskMessage(
        dataset_snapshot_id=dataset_snapshot_id,  # type: ignore[arg-type]
    )
    try:
        _snapshot_import_executor().execute(
            message,
            attempt_count=self.request.retries + 1,
            max_attempts=DEFAULT_MAX_SNAPSHOT_IMPORT_ATTEMPTS,
        )
    except TransientSnapshotImportError as error:
        countdown = jittered_exponential_retry_delay(
            self.request.retries + 1,
            base=timedelta(seconds=2),
            maximum=timedelta(seconds=60),
        ).total_seconds()
        raise self.retry(exc=error, countdown=countdown) from error
