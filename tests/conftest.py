"""Shared test configuration."""

import os
from collections.abc import Callable, Iterator
from typing import TypeAlias
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from hypothesis import settings
from psycopg import sql
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

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
