"""Celery task binding for asynchronous reference aggregation execution.

The task rebuilds the identifiers-only envelope and calls the application
executor directly. FastAPI remains outside the worker dependency graph.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from celery import shared_task

from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.services.aggregation_execution import (
    DEFAULT_MAX_AGGREGATION_ATTEMPTS,
    AggregationExecutor,
    TransientAggregationError,
)
from gendertagger.services.dispatch import jittered_exponential_retry_delay
from gendertagger.tasks.worker_resources import get_worker_resources

EXECUTE_AGGREGATION_TASK_NAME = "gendertagger.tasks.execute_aggregation"


def _aggregation_executor() -> AggregationExecutor:
    """Compose aggregation with the process owner's fresh-session factory."""
    resources = get_worker_resources()
    return AggregationExecutor(
        unit_of_work_factory=resources.create_unit_of_work,
        clock=partial(datetime.now, UTC),
    )


# Celery's shared_task is untyped; the task body below is fully annotated.
@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name=EXECUTE_AGGREGATION_TASK_NAME,
    max_retries=DEFAULT_MAX_AGGREGATION_ATTEMPTS - 1,
)
def execute_aggregation(self: Any, *, aggregation_execution_id: str) -> None:
    """Execute one persisted aggregation and retry transient failures."""
    message = AggregationTaskMessage(
        aggregation_execution_id=aggregation_execution_id,  # type: ignore[arg-type]
    )
    try:
        _aggregation_executor().execute(
            message,
            attempt_count=self.request.retries + 1,
            max_attempts=DEFAULT_MAX_AGGREGATION_ATTEMPTS,
        )
    except TransientAggregationError as error:
        countdown = jittered_exponential_retry_delay(
            self.request.retries + 1,
            base=timedelta(seconds=2),
            maximum=timedelta(seconds=60),
        ).total_seconds()
        raise self.retry(exc=error, countdown=countdown) from error
