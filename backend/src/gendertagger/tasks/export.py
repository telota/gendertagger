"""Celery task binding for asynchronous export execution.

The task rebuilds the identifiers-only envelope and calls the application
executor directly. FastAPI remains outside the worker dependency graph.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from functools import lru_cache, partial
from typing import Any
from weakref import finalize

from celery import shared_task

from gendertagger.config.settings import RuntimeSettings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.export import ExportTaskMessage
from gendertagger.services.export_execution import (
    DEFAULT_MAX_EXPORT_ATTEMPTS,
    ExportExecutor,
    TransientExportError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

EXECUTE_EXPORT_TASK_NAME = "gendertagger.tasks.execute_export"
_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 60.0
_MAX_EXPORT_OUTPUT_BYTES = 200 * 1024 * 1024


def _retry_countdown(retries: int) -> float:
    """Return full-jitter exponential backoff for one export retry."""
    ceiling = min(_RETRY_BASE_SECONDS * (2**retries), _RETRY_MAX_SECONDS)
    return random.uniform(0.0, ceiling)  # noqa: S311 - retry jitter is not security-sensitive


@lru_cache(maxsize=1)
def _export_executor() -> ExportExecutor:
    """Build the process-wide export executor from worker settings once."""
    settings = RuntimeSettings()  # type: ignore[call-arg]  # Values come from settings sources.
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    executor = ExportExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(settings.artifact_root),
        max_output_bytes=_MAX_EXPORT_OUTPUT_BYTES,
        clock=partial(datetime.now, UTC),
    )
    finalize(executor, engine.dispose)
    return executor


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
        raise self.retry(exc=error, countdown=_retry_countdown(self.request.retries)) from error
