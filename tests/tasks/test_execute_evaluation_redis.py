from __future__ import annotations

import time
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
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
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.evaluation import EvaluationCreateRequest, EvaluationDefinition
from gendertagger.models.lifecycle import EvaluationExecutionStatus
from gendertagger.services.dispatch import OutboxRelay
from gendertagger.services.evaluations import EvaluationService
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage
from gendertagger.tasks import evaluation as evaluation_module
from gendertagger.tasks.celery_app import create_celery_app
from gendertagger.tasks.dispatch import CeleryMessagePublisher

pytestmark = [pytest.mark.integration, pytest.mark.redis, pytest.mark.e2e]

_TERMINAL = {
    EvaluationExecutionStatus.completed,
    EvaluationExecutionStatus.failed,
}
_DEFINITION = EvaluationDefinition()


def _seed_completed_reference_run(
    factory: UnitOfWorkFactory,
) -> tuple[UUID, tuple[UUID, ...]]:
    now = datetime.now(UTC)
    with factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="evaluation-redis")
        snapshot = seed_ready_snapshot(
            unit_of_work,
            project.id,
            [tei_person_input(tei_id="p01", surname="Example")],
            ready_at=now,
        )
        completed = seed_completed_run(
            unit_of_work,
            snapshot,
            _DEFINITION.required_methods,
            only_method_answers("gnd", CanonicalLabel.male),
            at=now,
        )
        unit_of_work.commit()
    return completed.run.id, completed.execution_ids


def test_gnd_benchmark_evaluation_runs_through_relay_and_real_worker(
    repository_database_url: str,
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from celery.contrib.testing.worker import start_worker

    monkeypatch.setenv("GENDERTAGGER_DATABASE_URL", repository_database_url)
    monkeypatch.setenv("GENDERTAGGER_ARTIFACT_ROOT", str(tmp_path))
    evaluation_module._evaluation_executor.cache_clear()
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    run_id, execution_ids = _seed_completed_reference_run(factory)
    evaluation = EvaluationService(
        unit_of_work_factory=factory,
        artifact_storage=LocalArtifactStorage(tmp_path),
        cursor_codec=CursorCodec(),
        clock=partial(datetime.now, UTC),
    ).create_evaluation(EvaluationCreateRequest(run_id=run_id, method_execution_ids=execution_ids))
    assert evaluation.status is EvaluationExecutionStatus.queued

    app = create_celery_app()
    relay = OutboxRelay(
        unit_of_work_factory=factory,
        publisher=CeleryMessagePublisher(app),
        relay_id="evaluation-redis-e2e-relay",
        clock=partial(datetime.now, UTC),
    )
    terminal_status: EvaluationExecutionStatus | None = None
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
                    current = unit_of_work.evaluations.get_evaluation(evaluation.id)
                assert current is not None
                terminal_status = current.status
                if terminal_status in _TERMINAL:
                    break
                time.sleep(0.25)

        assert terminal_status is EvaluationExecutionStatus.completed
        with factory() as unit_of_work:
            completed = unit_of_work.evaluations.get_evaluation(evaluation.id)
            dispatch = unit_of_work.dispatches.get_dispatch_for_evaluation(evaluation.id)
        assert completed is not None
        assert completed.report_artifact_id is not None
        assert dispatch is not None
    finally:
        app.close()
        evaluation_module._evaluation_executor.cache_clear()
