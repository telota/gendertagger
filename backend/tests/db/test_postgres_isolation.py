"""Real PostgreSQL regressions for proven rollback and committed cleanup fallback."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from sqlalchemy import Connection, Engine, select
from sqlalchemy.orm import Session
from tests.postgres_isolation import RollbackIsolation, repository_session

from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
from gendertagger.db.rows.users import UserRow
from gendertagger.models.user import UserCreate

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_bound_session_commit_keeps_writes_inside_the_rolled_back_transaction(
    postgres_engine: Engine,
) -> None:
    isolation = RollbackIsolation()
    with repository_session(postgres_engine, isolation) as session:
        user = SqlAlchemyUserRepository(session).add_user(UserCreate(display_name="Bound user"))
        session.commit()
        assert session.scalar(select(UserRow.id).where(UserRow.id == user.id)) == user.id

    assert isolation.rolled_back is True
    assert isolation.requires_cleanup is False
    assert isolation.violations == set()
    with postgres_engine.connect() as observer:
        assert observer.scalar(select(UserRow.id).where(UserRow.id == user.id)) is None


def test_independent_connection_requires_cleanup_after_the_primary_transaction_rolls_back(
    postgres_engine: Engine,
) -> None:
    isolation = RollbackIsolation()
    with repository_session(postgres_engine, isolation) as session:
        user = SqlAlchemyUserRepository(session).add_user(UserCreate(display_name="Primary user"))
        with postgres_engine.connect() as observer:
            assert observer.scalar(select(UserRow.id).where(UserRow.id == user.id)) is None

    assert isolation.rolled_back is True
    assert isolation.requires_cleanup is True
    assert isolation.violations == {"opened another SQLAlchemy connection"}
    with postgres_engine.connect() as observer:
        assert observer.scalar(select(UserRow.id).where(UserRow.id == user.id)) is None


def test_independent_session_commit_requires_cleanup_and_leaves_its_write_visible(
    postgres_engine: Engine,
) -> None:
    isolation = RollbackIsolation()
    with repository_session(postgres_engine, isolation) as session:
        primary = SqlAlchemyUserRepository(session).add_user(
            UserCreate(display_name="Primary user")
        )
        with Session(postgres_engine) as independent:
            committed = SqlAlchemyUserRepository(independent).add_user(
                UserCreate(display_name="Independent user")
            )
            independent.commit()

    assert isolation.rolled_back is True
    assert isolation.requires_cleanup is True
    assert isolation.violations == {
        "opened another SQLAlchemy connection",
        "committed a SQLAlchemy connection",
    }
    with postgres_engine.connect() as observer:
        assert observer.scalar(select(UserRow.id).where(UserRow.id == primary.id)) is None
        assert observer.scalar(select(UserRow.id).where(UserRow.id == committed.id)) == committed.id


def test_direct_bound_connection_commit_invalidates_proof_without_finalizer_errors(
    postgres_engine: Engine,
) -> None:
    isolation = RollbackIsolation()
    with repository_session(postgres_engine, isolation) as session:
        user = SqlAlchemyUserRepository(session).add_user(UserCreate(display_name="Escaped user"))
        connection = session.get_bind()
        assert isinstance(connection, Connection)
        connection.commit()

    assert isolation.rolled_back is False
    assert isolation.requires_cleanup is True
    assert isolation.violations == {"committed a SQLAlchemy connection"}
    with postgres_engine.connect() as observer:
        assert observer.scalar(select(UserRow.id).where(UserRow.id == user.id)) == user.id


def test_replacement_outer_transaction_requires_cleanup_even_after_the_session_closes(
    postgres_engine: Engine,
) -> None:
    isolation = RollbackIsolation()
    with repository_session(postgres_engine, isolation) as session:
        connection = session.get_bind()
        assert isinstance(connection, Connection)
        connection.rollback()
        replacement = connection.begin()

    assert isolation.rolled_back is False
    assert isolation.requires_cleanup is True
    assert isolation.violations == {"started a replacement outer transaction"}
    assert replacement.is_active is False


def test_failed_body_rolls_back_its_writes_and_removes_event_observers(
    postgres_engine: Engine,
) -> None:
    isolation = RollbackIsolation()

    def fail_after_writing() -> None:
        with repository_session(postgres_engine, isolation) as session:
            SqlAlchemyUserRepository(session).add_user(UserCreate(display_name="Failed user"))
            session.commit()
            raise RuntimeError("synthetic body failure")

    with pytest.raises(RuntimeError, match="synthetic body failure"):
        fail_after_writing()

    assert isolation.rolled_back is True
    assert isolation.requires_cleanup is False
    with postgres_engine.begin() as observer:
        assert observer.scalars(select(UserRow.id)).all() == []
    assert isolation.violations == set(), "event observers leaked into the following transaction"


@pytest.mark.parametrize("escape_phase", ["body", "setup", "teardown"])
def test_escaped_marked_test_fails_then_truncates_before_the_following_test(
    tmp_path: Path,
    escape_phase: str,
) -> None:
    module = tmp_path / "test_escaped_rollback.py"
    module.write_text(
        dedent(
            """
            import pytest
            from sqlalchemy import event, select
            from sqlalchemy.orm import Session
            from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
            from gendertagger.db.rows.users import UserRow
            from gendertagger.models.user import UserCreate

            pytestmark = [pytest.mark.integration, pytest.mark.postgres]
            cleanup_statements = []

            @pytest.fixture(scope="session", autouse=True)
            def observe_cleanup(postgres_engine):
                def recorded(connection, cursor, statement, parameters, context, executemany):
                    if statement.startswith("TRUNCATE TABLE "):
                        cleanup_statements.append(statement)

                event.listen(postgres_engine, "before_cursor_execute", recorded)
                yield
                event.remove(postgres_engine, "before_cursor_execute", recorded)

            def commit_independent_user(postgres_engine):
                with Session(postgres_engine) as independent:
                    SqlAlchemyUserRepository(independent).add_user(
                        UserCreate(display_name="Committed child user")
                    )
                    independent.commit()

            @pytest.fixture
            def independently_committing_fixture(postgres_engine, isolate_postgres_test):
                if ESCAPE_PHASE == "setup":
                    commit_independent_user(postgres_engine)
                yield
                if ESCAPE_PHASE == "teardown":
                    commit_independent_user(postgres_engine)

            @pytest.mark.postgres_rollback
            def test_incorrectly_marked_case_commits_independently(
                independently_committing_fixture, db_session, postgres_engine
            ):
                primary = SqlAlchemyUserRepository(db_session).add_user(
                    UserCreate(display_name="Rolled back child user")
                )
                assert db_session.scalar(select(UserRow.id).where(UserRow.id == primary.id))
                if ESCAPE_PHASE == "body":
                    commit_independent_user(postgres_engine)

            def test_following_unmarked_case_sees_clean_database(db_session):
                assert len(cleanup_statements) == 1
                assert db_session.scalars(select(UserRow.id)).all() == []
            """
        )
        + f"\nESCAPE_PHASE = {escape_phase!r}\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(  # noqa: S603 -- the interpreter, plugin and generated paths are test-owned.
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tests.conftest",
            "-c",
            str(_BACKEND_ROOT / "pyproject.toml"),
            "-v",
            "--tb=short",
            "--color=no",
            str(module),
        ],
        cwd=_BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr

    assert result.returncode == pytest.ExitCode.TESTS_FAILED, output
    assert "postgres_rollback isolation was not proven" in output, output
    assert "opened another SQLAlchemy connection" in output, output
    assert "committed a SQLAlchemy connection" in output, output
    assert "test_following_unmarked_case_sees_clean_database PASSED" in output, output
    assert "2 passed, 1 error" in output, output
