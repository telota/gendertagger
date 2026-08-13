"""Alembic migration environment for the canonical PostgreSQL schema."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context

from gendertagger.db.schema import metadata
from gendertagger.db.session import create_database_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    configured_url = config.attributes.get("database_url")
    if configured_url is not None:
        if not isinstance(configured_url, str):
            msg = "Alembic database_url attribute must be a string"
            raise TypeError(msg)
        return configured_url
    environment_url = os.environ.get("GENDERTAGGER_DATABASE_URL")
    if environment_url is None:
        msg = "GENDERTAGGER_DATABASE_URL is required for Alembic commands"
        raise RuntimeError(msg)
    return environment_url


def run_migrations_offline() -> None:
    """Render migrations without opening a database connection."""
    context.configure(
        url=_database_url(),
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations through one transaction-aware PostgreSQL connection."""
    engine = create_database_engine(_database_url())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=metadata,
                compare_type=True,
                compare_server_default=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
