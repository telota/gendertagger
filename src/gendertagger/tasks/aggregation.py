"""Celery task binding for asynchronous reference aggregation execution.

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
from gendertagger.models.aggregation import AggregationTaskMessage
from gendertagger.services.aggregation_execution import (
    DEFAULT_MAX_AGGREGATION_ATTEMPTS,
    AggregationExecutor,
    TransientAggregationError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

EXECUTE_AGGREGATION_TASK_NAME = "gendertagger.tasks.execute_aggregation"
_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 60.0


def _retry_countdown(retries: int) -> float:
    """Return full-jitter exponential backoff for one aggregation retry."""
    ceiling = min(_RETRY_BASE_SECONDS * (2**retries), _RETRY_MAX_SECONDS)
    return random.uniform(0.0, ceiling)  # noqa: S311 - retry jitter is not security-sensitive


@lru_cache(maxsize=1)
def _aggregation_executor() -> AggregationExecutor:
    """Build the process-wide aggregation executor from worker settings once."""
    settings = RuntimeSettings()  # type: ignore[call-arg]  # Values come from settings sources.
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    executor = AggregationExecutor(
        unit_of_work_factory=unit_of_work_factory,
        clock=partial(datetime.now, UTC),
    )
    finalize(executor, engine.dispose)
    return executor


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
        raise self.retry(exc=error, countdown=_retry_countdown(self.request.retries)) from error
