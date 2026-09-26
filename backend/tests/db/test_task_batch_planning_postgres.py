from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from tests.factories import tei_person_input
from tests.seeding import legacy_snapshot_statistics, seed_project, session_repositories

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.db.repositories.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.repositories.run_repository import SqlAlchemyRunRepository
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import ImportedPerson
from gendertagger.models.project import (
    DatasetSnapshotCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotSourceMemberCreate,
    TeiImportProfile,
)
from gendertagger.models.run import MethodExecution, MethodExecutionCreate, RunCreate
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.task_batches import plan_task_batches

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _ready_execution(
    db_session: Session, *, record_count: int
) -> tuple[SqlAlchemyRunRepository, MethodExecution]:
    now = datetime.now(UTC)
    repositories = session_repositories(db_session)
    projects = repositories.projects
    project = seed_project(
        repositories,
        slug_prefix="batch",
        display_name="Batch planning project",
    )
    artifacts = SqlAlchemyArtifactRepository(db_session)
    source = artifacts.add_artifact(
        ArtifactCreate(
            logical_type="source_tei",
            storage_uri="file:///synthetic/source.xml",
            sha256="a" * 64,
            byte_size=1,
            media_type="application/xml",
            project_id=project.id,
        )
    )
    import_config = SnapshotImportConfig(
        profile=TeiImportProfile.tei_p5_person_register,
        limits=SnapshotImportLimits(),
    )
    snapshot = projects.add_snapshot(
        DatasetSnapshotCreate(
            project_id=project.id,
            source_artifact_id=source.id,
            source_sha256=source.sha256,
            parser_version=version_for_snapshot_import(import_config),
            import_config=import_config.model_dump(mode="json"),
        )
    )
    projects.add_snapshot_source_members(
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
    assert projects.claim_snapshot_import(snapshot.id) is not None
    projects.add_imported_person_records(
        snapshot.id,
        [
            ImportedPerson(
                person=tei_person_input(tei_id=f"p{index:04d}"),
                source_member_name="source.xml",
                source_record_locator=str(index),
            )
            for index in range(record_count)
        ],
    )
    projects.complete_snapshot_import(
        snapshot.id,
        statistics=legacy_snapshot_statistics(
            snapshot.id,
            [tei_person_input(tei_id=f"p{index:04d}") for index in range(record_count)],
        ),
        ready_at=now,
    )

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
