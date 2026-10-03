from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from tests.seeding import (
    SEED_TIME,
    always_abstain,
    seed_completed_aggregation,
    seed_completed_run,
    seed_pending_snapshot,
    seed_project,
    seed_ready_snapshot,
    seed_run,
    session_repositories,
)

from gendertagger.config.run import MethodRunConfig
from gendertagger.db.repositories.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.rows.projects import DatasetSnapshotRow
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import AggregationExecutionCreate
from gendertagger.models.lifecycle import (
    AggregationExecutionStatus,
    DatasetSnapshotStatus,
    RunStatus,
)
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.project import DatasetSnapshotListFilter, ProjectDataAvailability
from gendertagger.models.run import MethodExecutionCreate, RunListFilter
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


@pytest.mark.postgres_rollback
def test_data_availability_distinguishes_absent_and_empty_projects(db_session: Session) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories)

    assert repositories.projects.get_data_availability(uuid4()) is None
    assert repositories.projects.get_data_availability(project.id) == ProjectDataAvailability(
        project_id=project.id,
        has_ready_snapshots=False,
        has_completed_aggregations=False,
    )


@pytest.mark.postgres_rollback
def test_data_availability_requires_ready_imports_and_is_project_scoped(
    db_session: Session,
) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories)
    foreign_project = seed_project(repositories)
    foreign_snapshot = seed_ready_snapshot(repositories, foreign_project.id, [])
    foreign_run = seed_completed_run(
        repositories, foreign_snapshot, REFERENCE_REQUIRED_METHODS, always_abstain
    )
    seed_completed_aggregation(repositories, foreign_run.run.id, foreign_run.execution_ids)
    snapshot = seed_pending_snapshot(repositories, project.id)

    for transition in ("pending", "importing", "failed"):
        if transition == "importing":
            repositories.projects.claim_snapshot_import(snapshot.id)
        elif transition == "failed":
            repositories.projects.fail_snapshot_import(
                snapshot.id, failure_diagnostic="Invalid source"
            )
        availability = repositories.projects.get_data_availability(project.id)
        assert availability is not None
        assert not availability.has_ready_snapshots
        assert not availability.has_completed_aggregations

    ready_snapshot = seed_ready_snapshot(repositories, project.id, [])
    pending_snapshot = seed_pending_snapshot(repositories, project.id)
    pending_snapshot_row = db_session.get(DatasetSnapshotRow, pending_snapshot.id)
    assert pending_snapshot_row is not None
    # PostgreSQL now() is fixed for this test's outer transaction; pin a later creation time.
    pending_snapshot_row.created_at = ready_snapshot.created_at + timedelta(seconds=1)
    db_session.flush()
    first_snapshot_page = repositories.projects.list_snapshots(project.id, limit=1)
    assert first_snapshot_page[0].status is DatasetSnapshotStatus.pending
    availability = repositories.projects.get_data_availability(project.id)
    assert availability is not None
    assert availability.has_ready_snapshots
    assert not availability.has_completed_aggregations


@pytest.mark.postgres_rollback
def test_data_availability_requires_completed_aggregation_without_a_working_pointer(
    db_session: Session,
) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories)
    snapshot = seed_ready_snapshot(repositories, project.id, [])
    run = seed_completed_run(repositories, snapshot, REFERENCE_REQUIRED_METHODS, always_abstain)
    aggregation = repositories.aggregations.add_aggregation(
        AggregationExecutionCreate(run_id=run.run.id, method_execution_ids=run.execution_ids)
    )

    for transition in ("pending", "queued", "running", "failed"):
        if transition == "queued":
            repositories.aggregations.mark_aggregation_queued(aggregation.id)
        elif transition == "running":
            repositories.aggregations.claim_aggregation(aggregation.id, started_at=SEED_TIME)
        elif transition == "failed":
            repositories.aggregations.mark_aggregation_finished(
                aggregation.id,
                status=AggregationExecutionStatus.failed,
                finished_at=SEED_TIME,
                failure_diagnostic="Aggregation failure",
            )
        availability = repositories.projects.get_data_availability(project.id)
        assert availability is not None
        assert not availability.has_completed_aggregations

    seed_completed_aggregation(repositories, run.run.id, run.execution_ids)
    repositories.aggregations.add_aggregation(
        AggregationExecutionCreate(run_id=run.run.id, method_execution_ids=run.execution_ids)
    )
    availability = repositories.projects.get_data_availability(project.id)
    assert availability is not None
    assert availability.has_completed_aggregations

    assert [
        item.id
        for item in repositories.projects.list_snapshots(
            project.id,
            limit=1,
            filters=DatasetSnapshotListFilter(has_completed_aggregations=True),
        )
    ] == [snapshot.id]
    assert [
        item.id
        for item in repositories.runs.list_runs(
            snapshot.id, limit=1, filters=RunListFilter(has_completed_aggregations=True)
        )
    ] == [run.run.id]
    unchanged_project = repositories.projects.get_project(project.id)
    assert unchanged_project is not None
    assert unchanged_project.working_aggregation_execution_id is None


@pytest.mark.parametrize("run_status", [RunStatus.running, RunStatus.failed])
@pytest.mark.postgres_rollback
def test_data_availability_does_not_require_the_run_to_be_completed(
    db_session: Session,
    run_status: RunStatus,
) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories)
    snapshot = seed_ready_snapshot(repositories, project.id, [])
    run = seed_run(
        repositories,
        snapshot.id,
        [MethodRunConfig(name=name) for name in REFERENCE_REQUIRED_METHODS],
    )
    repositories.runs.mark_run_queued(run.id)
    repositories.runs.mark_run_started(run.id, started_at=SEED_TIME)
    execution_ids = []
    for method_name in REFERENCE_REQUIRED_METHODS:
        execution = repositories.runs.add_method_execution(
            MethodExecutionCreate(
                run_id=run.id,
                descriptor=MethodDescriptor(
                    name=method_name,
                    implementation_version="fixture_v1",
                    normalization_version="fixture_v1",
                ),
                queue_name="cpu",
                total_count=0,
            )
        )
        repositories.runs.mark_execution_queued(execution.id)
        repositories.runs.mark_execution_started(execution.id, started_at=SEED_TIME)
        repositories.runs.finalize_execution_if_complete(execution.id, finished_at=SEED_TIME)
        execution_ids.append(execution.id)
    if run_status is RunStatus.failed:
        repositories.runs.mark_run_finished(
            run.id,
            status=RunStatus.failed,
            finished_at=SEED_TIME,
            failure_diagnostic="Run failed after completed methods",
        )
    seed_completed_aggregation(repositories, run.id, execution_ids)

    availability = repositories.projects.get_data_availability(project.id)

    assert availability is not None
    assert availability.has_completed_aggregations
    assert [
        item.id
        for item in repositories.projects.list_snapshots(
            project.id,
            limit=1,
            filters=DatasetSnapshotListFilter(has_completed_aggregations=True),
        )
    ] == [snapshot.id]
    assert [
        item.id
        for item in repositories.runs.list_runs(
            snapshot.id, limit=1, filters=RunListFilter(has_completed_aggregations=True)
        )
    ] == [run.id]


@pytest.mark.postgres_rollback
def test_set_working_aggregation_rejects_an_unknown_project(db_session: Session) -> None:
    """The HTTP route's ``ProjectAccessGuard`` already hides an unknown project with 404 before
    the service is called, so this defensive repository branch is only reachable directly."""
    repository = SqlAlchemyProjectRepository(db_session)
    missing_project_id = uuid4()

    with pytest.raises(ResourceNotFoundError, match=str(missing_project_id)):
        repository.set_working_aggregation(missing_project_id, aggregation_execution_id=None)


@pytest.mark.postgres_rollback
def test_set_working_aggregation_rejects_an_unknown_aggregation(db_session: Session) -> None:
    repository = SqlAlchemyProjectRepository(db_session)
    project = seed_project(
        session_repositories(db_session),
        slug_prefix="working-agg",
        display_name="Working aggregation fixture",
    )
    missing_aggregation_id = uuid4()

    with pytest.raises(ResourceNotFoundError, match=str(missing_aggregation_id)):
        repository.set_working_aggregation(
            project.id,
            aggregation_execution_id=missing_aggregation_id,
        )
