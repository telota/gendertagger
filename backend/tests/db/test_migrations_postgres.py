from collections.abc import Callable
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
    "dispatch_outbox",
    "deployment_settings",
    "dataset_snapshots",
    "evaluation_executions",
    "evaluation_method_executions",
    "export_executions",
    "game_round_events",
    "game_rounds",
    "method_executions",
    "person_external_ids",
    "person_records",
    "predictions",
    "project_memberships",
    "projects",
    "public_classification_jobs",
    "review_states",
    "runs",
    "snapshot_source_members",
    "task_batches",
    "user_credentials",
    "user_roles",
    "user_preferences",
    "user_sessions",
    "team_memberships",
    "teams",
    "users",
}
ALEMBIC_VERSION_TABLE = "alembic_version"
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
    "trg_evaluation_executions_lifecycle",
    "trg_evaluation_executions_provenance",
    "trg_evaluation_methods_validate_mutation",
    "trg_export_executions_lifecycle",
    "trg_export_executions_provenance",
    "trg_method_executions_lifecycle",
    "trg_method_executions_provenance",
    "trg_person_external_ids_immutable_ready_snapshot",
    "trg_person_records_immutable_ready_snapshot",
    "trg_predictions_parent_completed",
    "trg_predictions_validate_insert",
    "trg_predictions_immutable",
    "trg_public_classification_jobs_immutable",
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
        assert set(inspect(engine).get_table_names()) == {
            *EXPECTED_APPLICATION_TABLES,
            ALEMBIC_VERSION_TABLE,
        }
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
            settings_row = (
                connection.execute(
                    text("SELECT id, revision, branding_overrides FROM deployment_settings")
                )
                .mappings()
                .one()
            )
        assert settings_row == {"id": 1, "revision": 0, "branding_overrides": {}}
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
        assert set(inspect(engine).get_table_names()) <= {ALEMBIC_VERSION_TABLE}
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


def test_game_mode_forward_migration_preserves_projects_and_defaults_disabled(
    postgres_database_factory: Callable[[], str],
) -> None:
    database_url = postgres_database_factory()
    config = alembic_config(database_url)
    command.upgrade(config, "20260926_0010")
    engine = create_engine(database_url)
    user_id = uuid4()
    team_id = uuid4()
    project_id = uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO users (id, display_name) VALUES (:user_id, 'Existing operator')"),
                {"user_id": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO teams (id, slug, display_name) "
                    "VALUES (:team_id, 'existing-team', 'Existing team')"
                ),
                {"team_id": team_id},
            )
            connection.execute(
                text("INSERT INTO team_memberships (team_id, user_id) VALUES (:team_id, :user_id)"),
                {"team_id": team_id, "user_id": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id, slug, display_name, team_id, manager_user_id, created_by_user_id) "
                    "VALUES (:project_id, 'existing-project', 'Existing project', "
                    ":team_id, :user_id, :user_id)"
                ),
                {
                    "project_id": project_id,
                    "team_id": team_id,
                    "user_id": user_id,
                },
            )

        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            enabled = connection.scalar(
                text("SELECT game_mode_enabled FROM projects WHERE id = :project_id"),
                {"project_id": project_id},
            )
        assert enabled is False
    finally:
        engine.dispose()


def test_preferences_forward_migration_preserves_accounts_without_backfilling_defaults(
    postgres_database_factory: Callable[[], str],
) -> None:
    database_url = postgres_database_factory()
    config = alembic_config(database_url)
    command.upgrade(config, "20260925_0007")
    engine = create_engine(database_url)
    user_id = uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO users (id, display_name) VALUES (:id, 'Existing account')"),
                {"id": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO user_credentials (user_id, username, password_hash) "
                    "VALUES (:id, 'existing_account', 'preserved-password-hash')"
                ),
                {"id": user_id},
            )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM user_preferences")) == 0
            assert connection.scalar(text("SELECT id FROM users")) == user_id
            assert connection.scalar(text("SELECT password_hash FROM user_credentials")) == (
                "preserved-password-hash"
            )
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO user_preferences (user_id) VALUES (:id)"), {"id": user_id}
            )
            defaults = (
                connection.execute(
                    text(
                        "SELECT locale, theme, desktop_sidebar_collapsed, revision FROM user_preferences"
                    )
                )
                .mappings()
                .one()
            )
            assert defaults == {
                "locale": None,
                "theme": "system",
                "desktop_sidebar_collapsed": False,
                "revision": 0,
            }
        command.downgrade(config, "20260925_0007")
        assert "user_preferences" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT id FROM users")) == user_id
            assert connection.scalar(text("SELECT password_hash FROM user_credentials")) == (
                "preserved-password-hash"
            )
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
