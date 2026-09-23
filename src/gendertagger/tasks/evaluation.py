"""Celery task binding for asynchronous evaluation execution.

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
from gendertagger.models.evaluation import EvaluationTaskMessage
from gendertagger.services.evaluation_execution import (
    DEFAULT_MAX_EVALUATION_ATTEMPTS,
    EvaluationExecutor,
    TransientEvaluationError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

EXECUTE_EVALUATION_TASK_NAME = "gendertagger.tasks.execute_evaluation"
_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 60.0
_MAX_EVALUATION_REPORT_BYTES = 50 * 1024 * 1024


def _retry_countdown(retries: int) -> float:
    """Return full-jitter exponential backoff for one evaluation retry."""
    ceiling = min(_RETRY_BASE_SECONDS * (2**retries), _RETRY_MAX_SECONDS)
    return random.uniform(0.0, ceiling)  # noqa: S311 - retry jitter is not security-sensitive


@lru_cache(maxsize=1)
def _evaluation_executor() -> EvaluationExecutor:
    """Build the process-wide evaluation executor from worker settings once."""
    settings = RuntimeSettings()  # type: ignore[call-arg]  # Values come from settings sources.
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    executor = EvaluationExecutor(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(settings.artifact_root),
        max_report_bytes=_MAX_EVALUATION_REPORT_BYTES,
        clock=partial(datetime.now, UTC),
    )
    finalize(executor, engine.dispose)
    return executor


# Celery's shared_task is untyped; the task body below is fully annotated.
@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name=EXECUTE_EVALUATION_TASK_NAME,
    max_retries=DEFAULT_MAX_EVALUATION_ATTEMPTS - 1,
)
def execute_evaluation(self: Any, *, evaluation_execution_id: str) -> None:
    """Execute one persisted evaluation and retry transient failures."""
    message = EvaluationTaskMessage(
        evaluation_execution_id=evaluation_execution_id,  # type: ignore[arg-type]
    )
    try:
        _evaluation_executor().execute(
            message,
            attempt_count=self.request.retries + 1,
            max_attempts=DEFAULT_MAX_EVALUATION_ATTEMPTS,
        )
    except TransientEvaluationError as error:
        raise self.retry(exc=error, countdown=_retry_countdown(self.request.retries)) from error
