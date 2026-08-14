"""Shared test configuration."""

import os
from collections.abc import Callable, Iterator
from functools import partial
from typing import TypeAlias, cast
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from hypothesis import settings
from psycopg import sql
from redis import Redis
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from gendertagger.db.base import Base
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.services.unit_of_work import UnitOfWorkFactory

settings.register_profile(
    "ci",
    deadline=None,
    derandomize=True,
    max_examples=200,
    print_blob=True,
)
settings.register_profile(
    "fuzz",
    deadline=None,
    max_examples=2_000,
    print_blob=True,
)
DatabaseFactory: TypeAlias = Callable[[], str]


def _alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.attributes["database_url"] = database_url
    return config


def _psycopg_url(database_url: URL) -> str:
    return database_url.set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def postgres_database_factory() -> Iterator[DatabaseFactory]:
    """Create isolated temporary databases and remove all of them after the suite."""
    configured_url = os.environ.get("GENDERTAGGER_TEST_DATABASE_URL")
    if configured_url is None:
        pytest.skip("GENDERTAGGER_TEST_DATABASE_URL is required for PostgreSQL tests")
    admin_url = make_url(configured_url)
    if admin_url.get_backend_name() != "postgresql":
        pytest.fail("GENDERTAGGER_TEST_DATABASE_URL must use PostgreSQL")

    created_database_names: list[str] = []

    def create_database() -> str:
        database_name = f"gendertagger_test_{uuid4().hex}"
        with psycopg.connect(_psycopg_url(admin_url), autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
        created_database_names.append(database_name)
        return admin_url.set(database=database_name).render_as_string(hide_password=False)

    yield create_database

    with psycopg.connect(_psycopg_url(admin_url), autocommit=True) as connection:
        for database_name in created_database_names:
            connection.execute(
                """SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()""",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))


@pytest.fixture(scope="session")
def repository_database_url(postgres_database_factory: DatabaseFactory) -> str:
    """Return a temporary database migrated to the current Alembic head."""
    database_url = postgres_database_factory()
    command.upgrade(_alembic_config(database_url), "head")
    return database_url


@pytest.fixture(scope="session")
def postgres_engine(repository_database_url: str) -> Iterator[Engine]:
    """Return a PostgreSQL engine for the migrated repository database."""
    engine = create_engine(repository_database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def isolate_postgres_test(request: pytest.FixtureRequest) -> Iterator[None]:
    """Remove committed rows after each test that uses the shared PostgreSQL database."""
    needs_database = request.node.get_closest_marker("postgres") is not None or any(
        fixture_name in request.fixturenames
        for fixture_name in ("db_session", "postgres_engine", "postgres_unit_of_work")
    )
    if not needs_database:
        yield
        return

    engine = cast(Engine, request.getfixturevalue("postgres_engine"))
    yield

    with engine.begin() as connection:
        preparer = connection.dialect.identifier_preparer
        table_names = ", ".join(
            preparer.format_table(table)
            for table in sorted(Base.metadata.tables.values(), key=lambda table: table.fullname)
        )
        connection.exec_driver_sql(f"TRUNCATE TABLE {table_names} CASCADE")


@pytest.fixture(autouse=True)
def isolate_redis_test(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Purge the explicitly configured non-default Redis test database per test."""
    if request.node.get_closest_marker("redis") is None:
        yield
        return

    test_url = os.environ.get("GENDERTAGGER_TEST_REDIS_URL")
    if test_url is None:
        pytest.skip("GENDERTAGGER_TEST_REDIS_URL is required for Redis tests")
    database_path = urlsplit(test_url).path.removeprefix("/")
    if not database_path.isdecimal() or int(database_path) == 0:
        pytest.fail("GENDERTAGGER_TEST_REDIS_URL must select a dedicated nonzero database")
    broker_url = os.environ.get("GENDERTAGGER_CELERY_BROKER_URL")
    if broker_url is not None and broker_url != test_url:
        pytest.fail("Redis test and Celery broker URLs must select the same database")
    monkeypatch.setenv("GENDERTAGGER_CELERY_BROKER_URL", test_url)

    client: Redis = Redis.from_url(test_url)
    client.flushdb()
    try:
        yield
    finally:
        client.flushdb()
        client.close()


@pytest.fixture
def db_session(postgres_engine: Engine) -> Iterator[Session]:
    """Run each repository test inside a rolled-back outer transaction."""
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, autoflush=False, expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            if transaction.is_active:
                transaction.rollback()


@pytest.fixture
def postgres_unit_of_work(
    postgres_engine: Engine,
) -> Iterator[tuple[UnitOfWorkFactory, Connection]]:
    """Yield a real unit-of-work factory (and its connection) that rolls back.

    Each unit of work opens its own session on one shared connection using
    savepoints, so services that own their transaction boundaries run unchanged
    while the outer transaction discards every write when the test ends.
    """
    with postgres_engine.connect() as connection:
        transaction = connection.begin()

        def session_factory() -> Session:
            return Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
                autoflush=False,
                expire_on_commit=False,
            )

        try:
            yield partial(SqlAlchemyUnitOfWork, session_factory), connection
        finally:
            if transaction.is_active:
                transaction.rollback()
