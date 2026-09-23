from __future__ import annotations

import time
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from gendertagger.db.session import create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.dispatch import DispatchStatus
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.project import ProjectCreate, SnapshotImportRequest
from gendertagger.models.user import UserCreate
from gendertagger.services.dispatch import OutboxRelay
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.projects import ProjectService
from gendertagger.storage.local import LocalArtifactStorage
from gendertagger.tasks import snapshot_import as snapshot_import_module
from gendertagger.tasks.celery_app import create_celery_app
from gendertagger.tasks.dispatch import CeleryMessagePublisher

pytestmark = [pytest.mark.integration, pytest.mark.redis, pytest.mark.e2e]

_TERMINAL = {DatasetSnapshotStatus.ready, DatasetSnapshotStatus.failed}
_VALID_TEI = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body><listPerson>
    <person xml:id="p2">
      <persName type="reg"><surname>Second</surname></persName>
    </person>
    <person xml:id="p1">
      <persName type="reg"><surname>Example</surname><forename>Anna</forename></persName>
      <idno type="uri">https://d-nb.info/gnd/123456789</idno>
    </person>
  </listPerson></body></text>
</TEI>
"""


def _creator_id(unit_of_work_factory: UnitOfWorkFactory) -> UUID:
    with unit_of_work_factory() as unit_of_work:
        creator = unit_of_work.users.add_user(UserCreate(display_name="Project creator"))
        unit_of_work.commit()
    return creator.id


def test_snapshot_import_runs_through_relay_and_real_worker(
    repository_database_url: str,
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from celery.contrib.testing.worker import start_worker

    # The worker builds its own database and storage adapters from settings.
    # Point both it and the acceptance service at the same durable resources.
    monkeypatch.setenv("GENDERTAGGER_DATABASE_URL", repository_database_url)
    monkeypatch.setenv("GENDERTAGGER_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("GENDERTAGGER_TEI_IMPORT_BATCH_RECORD_COUNT", "1")
    snapshot_import_module._snapshot_import_executor.cache_clear()

    factory: UnitOfWorkFactory = partial(
        SqlAlchemyUnitOfWork,
        create_session_factory(postgres_engine),
    )
    project_service = ProjectService(
        unit_of_work_factory=factory,
        artifact_storage=LocalArtifactStorage(tmp_path),
        parser=TeiPersonParser(),
        cursor_codec=CursorCodec(),
        clock=partial(datetime.now, UTC),
        max_upload_bytes=len(_VALID_TEI),
    )
    project = project_service.create_project(
        ProjectCreate(
            slug=f"snapshot-redis-{uuid4().hex}",
            display_name="Snapshot Redis e2e project",
        ),
        creator_user_id=_creator_id(factory),
    )
    snapshot = project_service.import_snapshot(
        project_id=project.id,
        source=BytesIO(_VALID_TEI),
        command=SnapshotImportRequest(),
    )
    assert snapshot.status is DatasetSnapshotStatus.pending

    app = create_celery_app()
    assert not app.conf.task_always_eager
    relay = OutboxRelay(
        unit_of_work_factory=factory,
        publisher=CeleryMessagePublisher(app),
        relay_id="snapshot-import-redis-e2e-relay",
        clock=partial(datetime.now, UTC),
    )
    terminal_status: DatasetSnapshotStatus | None = None
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
                    current = unit_of_work.projects.get_snapshot(snapshot.id)
                assert current is not None
                terminal_status = current.status
                if terminal_status in _TERMINAL:
                    break
                time.sleep(0.25)

        assert terminal_status is DatasetSnapshotStatus.ready
        with factory() as unit_of_work:
            completed = unit_of_work.projects.get_snapshot(snapshot.id)
            people = unit_of_work.projects.list_person_records(snapshot.id, limit=10)
            dispatch = unit_of_work.dispatches.get_dispatch_for_snapshot(snapshot.id)

        assert completed is not None
        assert completed.record_count == 2
        assert [person.tei_id for person in people] == ["p1", "p2"]
        assert people[0].surname == "Example"
        assert people[0].forenames == ["Anna"]
        assert people[0].gnd_id == "123456789"
        assert dispatch is not None
        assert dispatch.status is DispatchStatus.published
    finally:
        app.close()
        snapshot_import_module._snapshot_import_executor.cache_clear()
