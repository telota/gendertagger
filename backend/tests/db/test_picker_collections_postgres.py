"""Picker collections select eligible resources before applying their keyset limit."""

from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session
from tests.seeding import (
    SEED_TIME,
    always_abstain,
    legacy_snapshot_statistics,
    seed_completed_aggregation,
    seed_completed_run,
    seed_pending_snapshot,
    seed_project,
    seed_ready_snapshot,
    session_repositories,
)

from gendertagger.db.rows.projects import DatasetSnapshotRow
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.aggregation import (
    AggregationExecutionCreate,
    AggregationExecutionListFilter,
)
from gendertagger.models.lifecycle import AggregationExecutionStatus, DatasetSnapshotStatus
from gendertagger.models.project import DatasetSnapshotListFilter
from gendertagger.models.run import RunListFilter
from gendertagger.services.pagination import CreationPosition

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def test_snapshots_page_by_import_acceptance_date_with_stable_uuid_ties(
    db_session: Session,
) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories)
    newest, tied_lower, tied_higher, oldest = sorted(
        (seed_pending_snapshot(repositories, project.id) for _ in range(4)),
        key=lambda item: item.id,
    )
    # Deliberately oppose UUID and completion order to import acceptance order.
    for snapshot, accepted_minutes, completed_minutes in (
        (newest, 3, 4),
        (tied_lower, 2, 6),
        (tied_higher, 2, 5),
        (oldest, 1, 7),
    ):
        db_session.execute(
            update(DatasetSnapshotRow)
            .where(DatasetSnapshotRow.id == snapshot.id)
            .values(created_at=SEED_TIME + timedelta(minutes=accepted_minutes))
        )
        repositories.projects.claim_snapshot_import(snapshot.id)
        repositories.projects.complete_snapshot_import(
            snapshot.id,
            statistics=legacy_snapshot_statistics(snapshot.id, []),
            ready_at=SEED_TIME + timedelta(minutes=completed_minutes),
        )
    db_session.flush()

    filters = DatasetSnapshotListFilter(status=DatasetSnapshotStatus.ready)
    first_page = repositories.projects.list_snapshots(project.id, limit=2, filters=filters)
    assert [item.id for item in first_page] == [newest.id, tied_higher.id]
    after = CreationPosition(created_at=first_page[-1].created_at, id=first_page[-1].id)
    second_page = repositories.projects.list_snapshots(
        project.id, limit=2, filters=filters, after=after
    )
    assert [item.id for item in second_page] == [tied_lower.id, oldest.id]
    after = CreationPosition(created_at=second_page[-1].created_at, id=second_page[-1].id)
    assert not repositories.projects.list_snapshots(
        project.id, limit=2, filters=filters, after=after
    )


def test_snapshot_filters_find_older_results_and_do_not_cross_project_boundaries(
    db_session: Session,
) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories)
    foreign = seed_project(repositories)
    foreign_snapshot = seed_ready_snapshot(repositories, foreign.id, [])
    foreign_run = seed_completed_run(
        repositories, foreign_snapshot, REFERENCE_REQUIRED_METHODS, always_abstain
    )
    seed_completed_aggregation(repositories, foreign_run.run.id, foreign_run.execution_ids)
    # now() is transaction-stable, so UUID order decides ties in the immutable seeds.
    ready, empty = sorted(
        (seed_ready_snapshot(repositories, project.id, []) for _ in range(2)),
        key=lambda item: item.id,
    )
    older_run = seed_completed_run(repositories, ready, REFERENCE_REQUIRED_METHODS, always_abstain)
    seed_completed_aggregation(repositories, older_run.run.id, older_run.execution_ids)
    pending = seed_pending_snapshot(repositories, project.id)
    db_session.execute(
        update(DatasetSnapshotRow)
        .where(DatasetSnapshotRow.id == pending.id)
        .values(created_at=ready.created_at + timedelta(minutes=1))
    )
    db_session.flush()

    assert repositories.projects.list_snapshots(project.id, limit=1)[0].id == pending.id
    ready_only = repositories.projects.list_snapshots(
        project.id, limit=1, filters=DatasetSnapshotListFilter(status=DatasetSnapshotStatus.ready)
    )
    assert ready_only[0].id == empty.id
    with_results = repositories.projects.list_snapshots(
        project.id,
        limit=1,
        filters=DatasetSnapshotListFilter(
            status=DatasetSnapshotStatus.ready, has_completed_aggregations=True
        ),
    )
    assert [item.id for item in with_results] == [ready.id]
    without_results = repositories.projects.list_snapshots(
        project.id,
        limit=10,
        filters=DatasetSnapshotListFilter(has_completed_aggregations=False),
    )
    assert [item.id for item in without_results] == [pending.id, empty.id]
    assert not repositories.projects.list_snapshots(
        project.id,
        limit=10,
        filters=DatasetSnapshotListFilter(
            status=DatasetSnapshotStatus.pending, has_completed_aggregations=True
        ),
    )


def test_run_and_aggregation_filters_page_eligible_results_under_their_owning_parent(
    db_session: Session,
) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories)
    snapshot = seed_ready_snapshot(repositories, project.id, [])
    foreign_snapshot = seed_ready_snapshot(repositories, project.id, [])
    foreign_run = seed_completed_run(
        repositories, foreign_snapshot, REFERENCE_REQUIRED_METHODS, always_abstain
    )
    seed_completed_aggregation(repositories, foreign_run.run.id, foreign_run.execution_ids)
    older, newer, empty = sorted(
        (
            seed_completed_run(repositories, snapshot, REFERENCE_REQUIRED_METHODS, always_abstain)
            for _ in range(3)
        ),
        key=lambda item: item.run.id,
    )
    seed_completed_aggregation(repositories, older.run.id, older.execution_ids)
    first_result, second_result, pending = sorted(
        (
            repositories.aggregations.add_aggregation(
                AggregationExecutionCreate(
                    run_id=newer.run.id, method_execution_ids=newer.execution_ids
                )
            )
            for _ in range(3)
        ),
        key=lambda item: item.id,
    )
    for aggregation in (first_result, second_result):
        repositories.aggregations.mark_aggregation_queued(aggregation.id)
        repositories.aggregations.claim_aggregation(aggregation.id, started_at=SEED_TIME)
        repositories.aggregations.mark_aggregation_finished(
            aggregation.id, status=AggregationExecutionStatus.completed, finished_at=SEED_TIME
        )
    db_session.flush()

    assert repositories.runs.list_runs(snapshot.id, limit=1)[0].id == empty.run.id
    run_filter = RunListFilter(has_completed_aggregations=True)
    first_run_page = repositories.runs.list_runs(snapshot.id, limit=1, filters=run_filter)
    assert [item.id for item in first_run_page] == [newer.run.id]
    after_run = CreationPosition(created_at=first_run_page[0].created_at, id=first_run_page[0].id)
    assert [
        item.id
        for item in repositories.runs.list_runs(
            snapshot.id, limit=1, filters=run_filter, after=after_run
        )
    ] == [older.run.id]
    assert [
        item.id
        for item in repositories.runs.list_runs(
            snapshot.id, limit=10, filters=RunListFilter(has_completed_aggregations=False)
        )
    ] == [empty.run.id]

    assert repositories.aggregations.list_aggregations(newer.run.id, limit=1)[0].id == pending.id
    result_filter = AggregationExecutionListFilter(status=AggregationExecutionStatus.completed)
    first_result_page = repositories.aggregations.list_aggregations(
        newer.run.id, limit=1, filters=result_filter
    )
    assert [item.id for item in first_result_page] == [second_result.id]
    after_result = CreationPosition(
        created_at=first_result_page[0].created_at, id=first_result_page[0].id
    )
    assert [
        item.id
        for item in repositories.aggregations.list_aggregations(
            newer.run.id, limit=1, filters=result_filter, after=after_result
        )
    ] == [first_result.id]
    assert [
        item.id
        for item in repositories.aggregations.list_aggregations(
            newer.run.id,
            limit=10,
            filters=AggregationExecutionListFilter(status=AggregationExecutionStatus.pending),
        )
    ] == [pending.id]


def test_project_review_results_page_completed_results_with_context(
    db_session: Session,
) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories)
    foreign = seed_project(repositories)
    snapshot = seed_ready_snapshot(repositories, project.id, [])
    older_run = seed_completed_run(
        repositories, snapshot, REFERENCE_REQUIRED_METHODS, always_abstain
    )
    older_result = seed_completed_aggregation(
        repositories, older_run.run.id, older_run.execution_ids
    )
    newer_run = seed_completed_run(
        repositories, snapshot, REFERENCE_REQUIRED_METHODS, always_abstain
    )
    newer_result = seed_completed_aggregation(
        repositories, newer_run.run.id, newer_run.execution_ids
    )
    runs_by_result = {
        older_result.id: older_run,
        newer_result.id: newer_run,
    }
    foreign_snapshot = seed_ready_snapshot(repositories, foreign.id, [])
    foreign_run = seed_completed_run(
        repositories, foreign_snapshot, REFERENCE_REQUIRED_METHODS, always_abstain
    )
    seed_completed_aggregation(repositories, foreign_run.run.id, foreign_run.execution_ids)
    ordered = sorted(
        (older_result, newer_result), key=lambda item: (item.created_at, item.id), reverse=True
    )

    first_page = repositories.projects.list_review_results(project.id, limit=1)

    assert [item.aggregation.id for item in first_page] == [ordered[0].id]
    expected_run = runs_by_result[ordered[0].id]
    assert first_page[0].run.id == expected_run.run.id
    assert first_page[0].snapshot.id == snapshot.id
    assert first_page[0].aggregation.method_execution_ids == expected_run.execution_ids
    after = CreationPosition(created_at=ordered[0].created_at, id=ordered[0].id)
    second_page = repositories.projects.list_review_results(project.id, limit=10, after=after)
    assert [item.aggregation.id for item in second_page] == [ordered[1].id]
