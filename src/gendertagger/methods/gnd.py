"""GND authority adapter backed by an immutable local SQLite snapshot."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from gendertagger.methods.base import LookupMethodConfig, MethodDependencyError
from gendertagger.methods.gnd_snapshot import (
    GND_LOOKUP_LOGICAL_TYPE,
    GND_LOOKUP_SCHEMA_VERSION,
    GndEntityType,
)
from gendertagger.methods.normalization import GND_NORMALIZATION, normalize_raw_label
from gendertagger.methods.sqlite_lookup import (
    LookupAssetResolver,
    UnavailableLookupAssetResolver,
    open_lookup_database,
)
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput

_SQLITE_PARAMETER_BATCH_SIZE: Final = 900


class GndConfig(LookupMethodConfig):
    """Resolved configuration selecting a compiled local GND snapshot."""


@dataclass(frozen=True, slots=True)
class GndLookupRecord:
    """Validated authority evidence consumed by the GND adapter."""

    gnd_id: str
    entity_type: GndEntityType
    raw_entity_types: tuple[str, ...]
    gender_uri: str | None
    raw_gender_label: str | None
    lookup_label: str
    preferred_name: str | None
    record_status: str | None


class GndLookup(Protocol):
    """Bulk GND-ID lookup required by the adapter."""

    def get_many(self, gnd_ids: Sequence[str]) -> dict[str, GndLookupRecord]:
        """Return every present GND record keyed by input identifier."""
        ...


LookupFactory = Callable[[Path], GndLookup]


class SqliteGndLookup:
    """Read-only access to one validated compiled GND snapshot."""

    def __init__(self, path: Path) -> None:
        self._connection = open_lookup_database(
            path,
            expected_method_name="gnd",
            expected_schema_version=GND_LOOKUP_SCHEMA_VERSION,
        )

    def get_many(self, gnd_ids: Sequence[str]) -> dict[str, GndLookupRecord]:
        """Resolve GND IDs in bounded SQLite parameter batches."""
        unique_ids = tuple(dict.fromkeys(gnd_ids))
        found: dict[str, GndLookupRecord] = {}
        for offset in range(0, len(unique_ids), _SQLITE_PARAMETER_BATCH_SIZE):
            batch = unique_ids[offset : offset + _SQLITE_PARAMETER_BATCH_SIZE]
            placeholders = ",".join("?" for _ in batch)
            statement = (
                "SELECT gnd_id, entity_type, raw_entity_types, gender_uri, "  # noqa: S608
                "raw_gender_label, lookup_label, preferred_name, record_status "
                f"FROM gnd_entries WHERE gnd_id IN ({placeholders})"
            )
            for row in self._connection.execute(statement, batch):
                record = self._record_from_row(row)
                found[record.gnd_id] = record
        return found

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> GndLookupRecord:
        try:
            raw_entity_types = json.loads(str(row["raw_entity_types"]))
            if not isinstance(raw_entity_types, list) or not all(
                isinstance(value, str) for value in raw_entity_types
            ):
                raise ValueError
            return GndLookupRecord(
                gnd_id=str(row["gnd_id"]),
                entity_type=GndEntityType(str(row["entity_type"])),
                raw_entity_types=tuple(raw_entity_types),
                gender_uri=_optional_text(row["gender_uri"]),
                raw_gender_label=_optional_text(row["raw_gender_label"]),
                lookup_label=str(row["lookup_label"]),
                preferred_name=_optional_text(row["preferred_name"]),
                record_status=_optional_text(row["record_status"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            msg = "GND lookup contains an invalid authority row"
            raise MethodDependencyError(msg) from error


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


class GndMethod:
    """Classify records from local GND gender and entity-type evidence."""

    descriptor = MethodDescriptor(
        name="gnd",
        implementation_version="gnd_v1",
        normalization_version=GND_NORMALIZATION.normalization_version,
    )
    config_model = GndConfig

    def __init__(
        self,
        *,
        lookup_asset_resolver: LookupAssetResolver | None = None,
        lookup_factory: LookupFactory | None = None,
    ) -> None:
        self._lookup_asset_resolver = lookup_asset_resolver or UnavailableLookupAssetResolver()
        self._lookup_factory = lookup_factory or SqliteGndLookup
        self._lookups: dict[str, GndLookup] = {}

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: GndConfig,
    ) -> list[PredictionResult]:
        """Classify people in input order without external network access."""
        lookup = self._get_lookup(config.lookup_sha256)
        records = lookup.get_many([person.gnd_id for person in people if person.gnd_id is not None])
        return [self._predict_one(person, records.get(person.gnd_id or "")) for person in people]

    def _get_lookup(self, lookup_sha256: str) -> GndLookup:
        lookup = self._lookups.get(lookup_sha256)
        if lookup is None:
            path = self._lookup_asset_resolver.materialize(
                GND_LOOKUP_LOGICAL_TYPE,
                lookup_sha256,
            )
            lookup = self._lookup_factory(path)
            self._lookups[lookup_sha256] = lookup
        return lookup

    @staticmethod
    def _predict_one(person: PersonInput, record: GndLookupRecord | None) -> PredictionResult:
        if person.gnd_id is None or record is None:
            return normalize_raw_label(
                GND_NORMALIZATION,
                "no_gnd",
                raw_output={
                    "gnd_id": person.gnd_id,
                    "lookup_match": False,
                },
            )

        raw_label = (
            "organisation"
            if record.entity_type is GndEntityType.corporate_body
            else record.lookup_label
        )
        return normalize_raw_label(
            GND_NORMALIZATION,
            raw_label,
            raw_output={
                "gnd_id": record.gnd_id,
                "lookup_match": True,
                "entity_type": record.entity_type.value,
                "raw_entity_types": list(record.raw_entity_types),
                "gender_uri": record.gender_uri,
                "source_gender_label": record.raw_gender_label,
                "preferred_name": record.preferred_name,
                "record_status": record.record_status,
            },
        )
