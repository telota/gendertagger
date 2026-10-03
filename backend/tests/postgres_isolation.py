"""Proven rollback isolation for explicitly opted-in repository tests."""

from collections.abc import Generator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field

import pytest
from sqlalchemy import Connection, Engine, event
from sqlalchemy.orm import Session

from gendertagger.db.base import Base


def truncate_repository_tables(engine: Engine) -> None:
    """Establish the shared repository database's empty baseline without altering migrations."""
    with engine.begin() as connection:
        preparer = connection.dialect.identifier_preparer
        table_names = ", ".join(
            preparer.format_table(table)
            for table in sorted(Base.metadata.tables.values(), key=lambda table: table.fullname)
        )
        connection.exec_driver_sql(f"TRUNCATE TABLE {table_names} CASCADE")


def validate_rollback_marker(item: pytest.Item) -> None:
    """Reject inherited or incompatible opt-ins before any test can run."""
    markers = list(item.iter_markers_with_node("postgres_rollback"))
    if not markers:
        return
    reason: str | None = None
    if any(marker.args or marker.kwargs for _, marker in markers):
        reason = "does not accept arguments"
    elif any(node is not item for node, _ in markers):
        reason = "must be applied to each audited test, not a module or class"
    elif item.get_closest_marker("postgres") is None:
        reason = "requires the postgres marker"
    elif not isinstance(item, pytest.Function) or "db_session" not in item.fixturenames:
        reason = "requires the provided db_session fixture"
    elif (
        item.get_closest_marker("redis") is not None or "postgres_unit_of_work" in item.fixturenames
    ):
        reason = "cannot be combined with Redis or a separate unit-of-work fixture"
    if reason is not None:
        raise pytest.UsageError(f"{item.nodeid}: postgres_rollback {reason}")


@dataclass
class RollbackIsolation:
    """Record whether the bound transaction safely removed every opted-in write."""

    rolled_back: bool = False
    violations: set[str] = field(default_factory=set)
    _connection: Connection | None = field(default=None, init=False, repr=False)
    _opened: list[Connection] = field(default_factory=list, init=False, repr=False)
    _observing: bool = field(default=False, init=False, repr=False)

    @property
    def requires_cleanup(self) -> bool:
        """Keep committed cleanup unless rollback completed without an escape."""
        return not self.rolled_back or bool(self.violations)

    @contextmanager
    def observe(self) -> Generator[None, None, None]:
        """Observe escapes without interrupting SQLAlchemy's transaction finalizers.

        Engine events cover SQLAlchemy connections and commits. Direct DBAPI calls and textual
        transaction commands are outside this mode and must retain the default committed cleanup.
        """

        if self._observing:
            yield
            return

        def opened(candidate: Connection) -> None:
            self._opened.append(candidate)
            if self._connection is not None and candidate is not self._connection:
                self.violations.add("opened another SQLAlchemy connection")

        def committed(candidate: Connection) -> None:
            self.violations.add("committed a SQLAlchemy connection")

        event.listen(Engine, "engine_connect", opened)
        event.listen(Engine, "commit", committed)
        self._observing = True
        try:
            yield
        finally:
            event.remove(Engine, "commit", committed)
            event.remove(Engine, "engine_connect", opened)
            self._observing = False

    @contextmanager
    def bind(self, connection: Connection) -> Generator[None, None, None]:
        """Identify the owned connection and observe replacement outer transactions."""
        if self._connection is not None and self._connection is not connection:
            self.violations.add("opened another SQLAlchemy connection")
        self._connection = connection
        if any(candidate is not connection for candidate in self._opened):
            self.violations.add("opened another SQLAlchemy connection")

        def began(candidate: Connection) -> None:
            self.violations.add("started a replacement outer transaction")

        event.listen(connection, "begin", began)
        try:
            yield
        finally:
            event.remove(connection, "begin", began)


@contextmanager
def repository_session(
    engine: Engine, isolation: RollbackIsolation | None = None
) -> Generator[Session, None, None]:
    """Close the session and roll back its owned outer transaction before proving isolation."""
    observation = isolation.observe() if isolation else nullcontext()
    with observation, engine.connect() as connection:
        transaction = connection.begin()
        bound_observation = isolation.bind(connection) if isolation else nullcontext()
        with bound_observation:
            session = Session(
                bind=connection,
                autoflush=False,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint" if isolation else "conditional_savepoint",
            )
            try:
                yield session
            finally:
                try:
                    session.close()
                finally:
                    intact = transaction.is_active and connection.get_transaction() is transaction
                    if transaction.is_active:
                        transaction.rollback()
                    if isolation is not None:
                        isolation.rolled_back = intact and not transaction.is_active
