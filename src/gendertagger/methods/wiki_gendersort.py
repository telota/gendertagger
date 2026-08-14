"""Adapter for the Wiki-Gendersort first-name lookup table.

The adapter tokenizes each person's forename with the shared name-token filter,
resolves each token against a local ``NamesOut.txt`` snapshot through the ported
Wiki-Gendersort ``nameclean``/``assign`` logic, maps the native label to the
project alphabet, and reduces the per-token labels by the method's priority
consensus. The raw label is normalized against the frozen ``wiki_gendersort_v1``
profile. The snapshot path is resolved run configuration, so the exact authority
table used is recorded in provenance. See ADR-0013.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final, Protocol

from pydantic import Field

from gendertagger.methods.base import MethodConfig, MethodDependencyError
from gendertagger.methods.name_tokens import consensus_label, usable_forename_tokens
from gendertagger.methods.normalization import WIKI_GENDERSORT_NORMALIZATION, normalize_raw_label
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

_UNKNOWN_NATIVE: Final = "UNK"
_UNISEX_NATIVE: Final = "UNI"
_INITIALS_NATIVE: Final = "INI"


class WikiGendersortConfig(MethodConfig):
    """Resolved configuration selecting the Wiki-Gendersort name table snapshot."""

    names_db_path: str = Field(
        min_length=1,
        description="Filesystem path to the Wiki-Gendersort NamesOut.txt snapshot.",
    )


class NameAssigner(Protocol):
    """Structural contract resolving one first-name token to a native label."""

    def assign(self, name: str) -> tuple[str, str | None]:
        """Return ``(native_label, matched_name)`` for one token."""
        ...


AssignerFactory = Callable[[str], NameAssigner]

Transliterate = Callable[[str], str]


def _load_transliterate() -> Transliterate:
    try:
        from unidecode import unidecode
    except ImportError as error:  # pragma: no cover - exercised only without the extra
        msg = "wiki_gendersort requires the 'wiki' extra (install unidecode)"
        raise MethodDependencyError(msg) from error
    transliterate: Transliterate = unidecode
    return transliterate


def _count_alpha(name: str, transliterate: Transliterate) -> int:
    letters = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return sum(1 for char in name if transliterate(char) in letters)


def _count_vowel(name: str, transliterate: Transliterate) -> int:
    return sum(1 for char in name if transliterate(char) in "aeiouyAEIOUY")


def _clean_name(first_name: str, transliterate: Transliterate) -> list[str]:
    """Port of Wiki-Gendersort ``nameclean`` returning candidate lookup strings.

    Adapted verbatim for single-token inputs: quoted/parenthetical text is moved
    to the end, the name is split on non-letter characters, periods and fused
    initials are separated, hyphenated names keep the compound and their parts,
    and the surviving candidates are normalized and transliterated.
    """
    name = first_name
    while True:
        left_i = right_i = -1
        if '"' in name and name.find('"') != name.rfind('"'):
            left_i = name.find('"')
            right_i = left_i + 1 + name[left_i + 1 :].find('"')
        if "(" in name and ")" in name and name.find("(") < name.rfind(")"):
            left_i = name.find("(")
            right_i = name.rfind(")")
        if left_i != -1 and right_i != -1:
            name = name[:left_i] + " " + name[right_i + 1 :] + " " + name[left_i + 1 : right_i]
        else:
            break

    joined = ""
    for char in name:
        if _count_alpha(char, transliterate) >= 1 or char in {".", "-"}:
            joined += char
        else:
            joined += " "
    candidates = [part for part in joined.split() if _count_alpha(part, transliterate) != 0]

    index = 0
    while index < len(candidates):
        current = candidates[index]
        if (
            len(current) >= 4
            and current[-1] == "."
            and current[-2].isupper()
            and current[-3].islower()
        ):
            candidates.insert(index + 1, current[-2:])
            candidates[index] = current[:-2]
        if candidates[index][-1] == "." and 4 > len(candidates[index]) > 1:
            candidates.append(candidates[index][:-1])
            del candidates[index]
            index -= 1
        index += 1

    index = 0
    while index < len(candidates):
        if "." in candidates[index]:
            split = candidates[index].split(".")[::-1]
            for part in split:
                candidates.insert(index + 1, part)
            del candidates[index]
            index += len(split) - 1
        index += 1

    index = 0
    while index < len(candidates):
        while candidates[index] and candidates[index][0] == "-":
            candidates[index] = candidates[index][1:]
        while candidates[index] and candidates[index][-1] == "-":
            candidates[index] = candidates[index][:-1]
        if "-" in candidates[index]:
            for part in candidates[index].split("-")[::-1]:
                candidates.insert(index + 1, part)
        index += 1

    cleaned: list[str] = []
    for candidate in candidates:
        if (
            _count_alpha(candidate, transliterate) > 1
            and _count_vowel(candidate, transliterate) > 0
        ):
            if len(candidate) <= 1:
                normalized = candidate.upper()
            else:
                normalized = candidate[0].upper() + candidate[1:].lower()
            cleaned.append(normalized)
            transliterated = transliterate(normalized)
            if normalized != transliterated:
                cleaned.append(transliterated)
    return cleaned


class WikiGendersortTable:
    """Local ``NamesOut.txt`` lookup table with the ported ``assign`` behavior."""

    def __init__(self, names_db_path: str) -> None:
        self._transliterate = _load_transliterate()
        self._names_key: dict[str, str] = {}
        path = Path(names_db_path)
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2:
                    raw_name = "\t".join(parts[:-1]).upper()
                    if raw_name:
                        raw_name = raw_name[0] + raw_name[1:].lower()
                    self._names_key[raw_name] = parts[-1]

    def assign(self, name: str) -> tuple[str, str | None]:
        """Resolve one first-name token to its native label and matched name."""
        candidates = _clean_name(name, self._transliterate)
        native = _UNKNOWN_NATIVE
        matched: str | None = None
        for candidate in candidates:
            if candidate in self._names_key:
                found = self._names_key[candidate]
                if found != _UNKNOWN_NATIVE:
                    if matched is None:
                        matched = candidate
                    native = found
            if native not in {_UNKNOWN_NATIVE, _UNISEX_NATIVE}:
                matched = candidate
                break
        if not candidates and name:
            native = _INITIALS_NATIVE
        if name.upper() == "NULL":
            native = _UNKNOWN_NATIVE
        return native, matched


def _default_assigner_factory(names_db_path: str) -> NameAssigner:
    return WikiGendersortTable(names_db_path)


class WikiGendersortMethod:
    """Structural :class:`~gendertagger.methods.base.GenderMethod` implementation."""

    descriptor = MethodDescriptor(
        name="wiki_gendersort",
        implementation_version="wiki_gendersort_v1",
        normalization_version=WIKI_GENDERSORT_NORMALIZATION.normalization_version,
    )
    config_model = WikiGendersortConfig

    def __init__(self, assigner_factory: AssignerFactory | None = None) -> None:
        self._assigner_factory = assigner_factory or _default_assigner_factory
        self._assigners: dict[str, NameAssigner] = {}

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: WikiGendersortConfig,
    ) -> list[PredictionResult]:
        """Classify each person from its forename tokens in input order.

        Raises:
            MethodDependencyError: If the ``wiki`` extra is not installed.
        """
        assigner = self._get_assigner(config.names_db_path)
        return [self._predict_one(assigner, person) for person in people]

    def _get_assigner(self, names_db_path: str) -> NameAssigner:
        assigner = self._assigners.get(names_db_path)
        if assigner is None:
            assigner = self._assigner_factory(names_db_path)
            self._assigners[names_db_path] = assigner
        return assigner

    @staticmethod
    def _predict_one(assigner: NameAssigner, person: PersonInput) -> PredictionResult:
        tokens = usable_forename_tokens(person.forenames)
        native_labels: list[str] = []
        mapped_labels: list[str] = []
        matched_names: list[str] = []
        for token in tokens:
            native, matched = assigner.assign(token)
            native_labels.append(native)
            mapped_labels.append(_LABEL_MAP.get(native, "unknown"))
            matched_names.append(matched or "")
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
