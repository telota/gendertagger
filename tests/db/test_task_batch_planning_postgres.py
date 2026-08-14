from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.models.project import DatasetSnapshotCreate, ProjectCreate
from gendertagger.models.run import MethodExecution, MethodExecutionCreate, RunCreate
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.task_batches import plan_task_batches

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _ready_execution(
    db_session: Session, *, record_count: int
) -> tuple[SqlAlchemyRunRepository, MethodExecution]:
    now = datetime.now(UTC)
    artifacts = SqlAlchemyArtifactRepository(db_session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/source.xml",
            sha256="a" * 64,
            byte_size=1,
            media_type="application/xml",
        )
    )
    projects = SqlAlchemyProjectRepository(db_session)
    project = projects.add_project(
        ProjectCreate(slug=f"batch-{uuid4().hex}", display_name="Batch planning project")
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source.id,
            source_sha256=source.sha256,
            parser_version="tei_parser_v1",
            import_config={"profile": "tei_p5_person_register_v1"},
        )
    )
    projects.begin_snapshot_import(snapshot.id)
    projects.add_person_records(
        snapshot.id,
        [PersonInput(tei_id=f"p{index:04d}") for index in range(record_count)],
    )
    projects.complete_snapshot_import(snapshot.id, ready_at=now)

    runs = SqlAlchemyRunRepository(db_session)
    run = runs.add_run(
        RunCreate(
            dataset_snapshot_id=snapshot.id,
            resolved_config=RunConfig(methods=[MethodRunConfig(name="demo_method")]),
            code_git_commit="abc123",
            application_version="0.0.0",
            python_version="3.11.0",
            dependency_lock_sha256="b" * 64,
        )
    )
    execution = runs.add_method_execution(
        MethodExecutionCreate(
            run_id=run.id,
            descriptor=MethodDescriptor(
                name="demo_method",
                implementation_version="1.0.0",
                normalization_version="demo_v1",
            ),
            queue_name="cpu",
            total_count=record_count,
        )
    )
    return runs, execution


def test_planned_batches_persist_contiguous_slices(db_session: Session) -> None:
    runs, execution = _ready_execution(db_session, record_count=5)

    plans = plan_task_batches(5, batch_size=2)
    batches = runs.create_task_batches(execution.id, plans)

    assert [(b.batch_index, b.record_offset, b.record_count) for b in batches] == [
        (0, 0, 2),
        (1, 2, 2),
        (2, 4, 1),
    ]
    assert {batch.queue_name for batch in batches} == {"cpu"}


def test_replanning_is_idempotent(db_session: Session) -> None:
    runs, execution = _ready_execution(db_session, record_count=5)

    plans = plan_task_batches(5, batch_size=2)
    first = runs.create_task_batches(execution.id, plans)
    second = runs.create_task_batches(execution.id, plans)

    assert [batch.id for batch in first] == [batch.id for batch in second]


def test_empty_plan_persists_no_batches(db_session: Session) -> None:
    runs, execution = _ready_execution(db_session, record_count=0)

    assert runs.create_task_batches(execution.id, plan_task_batches(0, batch_size=2)) == []


def test_planning_unknown_execution_is_rejected(db_session: Session) -> None:
    runs, _ = _ready_execution(db_session, record_count=1)

    with pytest.raises(ResourceNotFoundError):
        runs.create_task_batches(uuid4(), plan_task_batches(1, batch_size=2))
