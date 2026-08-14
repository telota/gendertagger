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
