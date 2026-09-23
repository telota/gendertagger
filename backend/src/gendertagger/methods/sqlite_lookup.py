"""Shared contracts for immutable SQLite-backed method lookup artifacts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from gendertagger.methods.base import MethodDependencyError

_LOOKUP_APPLICATION_ID: Final = 0x47544C4B  # ``GTLK``
LOOKUP_METADATA_TABLE: Final = "lookup_metadata"


class LookupAssetResolver(Protocol):
    """Materialize one registered content-addressed lookup to a verified path."""

    def materialize(self, logical_type: str, sha256: str) -> Path:
        """Return a stable local path for the selected artifact."""
        ...


class UnavailableLookupAssetResolver:
    """Fail prediction when runtime composition omitted lookup-asset storage."""

    def materialize(self, logical_type: str, sha256: str) -> Path:
        """Raise a permanent dependency error for an uncomposed resolver."""
        del logical_type, sha256
        msg = "lookup artifact resolver is not configured"
        raise MethodDependencyError(msg)


@dataclass(frozen=True, slots=True)
class LookupDatabaseMetadata:
    """Stable metadata embedded in a compiled SQLite lookup."""

    method_name: str
    lookup_schema_version: str
    compiler_version: str
    source_sha256: str
    source_version: str | None = None
    source_sha256s: tuple[str, ...] = ()

    def as_rows(self) -> list[tuple[str, str]]:
        """Return stable key/value rows for the lookup metadata table."""
        rows = [
            ("compiler_version", self.compiler_version),
            ("lookup_schema_version", self.lookup_schema_version),
            ("method_name", self.method_name),
            ("source_sha256", self.source_sha256),
            (
                "source_sha256s",
                json.dumps(
                    self.source_sha256s or (self.source_sha256,),
                    separators=(",", ":"),
                ),
            ),
            ("sqlite_version", sqlite3.sqlite_version),
        ]
        if self.source_version is not None:
            rows.append(("source_version", self.source_version))
        return sorted(rows)


def create_lookup_database(
    path: Path,
    metadata: LookupDatabaseMetadata,
) -> sqlite3.Connection:
    """Create an unpublished lookup database with deterministic baseline settings."""
    if path.exists():
        msg = f"lookup destination already exists: {path}"
        raise ValueError(msg)
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"PRAGMA application_id = {_LOOKUP_APPLICATION_ID}")
        connection.execute("PRAGMA page_size = 4096")
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute(
            """CREATE TABLE lookup_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID"""
        )
        connection.executemany(
            "INSERT INTO lookup_metadata (key, value) VALUES (?, ?)",
            metadata.as_rows(),
        )
        connection.commit()
    except BaseException:
        connection.close()
        path.unlink(missing_ok=True)
        raise
    return connection


def finalize_lookup_database(connection: sqlite3.Connection, *, record_count: int) -> None:
    """Seal compiler metadata and compact the unpublished lookup database."""
    if record_count < 0:
        msg = "lookup record_count must be nonnegative"
        raise ValueError(msg)
    connection.execute(
        "INSERT INTO lookup_metadata (key, value) VALUES ('record_count', ?)",
        (str(record_count),),
    )
    connection.commit()
    connection.execute("ANALYZE")
    connection.execute("VACUUM")
    connection.commit()


def open_lookup_database(
    path: Path,
    *,
    expected_method_name: str,
    expected_schema_version: str,
) -> sqlite3.Connection:
    """Open and validate an immutable method lookup database.

    Raises:
        MethodDependencyError: If the file is absent, malformed, or belongs to a
            different method or lookup schema.
    """
    connection: sqlite3.Connection | None = None
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        if application_id != _LOOKUP_APPLICATION_ID:
            msg = "artifact is not a gendertagger lookup database"
            raise MethodDependencyError(msg)
        metadata = dict(connection.execute("SELECT key, value FROM lookup_metadata").fetchall())
        if metadata.get("method_name") != expected_method_name:
            msg = "lookup artifact method metadata does not match the adapter"
            raise MethodDependencyError(msg)
        if metadata.get("lookup_schema_version") != expected_schema_version:
            msg = "lookup artifact schema version is unsupported"
            raise MethodDependencyError(msg)
        record_count = metadata.get("record_count")
        if record_count is None or not record_count.isdecimal():
            msg = "lookup artifact record count is invalid"
            raise MethodDependencyError(msg)
        return connection
    except MethodDependencyError:
        if connection is not None:
            connection.close()
        raise
    except (OSError, sqlite3.Error, ValueError) as error:
        if connection is not None:
            connection.close()
        msg = "lookup artifact cannot be opened or validated"
        raise MethodDependencyError(msg) from error
