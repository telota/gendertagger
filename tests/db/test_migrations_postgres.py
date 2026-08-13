from collections.abc import Callable

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

EXPECTED_APPLICATION_TABLES = {
    "aggregated_results",
    "aggregation_executions",
    "aggregation_method_executions",
    "annotations",
    "artifacts",
    "dataset_snapshots",
    "method_executions",
    "person_external_ids",
    "person_records",
    "predictions",
    "projects",
    "review_states",
    "runs",
    "task_batches",
    "user_roles",
    "users",
}
EXPECTED_IMMUTABILITY_TRIGGERS = {
    "trg_aggregated_results_immutable",
    "trg_annotations_append_only",
    "trg_artifacts_immutable",
    "trg_dataset_snapshots_immutable_ready",
    "trg_person_external_ids_immutable_ready_snapshot",
    "trg_person_records_immutable_ready_snapshot",
    "trg_predictions_immutable",
}


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.attributes["database_url"] = database_url
    return config


def test_initial_migration_upgrades_downgrades_and_has_no_drift(
    postgres_database_factory: Callable[[], str],
) -> None:
    database_url = postgres_database_factory()
    config = alembic_config(database_url)

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) >= EXPECTED_APPLICATION_TABLES
        with engine.connect() as connection:
            trigger_names = set(
                connection.execute(
                    text(
                        """SELECT tgname
                        FROM pg_trigger
                        WHERE NOT tgisinternal AND tgname LIKE 'trg_%'"""
                    )
                ).scalars()
            )
        assert trigger_names == EXPECTED_IMMUTABILITY_TRIGGERS
    finally:
        engine.dispose()

    command.check(config)
    command.downgrade(config, "base")

    engine = create_engine(database_url)
    try:
        assert not EXPECTED_APPLICATION_TABLES.intersection(inspect(engine).get_table_names())
        with engine.connect() as connection:
            function_count = connection.execute(
                text(
                    """SELECT count(*)
                    FROM pg_proc
                    WHERE proname LIKE 'gendertagger_%'"""
                )
            ).scalar_one()
        assert function_count == 0
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    command.check(config)
