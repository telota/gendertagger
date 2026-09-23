from __future__ import annotations

import time
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from functools import partial
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import Engine
from tests.factories import tei_person_input
from tests.seeding import (
    only_method_answers,
    seed_completed_run,
    seed_project,
    seed_ready_snapshot,
)

from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import AggregationCreateRequest
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.dispatch import OutboxRelay
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.unit_of_work import UnitOfWorkFactory
from gendertagger.tasks import aggregation as aggregation_module
from gendertagger.tasks.celery_app import create_celery_app
from gendertagger.tasks.dispatch import CeleryMessagePublisher

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.redis]

_TERMINAL = {
    AggregationExecutionStatus.completed,
    AggregationExecutionStatus.failed,
}


def _seed_completed_reference_run(
    factory: UnitOfWorkFactory,
    _postgres_engine: Engine,
) -> tuple[UUID, tuple[UUID, ...]]:
    now = datetime.now(UTC)
    with factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="aggregation-redis")
        snapshot = seed_ready_snapshot(
            unit_of_work,
            project.id,
            [tei_person_input(tei_id="p01", surname="Example")],
            ready_at=now,
        )
        completed = seed_completed_run(
            unit_of_work,
            snapshot,
            REFERENCE_REQUIRED_METHODS,
            only_method_answers("gender_guesser", CanonicalLabel.female),
            at=now,
        )
        unit_of_work.commit()
    return completed.run.id, completed.execution_ids


def test_reference_aggregation_runs_through_relay_and_real_worker(
    repository_database_url: str,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from celery.contrib.testing.worker import start_worker

    monkeypatch.setenv("GENDERTAGGER_DATABASE_URL", repository_database_url)
    aggregation_module._aggregation_executor.cache_clear()
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    run_id, execution_ids = _seed_completed_reference_run(factory, postgres_engine)
    aggregation = (
        AggregationService(
            unit_of_work_factory=factory,
            cursor_codec=CursorCodec(),
            clock=partial(datetime.now, UTC),
        )
        .create_aggregation(
            run_id=run_id,
            command=AggregationCreateRequest(method_execution_ids=execution_ids),
        )
        .aggregation
    )
    assert aggregation.status is AggregationExecutionStatus.queued

    app = create_celery_app()
    relay = OutboxRelay(
        unit_of_work_factory=factory,
        publisher=CeleryMessagePublisher(app),
        relay_id="aggregation-redis-e2e-relay",
        clock=partial(datetime.now, UTC),
    )
    terminal_status: AggregationExecutionStatus | None = None
    try:
        worker_context = cast(
            AbstractContextManager[object],
            start_worker(app, queues=["cpu"], perform_ping_check=False, shutdown_timeout=30),
        )
        with worker_context:
            relay_result = relay.run_once()
            assert relay_result.published == 1
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                with factory() as unit_of_work:
                    current = unit_of_work.aggregations.get_aggregation(aggregation.id)
                assert current is not None
                terminal_status = current.status
                if terminal_status in _TERMINAL:
                    break
                time.sleep(0.25)

        assert terminal_status is AggregationExecutionStatus.completed
        with factory() as unit_of_work:
            results = unit_of_work.aggregations.list_results(aggregation.id, limit=10)
            dispatch = unit_of_work.dispatches.get_dispatch_for_aggregation(aggregation.id)
        assert len(results) == 1
        assert results[0].label is CanonicalLabel.female
        assert dispatch is not None
    finally:
        app.close()
        aggregation_module._aggregation_executor.cache_clear()
