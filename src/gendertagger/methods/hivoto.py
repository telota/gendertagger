"""Adapter for the HIVOTO historical first-name gender dataset.

The adapter tokenizes each person's forename with the shared name-token filter,
resolves each token against a lookup index built from a local HIVOTO snapshot,
and reduces the per-token labels by the method's priority consensus. The index
maps a normalized name to a majority-vote gender and an aggregated certainty.
The raw label is normalized against the frozen ``hivoto_v1`` profile. The
snapshot path is resolved run configuration, so the exact dataset is recorded in
provenance. See ADR-0014.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final

from pydantic import Field

from gendertagger.methods.base import MethodConfig
from gendertagger.methods.name_tokens import consensus_label, usable_forename_tokens
from gendertagger.methods.normalization import HIVOTO_NORMALIZATION, normalize_raw_label
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput

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

# Priority ranking used only to break majority-vote ties while aggregating the
# dataset into one gender per name; distinct from the per-token consensus above.
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

HivotoIndex = Mapping[str, tuple[str, str]]
IndexFactory = Callable[[str], HivotoIndex]


class HivotoConfig(MethodConfig):
    """Resolved configuration selecting the HIVOTO dataset snapshot."""

    dataset_path: str = Field(
        min_length=1,
        description="Filesystem path to the semicolon-delimited HIVOTO dataset snapshot.",
    )


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


def build_hivoto_index(dataset_path: str) -> dict[str, tuple[str, str]]:
    """Build the name lookup index from a local HIVOTO snapshot.

    Each row contributes its original and classified spellings as keys. Names
    seen multiple times take the majority-vote gender, ties broken by the index
    priority; certainty is ``sicher`` only when every entry for the name is
    ``sicher``, otherwise ``mittlere Sicherheit``.
    """
    index_rank = {label: rank for rank, label in enumerate(_INDEX_PRIORITY)}
    records: dict[str, list[tuple[str, str]]] = {}
    path = Path(dataset_path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            original = (row.get(_ORIGINAL_COLUMN) or "").strip().lower()
            classified = (row.get(_CLASSIFIED_COLUMN) or "").strip().lower().rstrip(".")
            gender = map_gender(row.get(_GENDER_COLUMN) or "")
            certainty = (row.get(_CERTAINTY_COLUMN) or "").strip()
            for key in {original, classified}:
                if not key:
                    continue
                records.setdefault(key, []).append((gender, certainty))

    index: dict[str, tuple[str, str]] = {}
    for key, entries in records.items():
        counts = Counter(gender for gender, _ in entries)
        winner = max(counts, key=lambda gender: (counts[gender], index_rank.get(gender, 0)))
        certainties = {certainty for _, certainty in entries}
        certainty = "sicher" if certainties == {"sicher"} else "mittlere Sicherheit"
        index[key] = (winner, certainty)
    return index


class HivotoMethod:
    """Structural :class:`~gendertagger.methods.base.GenderMethod` implementation."""

    descriptor = MethodDescriptor(
        name="hivoto",
        implementation_version="hivoto_v1",
        normalization_version=HIVOTO_NORMALIZATION.normalization_version,
    )
    config_model = HivotoConfig

    def __init__(self, index_factory: IndexFactory | None = None) -> None:
        self._index_factory = index_factory or build_hivoto_index
        self._indexes: dict[str, HivotoIndex] = {}

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: HivotoConfig,
    ) -> list[PredictionResult]:
        """Classify each person from its forename tokens in input order."""
        index = self._get_index(config.dataset_path)
        return [self._predict_one(index, person) for person in people]

    def _get_index(self, dataset_path: str) -> HivotoIndex:
        index = self._indexes.get(dataset_path)
        if index is None:
            index = self._index_factory(dataset_path)
            self._indexes[dataset_path] = index
        return index

    @staticmethod
    def _predict_one(index: HivotoIndex, person: PersonInput) -> PredictionResult:
        token_results: list[str] = []
        certainties: list[str] = []
        tokens = usable_forename_tokens(person.forenames)
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
