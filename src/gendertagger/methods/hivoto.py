"""Adapter and SQLite compiler for the HIVOTO historical first-name dataset.

Provisioning compiles the licensed semicolon-delimited source once into an
immutable content-addressed lookup. Workers bulk-resolve normalized tokens from
that lookup and retain the frozen ``hivoto_v1`` label and consensus behavior.
See ADR-0018 and ADR-0023.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final, Protocol

from gendertagger.methods.base import LookupMethodConfig
from gendertagger.methods.name_tokens import consensus_label, usable_forename_tokens
from gendertagger.methods.normalization import HIVOTO_NORMALIZATION, normalize_raw_label
from gendertagger.methods.sqlite_lookup import (
    LookupAssetResolver,
    LookupDatabaseMetadata,
    UnavailableLookupAssetResolver,
    create_lookup_database,
    finalize_lookup_database,
    open_lookup_database,
)
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput

HIVOTO_LOOKUP_LOGICAL_TYPE: Final = "hivoto_lookup"
HIVOTO_LOOKUP_SCHEMA_VERSION: Final = "hivoto_lookup_v1"
HIVOTO_LOOKUP_COMPILER_VERSION: Final = "hivoto_lookup_compiler_v1"

_PRIORITY: Final[tuple[str, ...]] = (
    "no_name",
    "unknown",
    "andy",
    "mostly_male",
    "mostly_female",
    "male",
    "female",
)
_MALE_LABELS: Final[frozenset[str]] = frozenset({"male", "mostly_male"})
_FEMALE_LABELS: Final[frozenset[str]] = frozenset({"female", "mostly_female"})

# Priority ranking used only to break majority-vote ties while compiling one
# gender per name; distinct from the prediction-time token consensus above.
_INDEX_PRIORITY: Final[tuple[str, ...]] = (
    "unknown",
    "andy",
    "mostly_male",
    "mostly_female",
    "male",
    "female",
)
_ORIGINAL_COLUMN: Final = "Originalschreibung"
_CLASSIFIED_COLUMN: Final = "Klassifizierte_Originalschreibung"
_GENDER_COLUMN: Final = "Namensgeschlecht"
_CERTAINTY_COLUMN: Final = "Sicherheit_Geschlechtszuordnung"
_SQLITE_PARAMETER_BATCH_SIZE: Final = 900

HivotoIndex = Mapping[str, tuple[str, str]]


class HivotoConfig(LookupMethodConfig):
    """Resolved configuration selecting a compiled HIVOTO lookup by digest."""


class HivotoLookup(Protocol):
    """Bulk key/value access required by the HIVOTO adapter."""

    def get_many(self, names: Sequence[str]) -> dict[str, tuple[str, str]]:
        """Return every present normalized name with gender and certainty."""
        ...


LookupFactory = Callable[[Path], HivotoLookup]


class SqliteHivotoLookup:
    """Read-only access to one validated compiled HIVOTO lookup."""

    def __init__(self, path: Path) -> None:
        self._connection = open_lookup_database(
            path,
            expected_method_name="hivoto",
            expected_schema_version=HIVOTO_LOOKUP_SCHEMA_VERSION,
        )

    def get_many(self, names: Sequence[str]) -> dict[str, tuple[str, str]]:
        """Resolve names in bounded SQLite parameter batches."""
        unique_names = tuple(dict.fromkeys(names))
        found: dict[str, tuple[str, str]] = {}
        for offset in range(0, len(unique_names), _SQLITE_PARAMETER_BATCH_SIZE):
            batch = unique_names[offset : offset + _SQLITE_PARAMETER_BATCH_SIZE]
            placeholders = ",".join("?" for _ in batch)
            statement = (
                "SELECT name, raw_gender, certainty FROM hivoto_names "  # noqa: S608
                f"WHERE name IN ({placeholders})"
            )
            rows = self._connection.execute(statement, batch)
            found.update(
                (str(row["name"]), (str(row["raw_gender"]), str(row["certainty"]))) for row in rows
            )
        return found


def map_gender(raw: str) -> str:
    """Map a HIVOTO ``Namensgeschlecht`` value to the method's raw label."""
    text = str(raw).strip()
    if text.startswith("männlich, vorwiegend"):
        return "mostly_male"
    if text.startswith("weiblich, vorwiegend"):
        return "mostly_female"
    if "männlich" in text:
        return "male"
    if "weiblich" in text:
        return "female"
    if "uneindeutig" in text:
        return "andy"
    return "unknown"


def build_hivoto_index(dataset_path: str | Path) -> dict[str, tuple[str, str]]:
    """Compile source rows to the frozen majority-vote name index."""
    index_rank = {label: rank for rank, label in enumerate(_INDEX_PRIORITY)}
    records: dict[str, list[tuple[str, str]]] = {}
    with Path(dataset_path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        required_columns = {
            _ORIGINAL_COLUMN,
            _CLASSIFIED_COLUMN,
            _GENDER_COLUMN,
            _CERTAINTY_COLUMN,
        }
        missing_columns = required_columns.difference(reader.fieldnames or ())
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            msg = f"HIVOTO source lacks required columns: {missing}"
            raise ValueError(msg)
        for row in reader:
            original = (row.get(_ORIGINAL_COLUMN) or "").strip().lower()
            classified = (row.get(_CLASSIFIED_COLUMN) or "").strip().lower().rstrip(".")
            gender = map_gender(row.get(_GENDER_COLUMN) or "")
            certainty = (row.get(_CERTAINTY_COLUMN) or "").strip()
            for key in {original, classified}:
                if key:
                    records.setdefault(key, []).append((gender, certainty))

    index: dict[str, tuple[str, str]] = {}
    for key, entries in records.items():
        counts = Counter(gender for gender, _ in entries)
        winner = max(counts, key=lambda gender: (counts[gender], index_rank.get(gender, 0)))
        certainties = {certainty for _, certainty in entries}
        certainty = "sicher" if certainties == {"sicher"} else "mittlere Sicherheit"
        index[key] = (winner, certainty)
    return index


def compile_hivoto_lookup(
    source_path: Path,
    destination_path: Path,
    *,
    source_sha256: str,
    source_version: str | None = None,
) -> int:
    """Compile one licensed HIVOTO source into an immutable SQLite lookup."""
    index = build_hivoto_index(source_path)
    if not index:
        msg = "HIVOTO source produced an empty lookup"
        raise ValueError(msg)
    connection = create_lookup_database(
        destination_path,
        LookupDatabaseMetadata(
            method_name="hivoto",
            lookup_schema_version=HIVOTO_LOOKUP_SCHEMA_VERSION,
            compiler_version=HIVOTO_LOOKUP_COMPILER_VERSION,
            source_sha256=source_sha256,
            source_version=source_version,
        ),
    )
    try:
        connection.execute(
            """CREATE TABLE hivoto_names (
                name TEXT PRIMARY KEY,
                raw_gender TEXT NOT NULL,
                certainty TEXT NOT NULL
            ) WITHOUT ROWID"""
        )
        connection.executemany(
            "INSERT INTO hivoto_names (name, raw_gender, certainty) VALUES (?, ?, ?)",
            ((name, *index[name]) for name in sorted(index)),
        )
        finalize_lookup_database(connection, record_count=len(index))
    except BaseException:
        connection.close()
        destination_path.unlink(missing_ok=True)
        raise
    connection.close()
    return len(index)


class HivotoMethod:
    """Classify forename tokens through a compiled HIVOTO lookup."""

    descriptor = MethodDescriptor(
        name="hivoto",
        implementation_version="hivoto_v1",
        normalization_version=HIVOTO_NORMALIZATION.normalization_version,
    )
    config_model = HivotoConfig

    def __init__(
        self,
        *,
        lookup_asset_resolver: LookupAssetResolver | None = None,
        lookup_factory: LookupFactory | None = None,
    ) -> None:
        self._lookup_asset_resolver = lookup_asset_resolver or UnavailableLookupAssetResolver()
        self._lookup_factory = lookup_factory or SqliteHivotoLookup
        self._lookups: dict[str, HivotoLookup] = {}

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: HivotoConfig,
    ) -> list[PredictionResult]:
        """Classify each person from its forename tokens in input order."""
        lookup = self._get_lookup(config.lookup_sha256)
        token_lists = [usable_forename_tokens(person.forenames) for person in people]
        keys = [token.lower().rstrip(".,;:)\"'") for tokens in token_lists for token in tokens]
        entries = lookup.get_many(keys)
        return [self._predict_one(entries, tokens) for tokens in token_lists]

    def _get_lookup(self, lookup_sha256: str) -> HivotoLookup:
        lookup = self._lookups.get(lookup_sha256)
        if lookup is None:
            path = self._lookup_asset_resolver.materialize(
                HIVOTO_LOOKUP_LOGICAL_TYPE,
                lookup_sha256,
            )
            lookup = self._lookup_factory(path)
            self._lookups[lookup_sha256] = lookup
        return lookup

    @staticmethod
    def _predict_one(index: HivotoIndex, tokens: list[str]) -> PredictionResult:
        token_results: list[str] = []
        certainties: list[str] = []
        for token in tokens:
            key = token.lower().rstrip(".,;:)\"'")
            gender, certainty = index.get(key, ("unknown", ""))
            token_results.append(gender)
            certainties.append(certainty)
        raw_label = consensus_label(
            token_results,
            priority=_PRIORITY,
            male_labels=_MALE_LABELS,
            female_labels=_FEMALE_LABELS,
        )
        return normalize_raw_label(
            HIVOTO_NORMALIZATION,
            raw_label,
            raw_output={
                "tokens": tokens,
                "token_results": token_results,
                "certainties": certainties,
            },
        )
