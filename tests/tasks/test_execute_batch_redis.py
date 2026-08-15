from __future__ import annotations

import time
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from functools import partial
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.lifecycle import RunStatus, TaskBatchStatus
from gendertagger.models.person import ImportedPerson, PersonInput
from gendertagger.models.project import (
    DatasetSnapshotCreate,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotSourceMemberCreate,
)
from gendertagger.models.run import RunCreate
from gendertagger.services.dispatch import OutboxRelay
from gendertagger.services.execution import RunScheduler
from gendertagger.services.method_registry import default_method_registry
from gendertagger.services.unit_of_work import UnitOfWorkFactory
from gendertagger.tasks import execution as execution_module
from gendertagger.tasks.celery_app import create_celery_app
from gendertagger.tasks.dispatch import CeleryMessagePublisher

pytestmark = [pytest.mark.integration, pytest.mark.redis, pytest.mark.e2e]

_TERMINAL = {RunStatus.completed, RunStatus.completed_with_errors, RunStatus.failed}


def _seed_created_run(factory: UnitOfWorkFactory) -> UUID:
    with factory() as unit_of_work:
        project = unit_of_work.projects.add_project(
            ProjectCreate(slug=f"redis-{uuid4().hex}", display_name="Redis e2e project")
        )
        source = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type="source_tei",
                storage_uri="file:///synthetic/source.xml",
                sha256="a" * 64,
                byte_size=1,
                media_type="application/xml",
                project_id=project.id,
            )
        )
        import_config = SnapshotImportConfig(limits=SnapshotImportLimits())
        snapshot = unit_of_work.projects.add_snapshot(
            DatasetSnapshotCreate(
                project_id=project.id,
                source_artifact_id=source.id,
                source_sha256=source.sha256,
                parser_version=version_for_snapshot_import(import_config),
                import_config=import_config.model_dump(mode="json"),
            )
        )
        unit_of_work.projects.add_snapshot_source_members(
            snapshot.id,
            [
                SnapshotSourceMemberCreate(
                    artifact_id=source.id,
                    ordinal=0,
                    logical_name="source.xml",
                    sha256=source.sha256,
                    byte_size=source.byte_size,
                    media_type=source.media_type,
                )
            ],
        )
        unit_of_work.projects.begin_snapshot_import(snapshot.id)
        unit_of_work.projects.add_imported_person_records(
            snapshot.id,
            [
                ImportedPerson(
                    person=PersonInput(tei_id="p01", surname="Frölich (Frau des Heinrich)"),
                    source_member_name="source.xml",
                    source_record_locator="1",
                ),
                ImportedPerson(
                    person=PersonInput(tei_id="p02", surname="Schleiermacher"),
                    source_member_name="source.xml",
                    source_record_locator="2",
                ),
            ],
        )
        unit_of_work.projects.complete_snapshot_import(snapshot.id, ready_at=datetime.now(UTC))
        run = unit_of_work.runs.add_run(
            RunCreate(
                dataset_snapshot_id=snapshot.id,
                resolved_config=RunConfig(
                    methods=[MethodRunConfig(name="parenthetical_qualifier")]
                ),
                code_git_commit="abc123",
                application_version="0.0.0",
                python_version="3.11.0",
                dependency_lock_sha256="b" * 64,
            )
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
    execution_module._batch_executor.cache_clear()

    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork, create_session_factory(postgres_engine)
    )
    run_id = _seed_created_run(factory)
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
        assert batch is not None
        assert batch.status is TaskBatchStatus.completed
        assert batch.success_count == 1  # Frölich (Frau des ...) -> female
        assert batch.abstain_count == 1  # Schleiermacher -> no qualifier
        assert batch.worker_task_id is not None
    finally:
        app.close()
        execution_module._batch_executor.cache_clear()
