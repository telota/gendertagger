import json
from collections.abc import Callable
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

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
            settings_row = (
                connection.execute(
                    text("SELECT id, revision, branding_overrides FROM deployment_settings")
                )
                .mappings()
                .one()
            )
        assert settings_row == {"id": 1, "revision": 0, "branding_overrides": {}}
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


def test_worker_provenance_migration_preserves_history_and_guards_new_claims(
    postgres_database_factory: Callable[[], str],
) -> None:
    database_url = postgres_database_factory()
    config = alembic_config(database_url)
    command.upgrade(config, "20261003_0013")
    engine = create_engine(database_url)
    ids = {
        name: uuid4()
        for name in (
            "user",
            "team",
            "project",
            "artifact",
            "snapshot",
            "person",
            "old_run",
            "old_execution",
            "old_batch",
            "open_run",
            "open_execution",
            "open_batch",
        )
    }
    historical_queries = {
        "artifacts": "SELECT to_jsonb(resource)::text FROM artifacts AS resource ORDER BY id",
        "dataset_snapshots": (
            "SELECT to_jsonb(resource)::text FROM dataset_snapshots AS resource ORDER BY id"
        ),
        "person_records": "SELECT to_jsonb(resource)::text FROM person_records AS resource ORDER BY id",
        "runs": "SELECT to_jsonb(resource)::text FROM runs AS resource ORDER BY id",
        "method_executions": (
            "SELECT to_jsonb(resource)::text FROM method_executions AS resource ORDER BY id"
        ),
        "task_batches": "SELECT to_jsonb(resource)::text FROM task_batches AS resource ORDER BY id",
    }
    receipt = {
        "code_git_commit": "actual-worker-revision",
        "application_version": "0.1.0",
        "python_version": "3.12.7",
        "dependency_lock_sha256": "b" * 64,
        "dependency_versions": {"pydantic": "2.11.7"},
        "container_image_digest": None,
        "hostname": "worker.example",
        "process_id": 1234,
    }
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO users (id, display_name) VALUES (:user, 'Historical operator')"),
                ids,
            )
            connection.execute(
                text(
                    "INSERT INTO teams (id, slug, display_name) "
                    "VALUES (:team, 'provenance-team', 'Provenance team')"
                ),
                ids,
            )
            connection.execute(
                text("INSERT INTO team_memberships (team_id, user_id) VALUES (:team, :user)"), ids
            )
            connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id, slug, display_name, team_id, manager_user_id, created_by_user_id) "
                    "VALUES (:project, 'provenance-project', 'Provenance project', :team, :user, :user)"
                ),
                ids,
            )
            connection.execute(
                text(
                    "INSERT INTO artifacts (id, logical_type, storage_uri, sha256, byte_size, "
                    "media_type, project_id) VALUES (:artifact, 'tei_source', "
                    "'file:///historical.xml', :digest, 14, 'application/xml', :project)"
                ),
                {**ids, "digest": "a" * 64},
            )
            connection.execute(
                text(
                    "INSERT INTO dataset_snapshots "
                    "(id, project_id, source_artifact_id, source_sha256, parser_version) "
                    "VALUES (:snapshot, :project, :artifact, :digest, 'historical-parser')"
                ),
                {**ids, "digest": "a" * 64},
            )
            connection.execute(
                text(
                    "INSERT INTO person_records "
                    "(id, dataset_snapshot_id, tei_id, surname, note, source_member_name, "
                    "source_record_locator) VALUES (:person, :snapshot, 'historical-person', "
                    "'Preserved', 'Original bytes', 'source.xml', '1')"
                ),
                ids,
            )
            connection.execute(
                text(
                    "UPDATE dataset_snapshots SET status = 'ready', record_count = 1, ready_at = now() "
                    "WHERE id = :snapshot"
                ),
                ids,
            )
            for prefix in ("old", "open"):
                parameters = {
                    **ids,
                    "run": ids[f"{prefix}_run"],
                    "execution": ids[f"{prefix}_execution"],
                    "batch": ids[f"{prefix}_batch"],
                    "digest": "a" * 64,
                }
                connection.execute(
                    text(
                        "INSERT INTO runs (id, dataset_snapshot_id, resolved_config, config_sha256, "
                        "code_git_commit, application_version, python_version) "
                        'VALUES (:run, :snapshot, \'{"methods":[{"name":"historical_method"}]}\', :digest, '
                        "'historical-revision', '0.1.0', '3.12.7')"
                    ),
                    parameters,
                )
                connection.execute(
                    text(
                        "INSERT INTO method_executions (id, run_id, method_name, implementation_version, "
                        "normalization_version, config_sha256, queue_name, worker_metadata) "
                        "VALUES (:execution, :run, 'historical_method', '1', '1', :digest, 'cpu', "
                        '\'{"historical":"sealed"}\')'
                    ),
                    parameters,
                )
                connection.execute(
                    text(
                        "INSERT INTO task_batches (id, method_execution_id, batch_index, record_offset, "
                        "record_count, queue_name) VALUES (:batch, :execution, 0, 0, 1, 'cpu')"
                    ),
                    parameters,
                )
            connection.execute(
                text(
                    "UPDATE task_batches SET status = 'running', started_at = now(), "
                    "worker_task_id = 'historical-task', attempt_count = 1 WHERE id = :old_batch"
                ),
                ids,
            )
            connection.execute(
                text(
                    "UPDATE task_batches SET status = 'failed', finished_at = now(), "
                    "failure_class = 'HistoricalError', failure_diagnostic = 'Original failure' "
                    "WHERE id = :old_batch"
                ),
                ids,
            )
            for statement in (
                "UPDATE method_executions SET status = 'queued' WHERE id = :old_execution",
                "UPDATE method_executions SET status = 'running', started_at = now() "
                "WHERE id = :old_execution",
                "UPDATE method_executions SET status = 'failed', finished_at = now(), "
                "failure_class = 'HistoricalError', failure_diagnostic = 'Original failure' "
                "WHERE id = :old_execution",
                "UPDATE runs SET status = 'queued' WHERE id = :old_run",
                "UPDATE runs SET status = 'running', started_at = now() WHERE id = :old_run",
                "UPDATE runs SET status = 'failed', finished_at = now(), "
                "failure_class = 'HistoricalError', failure_diagnostic = 'Original failure' "
                "WHERE id = :old_run",
            ):
                connection.execute(text(statement), ids)
            historical_bytes = {
                table: connection.execute(text(query)).scalars().all()
                for table, query in historical_queries.items()
            }

        for cycle in range(2):
            command.upgrade(config, "head")
            command.check(config)
            with engine.begin() as connection:
                for table, query in historical_queries.items():
                    if table == "runs":
                        query = (
                            "SELECT (to_jsonb(resource) - 'dependency_versions')::text "
                            "FROM runs AS resource ORDER BY id"
                        )
                    elif table == "task_batches" and cycle:
                        query = (
                            "SELECT (to_jsonb(resource) - 'worker_provenance')::text "
                            "FROM task_batches AS resource WHERE id <> :open_batch ORDER BY id"
                        )
                    elif table == "task_batches":
                        query = (
                            "SELECT (to_jsonb(resource) - 'worker_provenance')::text "
                            "FROM task_batches AS resource ORDER BY id"
                        )
                    actual = connection.execute(text(query), ids).scalars().all()
                    expected = historical_bytes[table]
                    if cycle and table == "task_batches":
                        expected = [
                            value
                            for value in expected
                            if json.loads(value)["id"] != str(ids["open_batch"])
                        ]
                    assert actual == expected
                assert (
                    connection.scalar(
                        text("SELECT count(*) FROM runs WHERE dependency_versions IS NOT NULL")
                    )
                    == 0
                )
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM task_batches WHERE worker_provenance IS NOT NULL"
                        )
                    )
                    == 0
                )
                if cycle == 0:
                    parameters = {**ids, "receipt": json.dumps(receipt)}
                    for invalid in ("[]", "null", '"not-an-object"'):
                        with (
                            pytest.raises(DBAPIError, match="dependency_versions_object"),
                            connection.begin_nested(),
                        ):
                            connection.execute(
                                text(
                                    "INSERT INTO runs (id, dataset_snapshot_id, resolved_config, "
                                    "config_sha256, code_git_commit, application_version, python_version, "
                                    "dependency_versions) SELECT :new_run, dataset_snapshot_id, "
                                    "resolved_config, config_sha256, code_git_commit, application_version, "
                                    "python_version, CAST(:dependencies AS jsonb) FROM runs "
                                    "WHERE id = :open_run"
                                ),
                                {**ids, "new_run": uuid4(), "dependencies": invalid},
                            )
                    for statement, message in (
                        (
                            "UPDATE runs SET dependency_versions = '{}' WHERE id = :open_run",
                            "runs provenance is immutable",
                        ),
                        (
                            "UPDATE task_batches SET worker_provenance = CAST(:receipt AS jsonb) "
                            "WHERE id = :open_batch",
                            "task batch worker provenance",
                        ),
                        (
                            "UPDATE task_batches SET status = 'running', started_at = now() "
                            "WHERE id = :open_batch",
                            "worker provenance is required",
                        ),
                        (
                            "INSERT INTO task_batches (id, method_execution_id, batch_index, "
                            "record_offset, record_count, queue_name, worker_provenance) "
                            "VALUES (:new_batch, :open_execution, 1, 0, 1, 'cpu', CAST(:receipt AS jsonb))",
                            "worker provenance requires an initial claim",
                        ),
                    ):
                        with pytest.raises(DBAPIError, match=message), connection.begin_nested():
                            connection.execute(
                                text(statement), {**parameters, "new_batch": uuid4()}
                            )
                    connection.execute(
                        text("UPDATE task_batches SET status = 'queued' WHERE id = :open_batch"),
                        ids,
                    )
                    with (
                        pytest.raises(DBAPIError, match="worker provenance is required"),
                        connection.begin_nested(),
                    ):
                        connection.execute(
                            text(
                                "UPDATE task_batches SET status = 'running', started_at = now() "
                                "WHERE id = :open_batch"
                            ),
                            ids,
                        )
                    for invalid in ("[]", "null", '"not-an-object"'):
                        with (
                            pytest.raises(DBAPIError, match="worker_provenance_object"),
                            connection.begin_nested(),
                        ):
                            connection.execute(
                                text(
                                    "UPDATE task_batches SET status = 'running', started_at = now(), "
                                    "worker_provenance = CAST(:receipt AS jsonb) WHERE id = :open_batch"
                                ),
                                {**ids, "receipt": invalid},
                            )
                    connection.execute(
                        text(
                            "UPDATE task_batches SET status = 'running', started_at = now(), "
                            "worker_task_id = 'actual-task', attempt_count = 1, "
                            "worker_provenance = CAST(:receipt AS jsonb) WHERE id = :open_batch"
                        ),
                        parameters,
                    )
                    assert (
                        connection.scalar(
                            text(
                                "SELECT worker_provenance FROM task_batches WHERE id = :open_batch"
                            ),
                            ids,
                        )
                        == receipt
                    )
                    duplicate = connection.execute(
                        text(
                            "UPDATE task_batches SET worker_provenance = '{}' WHERE id = :open_batch "
                            "AND status IN ('pending', 'queued')"
                        ),
                        ids,
                    )
                    assert duplicate.rowcount == 0
                    for replacement in ("{}", "null"):
                        with (
                            pytest.raises(DBAPIError, match="worker provenance is immutable"),
                            connection.begin_nested(),
                        ):
                            connection.execute(
                                text(
                                    "UPDATE task_batches SET worker_provenance = CAST(:receipt AS jsonb) "
                                    "WHERE id = :open_batch"
                                ),
                                {**ids, "receipt": replacement},
                            )
                    connection.execute(
                        text(
                            "UPDATE task_batches SET status = 'failed', finished_at = now(), "
                            "failure_class = 'ExampleError', failure_diagnostic = 'Example failure' "
                            "WHERE id = :open_batch"
                        ),
                        ids,
                    )
                    with (
                        pytest.raises(DBAPIError, match="terminal task_batches rows are immutable"),
                        connection.begin_nested(),
                    ):
                        connection.execute(
                            text(
                                "UPDATE task_batches SET worker_provenance = '{}' WHERE id = :open_batch"
                            ),
                            ids,
                        )
            if cycle == 0:
                command.downgrade(config, "20261003_0013")
                assert "dependency_versions" not in {
                    column["name"] for column in inspect(engine).get_columns("runs")
                }
                assert "worker_provenance" not in {
                    column["name"] for column in inspect(engine).get_columns("task_batches")
                }
                with engine.begin() as connection:
                    savepoint = connection.begin_nested()
                    parameters = {**ids, "new_batch": uuid4()}
                    connection.execute(
                        text(
                            "INSERT INTO task_batches (id, method_execution_id, batch_index, "
                            "record_offset, record_count, queue_name) "
                            "VALUES (:new_batch, :open_execution, 1, 0, 1, 'cpu')"
                        ),
                        parameters,
                    )
                    with (
                        pytest.raises(DBAPIError, match="task_batches provenance is immutable"),
                        connection.begin_nested(),
                    ):
                        connection.execute(
                            text(
                                "UPDATE task_batches SET queue_name = 'gpu' WHERE id = :new_batch"
                            ),
                            parameters,
                        )
                    connection.execute(
                        text(
                            "UPDATE task_batches SET status = 'running', started_at = now() "
                            "WHERE id = :new_batch"
                        ),
                        parameters,
                    )
                    savepoint.rollback()
    finally:
        engine.dispose()
