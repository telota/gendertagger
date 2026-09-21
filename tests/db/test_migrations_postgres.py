from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

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
    "batch_dispatches",
    "dataset_snapshots",
    "method_executions",
    "person_external_ids",
    "person_records",
    "predictions",
    "projects",
    "review_states",
    "runs",
    "snapshot_source_members",
    "task_batches",
    "user_roles",
    "users",
}
EXPECTED_IMMUTABILITY_TRIGGERS = {
    "trg_aggregated_results_parent_completed",
    "trg_aggregated_results_validate_insert",
    "trg_aggregated_results_immutable",
    "trg_aggregation_executions_lifecycle",
    "trg_aggregation_executions_provenance",
    "trg_aggregation_executions_result_coverage",
    "trg_aggregation_methods_validate_mutation",
    "trg_annotations_append_only",
    "trg_artifacts_immutable",
    "trg_dataset_snapshots_immutable_ready",
    "trg_method_executions_lifecycle",
    "trg_method_executions_provenance",
    "trg_person_external_ids_immutable_ready_snapshot",
    "trg_person_records_immutable_ready_snapshot",
    "trg_predictions_parent_completed",
    "trg_predictions_validate_insert",
    "trg_predictions_immutable",
    "trg_runs_lifecycle",
    "trg_runs_provenance",
    "trg_snapshot_source_members_immutable_ready_snapshot",
    "trg_task_batches_lifecycle",
    "trg_task_batches_prediction_coverage",
    "trg_task_batches_provenance",
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
        prediction_columns = {
            column["name"]: column for column in inspect(engine).get_columns("predictions")
        }
        assert prediction_columns["task_batch_id"]["nullable"] is False
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


def test_sliding_session_migration_caps_existing_sessions_at_their_original_expiry(
    postgres_database_factory: Callable[[], str],
) -> None:
    database_url = postgres_database_factory()
    config = alembic_config(database_url)
    command.upgrade(config, "20260903_0002")
    user_id = uuid4()
    original_expires_at = datetime(2026, 9, 21, 17, tzinfo=UTC)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO users (id, display_name) VALUES (:id, 'Synthetic reviewer')"),
                {"id": user_id},
            )
            connection.execute(
                text(
                    """INSERT INTO user_sessions (id, user_id, csrf_secret, expires_at)
                    VALUES (:id, :user_id, 'csrf-secret', :expires_at)"""
                ),
                {"id": "a" * 64, "user_id": user_id, "expires_at": original_expires_at},
            )

        command.upgrade(config, "head")

        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """SELECT keep_signed_in, expires_at, absolute_expires_at
                    FROM user_sessions WHERE id = :id"""
                ),
                {"id": "a" * 64},
            ).one()
    finally:
        engine.dispose()

    # A session issued under the fixed 8-hour lifetime must never be extended by sliding renewal.
    assert row.keep_signed_in is False
    assert row.expires_at == original_expires_at
    assert row.absolute_expires_at == original_expires_at
