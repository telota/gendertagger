import json
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
    "batch_dispatches",
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


def test_aggregation_outbox_migration_preserves_existing_batch_dispatches(
    postgres_database_factory: Callable[[], str],
) -> None:
    database_url = postgres_database_factory()
    config = alembic_config(database_url)
    command.upgrade(config, "20260814_0003")
    artifact_id = uuid4()
    project_id = uuid4()
    snapshot_id = uuid4()
    run_id = uuid4()
    execution_id = uuid4()
    batch_id = uuid4()
    batch_dispatch_id = uuid4()

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO artifacts
                    (id, logical_type, storage_uri, sha256, byte_size, media_type)
                    VALUES (:id, 'source_tei', 'local-sha256:test', :sha256, 1,
                            'application/tei+xml')"""
                ),
                {"id": artifact_id, "sha256": "a" * 64},
            )
            connection.execute(
                text(
                    """INSERT INTO projects (id, slug, display_name)
                    VALUES (:id, 'migration-fixture', 'Migration fixture')"""
                ),
                {"id": project_id},
            )
            connection.execute(
                text(
                    """INSERT INTO dataset_snapshots
                    (id, project_id, source_artifact_id, source_sha256, parser_version)
                    VALUES (:id, :project_id, :artifact_id, :sha256, 'tei_parser_v1')"""
                ),
                {
                    "id": snapshot_id,
                    "project_id": project_id,
                    "artifact_id": artifact_id,
                    "sha256": "a" * 64,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO runs
                    (id, dataset_snapshot_id, resolved_config, config_sha256,
                     code_git_commit, application_version, python_version)
                    VALUES (:id, :snapshot_id, CAST(:config AS jsonb), :sha256,
                            'c', '0.0.0', '3.13')"""
                ),
                {
                    "id": run_id,
                    "snapshot_id": snapshot_id,
                    "config": json.dumps({"methods": []}),
                    "sha256": "b" * 64,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO method_executions
                    (id, run_id, method_name, implementation_version,
                     normalization_version, config_sha256, queue_name)
                    VALUES (:id, :run_id, 'fixture_method', 'fixture_v1',
                            'fixture_v1', :sha256, 'cpu')"""
                ),
                {"id": execution_id, "run_id": run_id, "sha256": "c" * 64},
            )
            connection.execute(
                text(
                    """INSERT INTO task_batches
                    (id, method_execution_id, batch_index, record_offset,
                     record_count, queue_name)
                    VALUES (:id, :execution_id, 0, 0, 1, 'cpu')"""
                ),
                {"id": batch_id, "execution_id": execution_id},
            )
            connection.execute(
                text(
                    """INSERT INTO batch_dispatches
                    (id, task_batch_id, queue_name, payload, available_at)
                    VALUES (:id, :batch_id, 'cpu', CAST(:payload AS jsonb), now())"""
                ),
                {
                    "id": batch_dispatch_id,
                    "batch_id": batch_id,
                    "payload": json.dumps(
                        {
                            "method_execution_id": str(execution_id),
                            "task_batch_id": str(batch_id),
                        }
                    ),
                },
            )
    finally:
        engine.dispose()

    command.upgrade(config, "20260814_0004")
    aggregation_id = uuid4()
    aggregation_dispatch_id = uuid4()
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            preserved_batch_id = connection.execute(
                text(
                    """SELECT task_batch_id FROM batch_dispatches
                    WHERE id = :dispatch_id"""
                ),
                {"dispatch_id": batch_dispatch_id},
            ).scalar_one()
            assert preserved_batch_id == batch_id
            connection.execute(
                text(
                    """INSERT INTO aggregation_executions
                    (id, run_id, strategy, config_sha256, status)
                    VALUES (:id, :run_id, 'reference_v1', :sha256, 'queued')"""
                ),
                {"id": aggregation_id, "run_id": run_id, "sha256": "d" * 64},
            )
            connection.execute(
                text(
                    """INSERT INTO batch_dispatches
                    (id, aggregation_execution_id, queue_name, payload, available_at)
                    VALUES (:id, :aggregation_id, 'cpu', CAST(:payload AS jsonb), now())"""
                ),
                {
                    "id": aggregation_dispatch_id,
                    "aggregation_id": aggregation_id,
                    "payload": json.dumps({"aggregation_execution_id": str(aggregation_id)}),
                },
            )
    finally:
        engine.dispose()

    command.downgrade(config, "20260814_0003")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            remaining_dispatch_ids = set(
                connection.execute(text("SELECT id FROM batch_dispatches")).scalars()
            )
        assert remaining_dispatch_ids == {batch_dispatch_id}
        columns = {
            column["name"]: column for column in inspect(engine).get_columns("batch_dispatches")
        }
        assert "aggregation_execution_id" not in columns
        assert columns["task_batch_id"]["nullable"] is False
    finally:
        engine.dispose()


def test_structured_name_forms_migration_preserves_legacy_people_and_downgrades(
    postgres_database_factory: Callable[[], str],
) -> None:
    database_url = postgres_database_factory()
    config = alembic_config(database_url)
    command.upgrade(config, "20260814_0004")
    artifact_id = uuid4()
    project_id = uuid4()
    snapshot_id = uuid4()
    person_id = uuid4()

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO artifacts
                    (id, logical_type, storage_uri, sha256, byte_size, media_type)
                    VALUES (:id, 'source_tei', 'local-sha256:legacy', :sha256, 1,
                            'application/tei+xml')"""
                ),
                {"id": artifact_id, "sha256": "e" * 64},
            )
            connection.execute(
                text(
                    """INSERT INTO projects (id, slug, display_name)
                    VALUES (:id, 'structured-name-migration', 'Structured name migration')"""
                ),
                {"id": project_id},
            )
            connection.execute(
                text(
                    """INSERT INTO dataset_snapshots
                    (id, project_id, source_artifact_id, source_sha256, parser_version,
                     import_config)
                    VALUES (:id, :project_id, :artifact_id, :sha256, 'tei_parser_v1',
                            CAST(:import_config AS jsonb))"""
                ),
                {
                    "id": snapshot_id,
                    "project_id": project_id,
                    "artifact_id": artifact_id,
                    "sha256": "e" * 64,
                    "import_config": json.dumps({"profile": "tei_p5_person_register_v1"}),
                },
            )
            connection.execute(
                text(
                    """INSERT INTO person_records
                    (id, dataset_snapshot_id, tei_id, surname, forenames, alt_names)
                    VALUES (:id, :snapshot_id, 'legacy-person', 'Example',
                            ARRAY['Anna'], ARRAY['A. Example'])"""
                ),
                {"id": person_id, "snapshot_id": snapshot_id},
            )
    finally:
        engine.dispose()

    command.upgrade(config, "20260814_0005")
    engine = create_engine(database_url)
    try:
        columns = {
            column["name"]: column for column in inspect(engine).get_columns("person_records")
        }
        assert columns["name_forms"]["nullable"] is True
        assert {
            constraint["name"]
            for constraint in inspect(engine).get_check_constraints("person_records")
        } >= {"ck_person_records_name_forms_array"}
        with engine.connect() as connection:
            name_forms = connection.execute(
                text("SELECT name_forms FROM person_records WHERE id = :person_id"),
                {"person_id": person_id},
            ).scalar_one()
        assert name_forms is None
    finally:
        engine.dispose()

    command.downgrade(config, "20260814_0004")
    engine = create_engine(database_url)
    try:
        column_names = {column["name"] for column in inspect(engine).get_columns("person_records")}
        assert "name_forms" not in column_names
        with engine.connect() as connection:
            legacy_person = connection.execute(
                text(
                    """SELECT surname, forenames, alt_names
                    FROM person_records WHERE id = :person_id"""
                ),
                {"person_id": person_id},
            ).one()
        assert tuple(legacy_person) == ("Example", ["Anna"], ["A. Example"])
    finally:
        engine.dispose()
