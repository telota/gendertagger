"""Adapter and SQLite compiler for the Wiki-Gendersort name table.

Provisioning compiles the published ``NamesOut.txt`` once into an immutable
content-addressed lookup. Prediction uses the compatible rules in ADR-0045 and preserves the frozen
normalization. SQLite provisioning follows ADR-0023.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final, Protocol

from gendertagger.methods.base import LookupMethodConfig
from gendertagger.methods.name_tokens import consensus_label, usable_forename_tokens
from gendertagger.methods.normalization import WIKI_GENDERSORT_NORMALIZATION, normalize_raw_label
from gendertagger.methods.sqlite_lookup import (
    LookupAssetResolver,
    LookupDatabaseMetadata,
    UnavailableLookupAssetResolver,
    create_lookup_database,
    finalize_lookup_database,
    open_lookup_database,
)
from gendertagger.methods.wiki_gendersort_rules import clean_candidates, resolve_candidates
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput

# Native Wiki-Gendersort label -> project label. ``INI`` (pure initials) maps to
# the shared no-token label so it abstains; ``UNK`` stays a substantive unknown.
_LABEL_MAP: Final[dict[str, str]] = {
    "M": "male",
    "F": "female",
    "UNI": "unisex",
    "INI": "no_name",
    "UNK": "unknown",
}
_PRIORITY: Final[tuple[str, ...]] = ("no_name", "unknown", "unisex", "male", "female")
_MALE_LABELS: Final[frozenset[str]] = frozenset({"male"})
_FEMALE_LABELS: Final[frozenset[str]] = frozenset({"female"})

WIKI_GENDERSORT_LOOKUP_LOGICAL_TYPE: Final = "wiki_gendersort_lookup"
WIKI_GENDERSORT_LOOKUP_SCHEMA_VERSION: Final = "wiki_gendersort_lookup_v1"
WIKI_GENDERSORT_LOOKUP_COMPILER_VERSION: Final = "wiki_gendersort_lookup_compiler_v1"
_SQLITE_PARAMETER_BATCH_SIZE: Final = 900
# A ``NamesOut.txt`` line holds a name and a trailing native label, separated by tabs.
_NAMES_OUT_MIN_FIELDS: Final = 2
_NATIVE_LABELS: Final = frozenset(_LABEL_MAP)


class WikiGendersortConfig(LookupMethodConfig):
    """Resolved configuration selecting a compiled Wiki-Gendersort lookup."""


class NameAssigner(Protocol):
    """Structural contract resolving first-name tokens to native labels."""

    def assign_many(self, names: Sequence[str]) -> list[tuple[str, str | None]]:
        """Return native labels and matched candidates in input order."""
        ...


AssignerFactory = Callable[[Path], NameAssigner]

Transliterate = Callable[[str], str]


def _load_transliterate() -> Transliterate:
    from unidecode import unidecode

    transliterate: Transliterate = unidecode
    return transliterate


class WikiGendersortTable:
    """Resolve compatible name candidates through an immutable SQLite lookup."""

    def __init__(self, lookup_path: Path) -> None:
        self._transliterate = _load_transliterate()
        self._connection = open_lookup_database(
            lookup_path,
            expected_method_name="wiki_gendersort",
            expected_schema_version=WIKI_GENDERSORT_LOOKUP_SCHEMA_VERSION,
        )

    def assign(self, name: str) -> tuple[str, str | None]:
        """Resolve one first-name token to a native label and matched name."""
        return self.assign_many([name])[0]

    def assign_many(self, names: Sequence[str]) -> list[tuple[str, str | None]]:
        """Resolve tokens through one bulk candidate lookup."""
        candidates_by_name = {
            name: clean_candidates(name, self._transliterate) for name in dict.fromkeys(names)
        }
        candidate_lists = [candidates_by_name[name] for name in names]
        unique_candidates = tuple(
            dict.fromkeys(candidate for candidates in candidate_lists for candidate in candidates)
        )
        native_by_candidate: dict[str, str] = {}
        for offset in range(0, len(unique_candidates), _SQLITE_PARAMETER_BATCH_SIZE):
            batch = unique_candidates[offset : offset + _SQLITE_PARAMETER_BATCH_SIZE]
            placeholders = ",".join("?" for _ in batch)
            statement = (
                "SELECT name, native_label FROM wiki_names "  # noqa: S608
                f"WHERE name IN ({placeholders})"
            )
            rows = self._connection.execute(statement, batch)
            native_by_candidate.update((str(row["name"]), str(row["native_label"])) for row in rows)
        return [
            resolve_candidates(name, candidates, native_by_candidate)
            for name, candidates in zip(names, candidate_lists, strict=True)
        ]


def compile_wiki_gendersort_lookup(
    source_path: Path,
    destination_path: Path,
    *,
    source_sha256: str,
    source_version: str | None = None,
) -> int:
    """Compile one published ``NamesOut.txt`` into an immutable SQLite lookup."""
    entries: dict[str, str] = {}
    with source_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < _NAMES_OUT_MIN_FIELDS:
                continue
            raw_name = "\t".join(parts[:-1]).upper()
            normalized_name = raw_name[0] + raw_name[1:].lower() if raw_name else raw_name
            native_label = parts[-1]
            if native_label not in _NATIVE_LABELS:
                msg = f"unsupported Wiki-Gendersort label at source line {line_number}"
                raise ValueError(msg)
            entries[normalized_name] = native_label
    if not entries:
        msg = "Wiki-Gendersort source produced an empty lookup"
        raise ValueError(msg)

    connection = create_lookup_database(
        destination_path,
        LookupDatabaseMetadata(
            method_name="wiki_gendersort",
            lookup_schema_version=WIKI_GENDERSORT_LOOKUP_SCHEMA_VERSION,
            compiler_version=WIKI_GENDERSORT_LOOKUP_COMPILER_VERSION,
            source_sha256=source_sha256,
            source_version=source_version,
        ),
    )
    try:
        connection.execute(
            """CREATE TABLE wiki_names (
                name TEXT PRIMARY KEY,
                native_label TEXT NOT NULL
            ) WITHOUT ROWID"""
        )
        connection.executemany(
            "INSERT INTO wiki_names (name, native_label) VALUES (?, ?)",
            ((name, entries[name]) for name in sorted(entries)),
        )
        finalize_lookup_database(connection, record_count=len(entries))
    except BaseException:
        connection.close()
        destination_path.unlink(missing_ok=True)
        raise
    connection.close()
    return len(entries)


class WikiGendersortMethod:
    """Classify forename tokens through a compiled Wiki-Gendersort lookup."""

    descriptor = MethodDescriptor(
        name="wiki_gendersort",
        implementation_version="wiki_gendersort_v2",
        normalization_version=WIKI_GENDERSORT_NORMALIZATION.normalization_version,
    )
    config_model = WikiGendersortConfig

    def __init__(
        self,
        *,
        lookup_asset_resolver: LookupAssetResolver | None = None,
        assigner_factory: AssignerFactory | None = None,
    ) -> None:
        self._lookup_asset_resolver = lookup_asset_resolver or UnavailableLookupAssetResolver()
        self._assigner_factory = assigner_factory or WikiGendersortTable
        self._assigners: dict[str, NameAssigner] = {}

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: WikiGendersortConfig,
    ) -> list[PredictionResult]:
        """Classify each person from its forename tokens in input order."""
        assigner = self._get_assigner(config.lookup_sha256)
        token_lists = [usable_forename_tokens(person.forenames) for person in people]
        all_tokens = [token for tokens in token_lists for token in tokens]
        assignments = assigner.assign_many(all_tokens)
        results: list[PredictionResult] = []
        offset = 0
        for tokens in token_lists:
            next_offset = offset + len(tokens)
            results.append(self._predict_one(tokens, assignments[offset:next_offset]))
            offset = next_offset
        return results

    def _get_assigner(self, lookup_sha256: str) -> NameAssigner:
        assigner = self._assigners.get(lookup_sha256)
        if assigner is None:
            path = self._lookup_asset_resolver.materialize(
                WIKI_GENDERSORT_LOOKUP_LOGICAL_TYPE,
                lookup_sha256,
            )
            assigner = self._assigner_factory(path)
            self._assigners[lookup_sha256] = assigner
        return assigner

    @staticmethod
    def _predict_one(
        tokens: list[str],
        assignments: Sequence[tuple[str, str | None]],
    ) -> PredictionResult:
        native_labels = [native for native, _ in assignments]
        mapped_labels = [_LABEL_MAP.get(native, "unknown") for native in native_labels]
        matched_names = [matched or "" for _, matched in assignments]
        raw_label = consensus_label(
            mapped_labels,
            priority=_PRIORITY,
            male_labels=_MALE_LABELS,
            female_labels=_FEMALE_LABELS,
        )
        return normalize_raw_label(
            WIKI_GENDERSORT_NORMALIZATION,
            raw_label,
            raw_output={
                "tokens": tokens,
                "native_labels": native_labels,
                "token_results": mapped_labels,
                "matched_names": matched_names,
            },
        )
