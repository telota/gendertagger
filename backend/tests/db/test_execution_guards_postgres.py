"""Database guards on evaluation and export executions.

Each test bypasses the repositories with raw SQL, so a passing test proves that PostgreSQL itself
rejects the change, as it does for aggregation executions.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from tests.factories import tei_person_input
from tests.seeding import (
    only_method_answers,
    seed_completed_aggregation,
    seed_completed_run,
    seed_pending_snapshot,
    seed_project,
    seed_ready_snapshot,
    seed_run,
    session_repositories,
)

from gendertagger.config.run import MethodRunConfig
from gendertagger.db.repositories.evaluation_repository import SqlAlchemyEvaluationRepository
from gendertagger.db.repositories.export_repository import SqlAlchemyExportRepository
from gendertagger.domain.aggregation import REFERENCE_REQUIRED_METHODS
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.evaluation import EvaluationDefinition, EvaluationExecutionCreate
from gendertagger.models.export import ExportExecutionCreate, ExportFormat
from gendertagger.models.lifecycle import EvaluationExecutionStatus, ExportExecutionStatus

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
DEFINITION = EvaluationDefinition()
METHOD_NAMES = tuple(dict.fromkeys((*REFERENCE_REQUIRED_METHODS, *DEFINITION.required_methods)))


@dataclass(frozen=True, slots=True)
class _SeededRun:
    run_id: UUID
    execution_ids: dict[str, UUID]
    aggregation_id: UUID


def _seed(session: Session) -> _SeededRun:
    repositories = session_repositories(session)
    project = seed_project(repositories, slug_prefix="execution-guards")
    snapshot = seed_ready_snapshot(
        repositories, project.id, [tei_person_input(tei_id="p1", surname="Example")]
    )
    completed = seed_completed_run(
        repositories, snapshot, METHOD_NAMES, only_method_answers("gnd", CanonicalLabel.male)
    )
    execution_ids = dict(zip(METHOD_NAMES, completed.execution_ids, strict=True))
    aggregation = seed_completed_aggregation(
        repositories,
        completed.run.id,
        [execution_ids[name] for name in REFERENCE_REQUIRED_METHODS],
    )
    return _SeededRun(completed.run.id, execution_ids, aggregation.id)


def _evaluation(session: Session, seeded: _SeededRun) -> UUID:
    evaluation = SqlAlchemyEvaluationRepository(session).add_evaluation(
        EvaluationExecutionCreate(
            run_id=seeded.run_id,
            resolved_config=DEFINITION.model_dump(mode="json"),
            method_execution_ids=tuple(
                seeded.execution_ids[name] for name in DEFINITION.required_methods
            ),
        )
    )
    return evaluation.id


def _export(session: Session, seeded: _SeededRun) -> UUID:
    export = SqlAlchemyExportRepository(session).add_export(
        ExportExecutionCreate(
            run_id=seeded.run_id,
            aggregation_execution_id=seeded.aggregation_id,
            format=ExportFormat.json,
        )
    )
    return export.id


def _assert_rejected(
    session: Session,
    statement: str,
    parameters: dict[str, object],
    *,
    sqlstate: str,
    message: str,
) -> None:
    with pytest.raises(DBAPIError, match=message) as error, session.begin_nested():
        _execute_and_flush(session, statement, parameters)
    assert getattr(error.value.orig, "sqlstate", None) == sqlstate
    session.expire_all()


def _execute_and_flush(session: Session, statement: str, parameters: dict[str, object]) -> None:
    session.execute(text(statement), parameters)
    session.flush()


def _fail_evaluation(session: Session, evaluation_id: UUID) -> None:
    repository = SqlAlchemyEvaluationRepository(session)
    repository.claim_evaluation(evaluation_id, started_at=NOW)
    repository.mark_evaluation_finished(
        evaluation_id,
        status=EvaluationExecutionStatus.failed,
        finished_at=NOW,
        failure_class="EvaluationInputError",
        failure_diagnostic="synthetic failure",
    )


def _fail_export(session: Session, export_id: UUID) -> None:
    repository = SqlAlchemyExportRepository(session)
    repository.claim_export(export_id, started_at=NOW)
    repository.mark_export_finished(
        export_id,
        status=ExportExecutionStatus.failed,
        finished_at=NOW,
        failure_class="ExportInputError",
        failure_diagnostic="synthetic failure",
    )


_Create = Callable[[Session, _SeededRun], UUID]
_Fail = Callable[[Session, UUID], None]
_EXECUTION_TABLES: list[tuple[str, _Create, _Fail, str]] = [
    ("evaluation_executions", _evaluation, _fail_evaluation, "config_sha256 = repeat('f', 64)"),
    ("export_executions", _export, _fail_export, "human_resp_id = '#someone_else'"),
]


@pytest.mark.parametrize(("table", "create", "fail", "provenance_change"), _EXECUTION_TABLES)
@pytest.mark.postgres_rollback
def test_database_rejects_skipping_the_lifecycle(
    db_session: Session, table: str, create: _Create, fail: _Fail, provenance_change: str
) -> None:
    execution_id = create(db_session, _seed(db_session))

    _assert_rejected(
        db_session,
        f"UPDATE {table} SET status = 'completed', started_at = :now, finished_at = :now "  # noqa: S608 - fixed table list
        "WHERE id = :id",
        {"id": execution_id, "now": NOW},
        sqlstate="23514",
        message=f"illegal {table} lifecycle transition to completed",
    )


@pytest.mark.parametrize(("table", "create", "fail", "provenance_change"), _EXECUTION_TABLES)
@pytest.mark.postgres_rollback
def test_database_rejects_deleting_an_execution(
    db_session: Session, table: str, create: _Create, fail: _Fail, provenance_change: str
) -> None:
    execution_id = create(db_session, _seed(db_session))

    _assert_rejected(
        db_session,
        f"DELETE FROM {table} WHERE id = :id",  # noqa: S608 - fixed table list
        {"id": execution_id},
        sqlstate="55000",
        message=f"{table} lifecycle rows cannot be deleted",
    )


@pytest.mark.parametrize(("table", "create", "fail", "provenance_change"), _EXECUTION_TABLES)
@pytest.mark.postgres_rollback
def test_database_rejects_changing_creation_provenance(
    db_session: Session, table: str, create: _Create, fail: _Fail, provenance_change: str
) -> None:
    execution_id = create(db_session, _seed(db_session))

    _assert_rejected(
        db_session,
        f"UPDATE {table} SET {provenance_change} WHERE id = :id",  # noqa: S608 - fixed table list
        {"id": execution_id},
        sqlstate="55000",
        message=f"{table} provenance is immutable",
    )


@pytest.mark.parametrize(("table", "create", "fail", "provenance_change"), _EXECUTION_TABLES)
@pytest.mark.postgres_rollback
def test_database_rejects_changing_a_terminal_execution(
    db_session: Session, table: str, create: _Create, fail: _Fail, provenance_change: str
) -> None:
    execution_id = create(db_session, _seed(db_session))
    fail(db_session, execution_id)

    _assert_rejected(
        db_session,
        f"UPDATE {table} SET failure_diagnostic = 'rewritten' WHERE id = :id",  # noqa: S608 - fixed table list
        {"id": execution_id},
        sqlstate="55000",
        message=f"terminal {table} rows are immutable",
    )


@pytest.mark.postgres_rollback
def test_database_rejects_changing_evaluation_membership(db_session: Session) -> None:
    evaluation_id = _evaluation(db_session, _seed(db_session))

    _assert_rejected(
        db_session,
        "DELETE FROM evaluation_method_executions WHERE evaluation_execution_id = :id",
        {"id": evaluation_id},
        sqlstate="55000",
        message="evaluation method-execution membership is immutable",
    )


@pytest.mark.postgres_rollback
def test_database_rejects_membership_added_after_queuing(db_session: Session) -> None:
    seeded = _seed(db_session)
    evaluation_id = _evaluation(db_session, seeded)
    SqlAlchemyEvaluationRepository(db_session).mark_evaluation_queued(evaluation_id)

    _assert_rejected(
        db_session,
        "INSERT INTO evaluation_method_executions "
        "(evaluation_execution_id, method_execution_id, position) VALUES (:id, :member, 99)",
        {"id": evaluation_id, "member": seeded.execution_ids["gnd"]},
        sqlstate="55000",
        message="evaluation membership may only be added while pending",
    )


@pytest.mark.postgres_rollback
def test_database_rejects_a_member_from_another_run(db_session: Session) -> None:
    evaluation_id = _evaluation(db_session, _seed(db_session))
    foreign_execution_id = _seed(db_session).execution_ids["gnd"]

    _assert_rejected(
        db_session,
        "INSERT INTO evaluation_method_executions "
        "(evaluation_execution_id, method_execution_id, position) VALUES (:id, :member, 99)",
        {"id": evaluation_id, "member": foreign_execution_id},
        sqlstate="23514",
        message="evaluation members must be completed executions from its run",
    )


@pytest.mark.postgres_rollback
def test_database_rejects_failure_class_on_a_run_that_did_not_fail(db_session: Session) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories, slug_prefix="execution-guards")
    snapshot = seed_ready_snapshot(repositories, project.id, [tei_person_input(tei_id="p1")])
    run = seed_run(repositories, snapshot.id, [MethodRunConfig(name="gnd")])
    repositories.runs.mark_run_queued(run.id)
    repositories.runs.mark_run_started(run.id, started_at=NOW)

    _assert_rejected(
        db_session,
        "UPDATE runs SET failure_class = 'RuntimeError' WHERE id = :id",
        {"id": run.id},
        sqlstate="23514",
        message="only a failed runs row may have failure details",
    )


@pytest.mark.postgres_rollback
def test_database_rejects_failure_class_on_a_snapshot_that_did_not_fail(
    db_session: Session,
) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories, slug_prefix="execution-guards")
    snapshot = seed_pending_snapshot(repositories, project.id)

    _assert_rejected(
        db_session,
        "UPDATE dataset_snapshots SET failure_class = 'TeiImportError' WHERE id = :id",
        {"id": snapshot.id},
        sqlstate="23514",
        message="ck_dataset_snapshots_failure_class_requires_failed",
    )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE dataset_snapshots SET failure_diagnostic = 'rewritten' WHERE id = :id",
        "UPDATE dataset_snapshots SET status = 'pending' WHERE id = :id",
        "DELETE FROM dataset_snapshots WHERE id = :id",
    ],
)
@pytest.mark.postgres_rollback
def test_database_seals_a_failed_snapshot(db_session: Session, statement: str) -> None:
    repositories = session_repositories(db_session)
    project = seed_project(repositories, slug_prefix="execution-guards")
    snapshot = seed_pending_snapshot(repositories, project.id)
    assert repositories.projects.claim_snapshot_import(snapshot.id) is not None
    repositories.projects.fail_snapshot_import(
        snapshot.id, failure_class="TeiImportError", failure_diagnostic="synthetic failure"
    )

    _assert_rejected(
        db_session,
        statement,
        {"id": snapshot.id},
        sqlstate="55000",
        message="failed dataset snapshots are immutable",
    )
