"""Celery application factory and Redis broker configuration.

This module is the worker composition seam. It never imports the FastAPI layer:
the API enqueues work by importing this factory, not the other way around.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from celery import Celery
from kombu import Queue
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from gendertagger.models.queues import CLASSIFICATION_QUEUES, DEFAULT_QUEUE

_REDIS_SCHEMES = frozenset({"redis", "rediss"})


class CelerySettings(BaseSettings):
    """Validated broker settings loaded from ``GENDERTAGGER_*`` variables."""

    model_config = SettingsConfigDict(
        env_prefix="GENDERTAGGER_",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    celery_broker_url: SecretStr = SecretStr("redis://localhost:6379/0")
    celery_result_backend: SecretStr | None = None

    @field_validator("celery_broker_url", "celery_result_backend")
    @classmethod
    def _validate_redis_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        scheme = urlsplit(value.get_secret_value()).scheme
        if scheme not in _REDIS_SCHEMES:
            msg = "Celery broker and result backend must use a redis:// or rediss:// URL"
            raise ValueError(msg)
        return value


def create_celery_app(settings: CelerySettings | None = None) -> Celery:
    """Build a Celery app with durable-friendly, JSON-only broker defaults.

    Scientific results are authoritative in PostgreSQL, so the Celery result
    backend stays disabled unless one is explicitly configured. Tasks are
    acknowledged late and workers prefetch one message at a time so a crash
    re-delivers at-most one in-flight batch to an idempotent task.
    """
    resolved = settings or CelerySettings()
    backend = resolved.celery_result_backend
    app = Celery(
        "gendertagger",
        broker=resolved.celery_broker_url.get_secret_value(),
        backend=backend.get_secret_value() if backend is not None else None,
        # Imported lazily on worker finalize, so API clients that only send by
        # name never pull the execution module's heavy imports.
        include=["gendertagger.tasks.execution"],
    )
    configuration: dict[str, Any] = {
        # JSON only: never deserialize pickled payloads from the broker.
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "enable_utc": True,
        "timezone": "UTC",
        # At-least-once delivery paired with idempotent, bounded batch tasks.
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        "worker_prefetch_multiplier": 1,
        "task_track_started": True,
        "task_default_queue": DEFAULT_QUEUE,
        "task_queues": tuple(Queue(name) for name in CLASSIFICATION_QUEUES),
        "task_ignore_result": backend is None,
        "broker_connection_retry_on_startup": True,
    }
    app.conf.update(configuration)
    return app


app = create_celery_app()
"""Module-level app for the ``celery -A gendertagger.tasks.celery_app`` worker CLI."""
