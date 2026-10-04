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
    seed_completed_aggregation,
    seed_completed_run,
    seed_project,
    seed_ready_snapshot,
)

from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.export import ExportCreateRequest, ExportFormat
from gendertagger.models.lifecycle import ExportExecutionStatus
from gendertagger.services.dispatch import OutboxRelay
from gendertagger.services.exports import ExportService
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage
from gendertagger.tasks.celery_app import create_celery_app
from gendertagger.tasks.dispatch import CeleryMessagePublisher
from gendertagger.tasks.worker_resources import reset_worker_resources

pytestmark = [pytest.mark.integration, pytest.mark.redis, pytest.mark.e2e]

_TERMINAL = {
    ExportExecutionStatus.completed,
    ExportExecutionStatus.failed,
}


def _seed_completed_reference_run_and_aggregation(
    factory: UnitOfWorkFactory,
) -> tuple[UUID, UUID]:
    now = datetime.now(UTC)
    with factory() as unit_of_work:
        project = seed_project(unit_of_work, slug_prefix="export-redis")
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
            only_method_answers("gnd", CanonicalLabel.male),
            at=now,
        )
        aggregation = seed_completed_aggregation(
            unit_of_work, completed.run.id, completed.execution_ids, at=now
        )
        unit_of_work.commit()
    return completed.run.id, aggregation.id


def test_json_export_runs_through_relay_and_real_worker(
    repository_database_url: str,
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from celery.contrib.testing.worker import start_worker

    monkeypatch.setenv("GENDERTAGGER_DATABASE_URL", repository_database_url)
    monkeypatch.setenv("GENDERTAGGER_ARTIFACT_ROOT", str(tmp_path))
    reset_worker_resources()
    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    run_id, aggregation_id = _seed_completed_reference_run_and_aggregation(factory)
    export = ExportService(
        unit_of_work_factory=factory,
        artifact_storage=LocalArtifactStorage(tmp_path),
        cursor_codec=CursorCodec(),
        clock=partial(datetime.now, UTC),
    ).create_export(
        ExportCreateRequest(
            run_id=run_id,
            aggregation_execution_id=aggregation_id,
            format=ExportFormat.json,
        )
    )
    assert export.status is ExportExecutionStatus.queued

    app = create_celery_app()
    relay = OutboxRelay(
        unit_of_work_factory=factory,
        publisher=CeleryMessagePublisher(app),
        relay_id="export-redis-e2e-relay",
        clock=partial(datetime.now, UTC),
    )
    terminal_status: ExportExecutionStatus | None = None
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
                    current = unit_of_work.exports.get_export(export.id)
                assert current is not None
                terminal_status = current.status
                if terminal_status in _TERMINAL:
                    break
                time.sleep(0.25)

        assert terminal_status is ExportExecutionStatus.completed
        with factory() as unit_of_work:
            completed = unit_of_work.exports.get_export(export.id)
            dispatch = unit_of_work.dispatches.get_dispatch_for_export(export.id)
        assert completed is not None
        assert completed.manifest_artifact_id is not None
        assert dispatch is not None
    finally:
        app.close()
        reset_worker_resources()
