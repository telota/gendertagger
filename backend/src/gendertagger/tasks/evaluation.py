"""Celery task binding for asynchronous evaluation execution.

The task rebuilds the identifiers-only envelope and calls the application
executor directly. FastAPI remains outside the worker dependency graph.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from celery import shared_task

from gendertagger.models.evaluation import EvaluationTaskMessage
from gendertagger.services.dispatch import jittered_exponential_retry_delay
from gendertagger.services.evaluation_execution import (
    DEFAULT_MAX_EVALUATION_ATTEMPTS,
    EvaluationExecutor,
    TransientEvaluationError,
)
from gendertagger.tasks.worker_resources import get_worker_resources

EXECUTE_EVALUATION_TASK_NAME = "gendertagger.tasks.execute_evaluation"
_MAX_EVALUATION_REPORT_BYTES = 50 * 1024 * 1024


def _evaluation_executor() -> EvaluationExecutor:
    """Compose evaluation with shared artifacts and fresh transaction scopes."""
    resources = get_worker_resources()
    return EvaluationExecutor(
        unit_of_work_factory=resources.create_unit_of_work,
        artifact_storage=resources.artifact_storage,
        max_report_bytes=_MAX_EVALUATION_REPORT_BYTES,
        clock=partial(datetime.now, UTC),
    )


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
        countdown = jittered_exponential_retry_delay(
            self.request.retries + 1,
            base=timedelta(seconds=2),
            maximum=timedelta(seconds=60),
        ).total_seconds()
        raise self.retry(exc=error, countdown=countdown) from error
