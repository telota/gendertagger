"""Celery task binding for asynchronous dataset-snapshot imports."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from functools import lru_cache, partial
from pathlib import Path
from typing import Any
from weakref import finalize

from celery import shared_task
from pydantic import Field

from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.project import SnapshotImportTaskMessage
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.snapshot_import import (
    DEFAULT_MAX_SNAPSHOT_IMPORT_ATTEMPTS,
    SnapshotImportExecutor,
    TransientSnapshotImportError,
)
from gendertagger.storage.local import LocalArtifactStorage
from gendertagger.tasks.execution import WorkerSettings

EXECUTE_SNAPSHOT_IMPORT_TASK_NAME = "gendertagger.tasks.execute_snapshot_import"
_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 60.0


class SnapshotImportWorkerSettings(WorkerSettings):
    """Validated database, artifact-storage, and import worker settings."""

    artifact_root: Path = Path("data/artifacts")
    tei_import_batch_record_count: int = Field(default=500, gt=0, le=10_000)


def _retry_countdown(retries: int) -> float:
    """Return full-jitter exponential backoff for one import retry."""
    ceiling = min(_RETRY_BASE_SECONDS * (2**retries), _RETRY_MAX_SECONDS)
    return random.uniform(0.0, ceiling)  # noqa: S311 - retry jitter is not security-sensitive


@lru_cache(maxsize=1)
def _snapshot_import_executor() -> SnapshotImportExecutor:
    """Build the process-wide snapshot-import executor from worker settings."""
    settings = SnapshotImportWorkerSettings()  # type: ignore[call-arg]
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    executor = SnapshotImportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(settings.artifact_root),
        parser=TeiPersonParser(),
        clock=partial(datetime.now, UTC),
        import_batch_record_count=settings.tei_import_batch_record_count,
    )
    finalize(executor, engine.dispose)
    return executor


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
        raise self.retry(exc=error, countdown=_retry_countdown(self.request.retries)) from error
