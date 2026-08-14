"""Celery task binding for asynchronous classification-batch execution.

The task is a thin wrapper: it rebuilds the small envelope and delegates to the
application :class:`~gendertagger.services.execution.BatchExecutor`. It never
imports the FastAPI layer.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from functools import lru_cache, partial
from pathlib import Path
from typing import Any
from weakref import finalize

from celery import shared_task
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.run import TaskBatchMessage
from gendertagger.services.execution import (
    DEFAULT_MAX_BATCH_ATTEMPTS,
    BatchExecutor,
    TransientBatchError,
)
from gendertagger.services.lookup_assets import RegisteredLookupAssetResolver
from gendertagger.services.method_registry import default_method_registry
from gendertagger.services.unit_of_work import UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

EXECUTE_BATCH_TASK_NAME = "gendertagger.tasks.execute_batch"
_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 60.0


def _retry_countdown(retries: int) -> float:
    """Exponential backoff with full jitter, bounded to a maximum delay."""
    ceiling = min(_RETRY_BASE_SECONDS * (2**retries), _RETRY_MAX_SECONDS)
    return random.uniform(0.0, ceiling)  # noqa: S311 - retry jitter is not security-sensitive


class WorkerSettings(BaseSettings):
    """Validated worker settings loaded from ``GENDERTAGGER_*`` variables."""

    model_config = SettingsConfigDict(
        env_prefix="GENDERTAGGER_",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    artifact_root: Path = Path("data/artifacts")

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            database_url = make_url(value.get_secret_value())
        except ArgumentError as error:
            msg = "database_url must be a valid SQLAlchemy URL"
            raise ValueError(msg) from error
        if database_url.drivername != "postgresql+psycopg":
            msg = "database_url must use the postgresql+psycopg driver"
            raise ValueError(msg)
        return value


@lru_cache(maxsize=1)
def _batch_executor() -> BatchExecutor:
    """Build the process-wide batch executor from worker settings once."""
    settings = WorkerSettings()  # type: ignore[call-arg]  # Values come from settings sources.
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    lookup_resolver = RegisteredLookupAssetResolver(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(settings.artifact_root),
    )
    executor = BatchExecutor(
        unit_of_work_factory=unit_of_work_factory,
        method_registry=default_method_registry(lookup_resolver),
        clock=partial(datetime.now, UTC),
    )
    finalize(executor, engine.dispose)
    return executor


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
        raise self.retry(exc=error, countdown=_retry_countdown(self.request.retries)) from error
