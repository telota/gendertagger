from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gendertagger.methods.base import MethodDependencyError
from gendertagger.methods.sqlite_lookup import (
    LookupDatabaseMetadata,
    create_lookup_database,
    finalize_lookup_database,
    open_lookup_database,
)

pytestmark = pytest.mark.unit


def _lookup(path: Path) -> None:
    connection = create_lookup_database(
        path,
        LookupDatabaseMetadata(
            method_name="test_method",
            lookup_schema_version="test_lookup_v1",
            compiler_version="test_compiler_v1",
            source_sha256="a" * 64,
            source_version="source-v1",
        ),
    )
    connection.execute("CREATE TABLE entries (key TEXT PRIMARY KEY) WITHOUT ROWID")
    connection.execute("INSERT INTO entries (key) VALUES ('one')")
    finalize_lookup_database(connection, record_count=1)
    connection.close()


def test_open_lookup_validates_metadata_and_enforces_query_only(tmp_path: Path) -> None:
    path = tmp_path / "lookup.sqlite3"
    _lookup(path)

    connection = open_lookup_database(
        path,
        expected_method_name="test_method",
        expected_schema_version="test_lookup_v1",
    )
    try:
        assert connection.execute("SELECT key FROM entries").fetchone()[0] == "one"
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM entries")
    finally:
        connection.close()


def test_open_lookup_rejects_another_method_or_schema(tmp_path: Path) -> None:
    path = tmp_path / "lookup.sqlite3"
    _lookup(path)

    with pytest.raises(MethodDependencyError, match="method metadata"):
        open_lookup_database(
            path,
            expected_method_name="other_method",
            expected_schema_version="test_lookup_v1",
        )
    with pytest.raises(MethodDependencyError, match="schema version"):
        open_lookup_database(
            path,
            expected_method_name="test_method",
            expected_schema_version="test_lookup_v2",
        )
