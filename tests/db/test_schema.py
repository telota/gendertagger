from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from gendertagger.db.schema import ORM_ROW_TYPES, metadata

EXPECTED_TABLES = {
    "aggregated_results",
    "aggregation_executions",
    "aggregation_method_executions",
    "annotations",
    "artifacts",
    "batch_dispatches",
    "dataset_snapshots",
    "evaluation_executions",
    "evaluation_method_executions",
    "export_executions",
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


def test_schema_registers_every_persistence_table() -> None:
    assert set(metadata.tables) == EXPECTED_TABLES
    assert len(ORM_ROW_TYPES) == len(EXPECTED_TABLES)
    assert len(set(ORM_ROW_TYPES)) == len(ORM_ROW_TYPES)


def test_schema_compiles_as_postgresql_ddl() -> None:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]  # Dynamic factory.

    for table in metadata.tables.values():
        statement = str(CreateTable(table).compile(dialect=dialect))
        assert f"CREATE TABLE {table.name}" in statement


def test_dispatch_schema_has_exactly_one_unique_foreign_key_owner() -> None:
    table = metadata.tables["batch_dispatches"]

    assert table.c.task_batch_id.nullable
    assert table.c.aggregation_execution_id.nullable
    assert table.c.dataset_snapshot_id.nullable
    assert table.c.evaluation_execution_id.nullable
    assert table.c.export_id.nullable
    assert {constraint.name for constraint in table.constraints} >= {
        "task_batch_single_dispatch",
        "aggregation_execution_single_dispatch",
        "dataset_snapshot_single_dispatch",
        "evaluation_execution_single_dispatch",
        "export_single_dispatch",
        "ck_batch_dispatches_exactly_one_target",
        "fk_batch_dispatches_task_batch_id_task_batches",
        "fk_batch_dispatches_aggregation_execution_id_aggregation_executions",
        "fk_batch_dispatches_dataset_snapshot_id_dataset_snapshots",
        "fk_batch_dispatches_evaluation_execution_id_evaluation_executions",
        "fk_batch_dispatches_export_id_export_executions",
    }
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} >= {
        "task_batches.id",
        "aggregation_executions.id",
        "dataset_snapshots.id",
        "evaluation_executions.id",
        "export_executions.id",
    }


def test_prediction_schema_requires_task_batch_provenance() -> None:
    table = metadata.tables["predictions"]

    assert not table.c.task_batch_id.nullable
    assert "task_batches.id" in {
        foreign_key.target_fullname for foreign_key in table.c.task_batch_id.foreign_keys
    }


def test_person_schema_stores_optional_structured_name_forms_as_jsonb() -> None:
    table = metadata.tables["person_records"]

    assert table.c.name_forms.nullable
    assert isinstance(table.c.name_forms.type, postgresql.JSONB)
    assert isinstance(table.c.events.type, postgresql.JSONB)
    assert not table.c.events.nullable
    assert not table.c.source_member_name.nullable
    assert not table.c.source_record_locator.nullable
    assert {constraint.name for constraint in table.constraints} >= {
        "ck_person_records_name_forms_array",
        "ck_person_records_events_array",
        "ck_person_records_source_member_name_nonblank",
        "ck_person_records_source_record_locator_nonblank",
    }


def test_snapshot_source_member_schema_has_ordered_unique_artifact_references() -> None:
    table = metadata.tables["snapshot_source_members"]

    assert {constraint.name for constraint in table.constraints} >= {
        "snapshot_source_member_ordinal",
        "snapshot_source_member_logical_name",
        "ck_snapshot_source_members_ordinal_nonnegative",
        "ck_snapshot_source_members_sha256_format",
        "fk_snapshot_source_members_artifact_id_artifacts",
        "fk_snapshot_source_members_dataset_snapshot_id_dataset_snapshots",
    }
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == {
        "artifacts.id",
        "dataset_snapshots.id",
    }
