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
    SEED_CODE_GIT_COMMIT,
    SEED_DEPENDENCY_LOCK_SHA256,
    seed_project,
    seed_ready_snapshot,
    seed_run,
)

from gendertagger.config.run import MethodRunConfig
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.lifecycle import RunStatus, TaskBatchStatus
from gendertagger.models.run import WorkerProvenance
from gendertagger.services.dispatch import OutboxRelay
from gendertagger.services.execution import RunScheduler
from gendertagger.services.method_registry import default_method_registry
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.runtime_provenance import capture_worker_provenance
from gendertagger.tasks import execution as execution_module
from gendertagger.tasks.celery_app import create_celery_app
from gendertagger.tasks.dispatch import CeleryMessagePublisher

pytestmark = [pytest.mark.integration, pytest.mark.redis, pytest.mark.e2e]

_TERMINAL = {RunStatus.completed, RunStatus.completed_with_errors, RunStatus.failed}


def _seed_created_run(factory: UnitOfWorkFactory, provenance: WorkerProvenance) -> UUID:
    with factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="redis")
        snapshot = seed_ready_snapshot(
            unit_of_work,
            project.id,
            [
                tei_person_input(tei_id="p01", surname="Frölich (Frau des Heinrich)"),
                tei_person_input(tei_id="p02", surname="Schleiermacher"),
            ],
            ready_at=datetime.now(UTC),
        )
        run = seed_run(
            unit_of_work,
            snapshot.id,
            [MethodRunConfig(name="parenthetical_qualifier")],
            worker_provenance=provenance,
        )
        unit_of_work.commit()
        return run.id


def test_cheap_method_runs_asynchronously_end_to_end(
    repository_database_url: str,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from celery.contrib.testing.worker import start_worker

    # The in-process worker builds its own engine from settings; point it at the
    # migrated temporary database this test writes to.
    monkeypatch.setenv("GENDERTAGGER_DATABASE_URL", repository_database_url)
    monkeypatch.setenv("GENDERTAGGER_CODE_GIT_COMMIT", SEED_CODE_GIT_COMMIT)
    monkeypatch.setenv("GENDERTAGGER_DEPENDENCY_LOCK_SHA256", SEED_DEPENDENCY_LOCK_SHA256)
    monkeypatch.delenv("GENDERTAGGER_CONTAINER_IMAGE_DIGEST", raising=False)
    provenance = capture_worker_provenance(
        code_git_commit=SEED_CODE_GIT_COMMIT,
        dependency_lock_sha256=SEED_DEPENDENCY_LOCK_SHA256,
    )
    execution_module._batch_executor.cache_clear()

    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork, create_session_factory(postgres_engine)
    )
    run_id = _seed_created_run(factory, provenance)
    scheduler = RunScheduler(
        unit_of_work_factory=factory,
        method_registry=default_method_registry(),
        clock=partial(datetime.now, UTC),
    )
    scheduled = scheduler.schedule_run(run_id)
    assert len(scheduled) == 1

    app = create_celery_app()
    relay = OutboxRelay(
        unit_of_work_factory=factory,
        publisher=CeleryMessagePublisher(app),
        relay_id="redis-e2e-relay",
        clock=partial(datetime.now, UTC),
    )
    status: RunStatus | None = None
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
                    run = unit_of_work.runs.get_run(run_id)
                assert run is not None
                status = run.status
                if status in _TERMINAL:
                    break
                time.sleep(0.25)

        assert status is RunStatus.completed
        with factory() as unit_of_work:
            batch = unit_of_work.runs.get_task_batch(scheduled[0].task_batch_id)
            persisted_run = unit_of_work.runs.get_run(run_id)
        assert batch is not None
        assert batch.status is TaskBatchStatus.completed
        assert batch.success_count == 1  # Frölich (Frau des ...) -> female
        assert batch.abstain_count == 1  # Schleiermacher -> no qualifier
        assert batch.worker_task_id is not None
        assert batch.worker_provenance == provenance
        assert persisted_run is not None
        assert persisted_run.dependency_versions == provenance.dependency_versions
    finally:
        app.close()
        execution_module._batch_executor.cache_clear()
