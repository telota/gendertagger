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
    assert {constraint.name for constraint in table.constraints} >= {
        "task_batch_single_dispatch",
        "aggregation_execution_single_dispatch",
        "ck_batch_dispatches_exactly_one_target",
        "fk_batch_dispatches_task_batch_id_task_batches",
        "fk_batch_dispatches_aggregation_execution_id_aggregation_executions",
    }
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} >= {
        "task_batches.id",
        "aggregation_executions.id",
    }


def test_person_schema_stores_optional_structured_name_forms_as_jsonb() -> None:
    table = metadata.tables["person_records"]

    assert table.c.name_forms.nullable
    assert isinstance(table.c.name_forms.type, postgresql.JSONB)
    assert {constraint.name for constraint in table.constraints} >= {
        "ck_person_records_name_forms_array"
    }
