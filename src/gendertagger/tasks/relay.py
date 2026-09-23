"""Process entry point for reliable outbox relay and dispatch reconciliation."""

from __future__ import annotations

import logging
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from threading import Event
from types import FrameType
from typing import Self
from uuid import uuid4

from celery import Celery
from pydantic import Field, SecretStr, field_validator, model_validator
from sqlalchemy import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.services.dispatch import (
    DispatchReconciler,
    OutboxRelay,
    jittered_exponential_retry_delay,
)
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.tasks.celery_app import CelerySettings, create_celery_app
from gendertagger.tasks.dispatch import CeleryMessagePublisher

logger = logging.getLogger(__name__)

MonotonicClock = Callable[[], float]


class DispatchCoordinatorSettings(CelerySettings):
    """Validated database, broker, and coordinator-loop settings."""

    database_url: SecretStr
    dispatch_poll_interval_seconds: float = Field(default=0.5, gt=0)
    dispatch_reconciliation_interval_seconds: float = Field(default=60.0, gt=0)
    dispatch_lease_seconds: float = Field(default=30.0, gt=0)
    dispatch_published_stale_seconds: float = Field(default=600.0, gt=0)
    dispatch_retry_base_seconds: float = Field(default=1.0, gt=0)
    dispatch_retry_max_seconds: float = Field(default=60.0, gt=0)
    dispatch_batch_size: int = Field(default=100, ge=1, le=10_000)
    dispatch_reconciliation_batch_size: int = Field(default=100, ge=1, le=10_000)

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

    @model_validator(mode="after")
    def _validate_retry_window(self) -> Self:
        if self.dispatch_retry_max_seconds < self.dispatch_retry_base_seconds:
            msg = "dispatch_retry_max_seconds must not be less than the base delay"
            raise ValueError(msg)
        return self


class DispatchCoordinator:
    """Run frequent relay cycles and slower reconciliation cycles."""

    def __init__(
        self,
        *,
        relay: OutboxRelay,
        reconciler: DispatchReconciler,
        stop_event: Event,
        poll_interval_seconds: float,
        reconciliation_interval_seconds: float,
        relay_batch_size: int,
        reconciliation_batch_size: int,
        monotonic: MonotonicClock = time.monotonic,
    ) -> None:
        if poll_interval_seconds <= 0 or reconciliation_interval_seconds <= 0:
            msg = "coordinator intervals must be positive"
            raise ValueError(msg)
        if relay_batch_size < 1 or reconciliation_batch_size < 1:
            msg = "coordinator batch sizes must be positive"
            raise ValueError(msg)
        self._relay = relay
        self._reconciler = reconciler
        self._stop_event = stop_event
        self._poll_interval_seconds = poll_interval_seconds
        self._reconciliation_interval_seconds = reconciliation_interval_seconds
        self._relay_batch_size = relay_batch_size
        self._reconciliation_batch_size = reconciliation_batch_size
        self._monotonic = monotonic

    def run(self) -> None:
        """Relay until signalled, reconciling immediately and then periodically."""
        next_reconciliation = self._monotonic()
        while not self._stop_event.is_set():
            relay_result = self._relay.run_once(limit=self._relay_batch_size)
            if relay_result.failed:
                logger.warning(
                    "dispatch relay cycle deferred %d of %d claimed messages",
                    relay_result.failed,
                    relay_result.claimed,
                )
            if relay_result.lease_conflicts:
                logger.warning(
                    "dispatch relay lost %d leases while recording outcomes",
                    relay_result.lease_conflicts,
                )

            now = self._monotonic()
            if now >= next_reconciliation:
                result = self._reconciler.run_once(limit=self._reconciliation_batch_size)
                if result.missing_created or result.stale_rearmed:
                    logger.info(
                        "dispatch reconciliation created %d missing and rearmed %d stale rows",
                        result.missing_created,
                        result.stale_rearmed,
                    )
                next_reconciliation = now + self._reconciliation_interval_seconds

            if relay_result.claimed < self._relay_batch_size:
                self._stop_event.wait(self._poll_interval_seconds)


@dataclass(frozen=True, slots=True)
class DispatchCoordinatorApplication:
    """Owned coordinator resources composed for one long-running process."""

    coordinator: DispatchCoordinator
    engine: Engine
    celery_app: Celery

    def close(self) -> None:
        """Release broker and database connection pools."""
        self.celery_app.close()
        self.engine.dispose()


def compose_dispatch_coordinator(
    settings: DispatchCoordinatorSettings,
    *,
    stop_event: Event,
) -> DispatchCoordinatorApplication:
    """Compose the coordinator from validated environment-backed settings."""
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    celery_app = create_celery_app(settings)
    clock = partial(datetime.now, UTC)
    relay = OutboxRelay(
        unit_of_work_factory=unit_of_work_factory,
        publisher=CeleryMessagePublisher(celery_app),
        relay_id=f"dispatch-coordinator-{uuid4().hex}",
        clock=clock,
        lease_duration=timedelta(seconds=settings.dispatch_lease_seconds),
        retry_delay=partial(
            jittered_exponential_retry_delay,
            base=timedelta(seconds=settings.dispatch_retry_base_seconds),
            maximum=timedelta(seconds=settings.dispatch_retry_max_seconds),
        ),
    )
    reconciler = DispatchReconciler(
        unit_of_work_factory=unit_of_work_factory,
        clock=clock,
        published_stale_after=timedelta(seconds=settings.dispatch_published_stale_seconds),
    )
    coordinator = DispatchCoordinator(
        relay=relay,
        reconciler=reconciler,
        stop_event=stop_event,
        poll_interval_seconds=settings.dispatch_poll_interval_seconds,
        reconciliation_interval_seconds=settings.dispatch_reconciliation_interval_seconds,
        relay_batch_size=settings.dispatch_batch_size,
        reconciliation_batch_size=settings.dispatch_reconciliation_batch_size,
    )
    return DispatchCoordinatorApplication(
        coordinator=coordinator,
        engine=engine,
        celery_app=celery_app,
    )


def _install_shutdown_handlers(stop_event: Event) -> None:
    def request_shutdown(signal_number: int, _frame: FrameType | None) -> None:
        logger.info(
            "received %s; stopping dispatch coordinator", signal.Signals(signal_number).name
        )
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def main() -> None:
    """Run the signal-aware dispatch coordinator process."""
    logging.basicConfig(level=logging.INFO)
    settings = DispatchCoordinatorSettings()  # type: ignore[call-arg]
    stop_event = Event()
    _install_shutdown_handlers(stop_event)
    application = compose_dispatch_coordinator(settings, stop_event=stop_event)
    logger.info("dispatch coordinator started")
    try:
        application.coordinator.run()
    finally:
        application.close()
        logger.info("dispatch coordinator stopped")


if __name__ == "__main__":
    main()
