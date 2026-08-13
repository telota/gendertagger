"""Deterministic parenthetical-qualifier rule adapter.

The rule reads relational qualifiers that editors place in parentheses inside a
person's name (for example ``Frölich (Frau des Heinrich)``) or as the leading
word of an editorial note. It emits a raw label and defers every canonical
outcome to the frozen ``parenthetical_qualifier_v1`` normalization profile so
raw method output and normalization provenance stay separable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from gendertagger.methods.base import MethodConfig
from gendertagger.methods.normalization import (
    PARENTHETICAL_QUALIFIER_NORMALIZATION,
    normalize_raw_label,
)
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput


class ParentheticalQualifierConfig(MethodConfig):
    """Closed configuration for the deterministic parenthetical-qualifier rule."""


_QUALIFIER_PATTERN: Final = re.compile(r"\(([^)]+)\)")

_FEMALE_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "frau",
        "tochter",
        "töchter",
        "mutter",
        "schwester",
        "schwestern",
        "fräulein",
        "mädchen",
        "witwe",
        "enkelin",
        "nichte",
        "großmutter",
        "stiefmutter",
    }
)
_MALE_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "mann",
        "sohn",
        "söhne",
        "vater",
        "bruder",
        "brüder",
        "onkel",
        "enkel",
        "neffe",
        "großvater",
        "herr",
        "stiefvater",
    }
)
# Family-group qualifiers name persons but cannot carry a single group gender.
_FAMILY_GROUP_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "familie",
        "kinder",
        "kind",
        "geschwister",
        "stiefgeschwister",
        "eltern",
        "ehepaar",
        "gebrüder",
    }
)
# Commercial/organisational qualifiers mark a corporate body rather than a person.
_ORGANISATION_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "weinhandlung",
        "bankier",
        "bankiers",
        "kaufleute",
        "firma",
    }
)

_FEMALE_LABEL: Final = "female"
_MALE_LABEL: Final = "male"
_GROUP_LABEL: Final = "unknown"
_INSTITUTION_LABEL: Final = "institution"


@dataclass(frozen=True, slots=True)
class _QualifierMatch:
    """One matched relational qualifier and the evidence that produced it."""

    raw_label: str
    matched_keyword: str
    matched_field: str


def _keyword_label(keyword: str) -> str | None:
    if keyword in _FEMALE_KEYWORDS:
        return _FEMALE_LABEL
    if keyword in _MALE_KEYWORDS:
        return _MALE_LABEL
    if keyword in _FAMILY_GROUP_KEYWORDS:
        return _GROUP_LABEL
    if keyword in _ORGANISATION_KEYWORDS:
        return _INSTITUTION_LABEL
    return None


def _normalize_words(content: str) -> list[str]:
    return [word.rstrip(".,").lower() for word in content.split()]


def _match_name_field(field_name: str, value: str) -> _QualifierMatch | None:
    for parenthetical in _QUALIFIER_PATTERN.finditer(value):
        words = _normalize_words(parenthetical.group(1).strip())
        if not words:
            continue
        # A leading relational word is the strongest signal; fall back to any word.
        leading = _keyword_label(words[0])
        if leading is not None:
            return _QualifierMatch(leading, words[0], field_name)
        for word in words:
            label = _keyword_label(word)
            if label is not None:
                return _QualifierMatch(label, word, field_name)
    return None


def _match_note(note: str) -> _QualifierMatch | None:
    words = _normalize_words(note)
    if not words:
        return None
    leading = words[0]
    # A note is only trusted on its first word and never asserts an institution.
    if leading in _FEMALE_KEYWORDS:
        return _QualifierMatch(_FEMALE_LABEL, leading, "note")
    if leading in _MALE_KEYWORDS:
        return _QualifierMatch(_MALE_LABEL, leading, "note")
    if leading in _FAMILY_GROUP_KEYWORDS:
        return _QualifierMatch(_GROUP_LABEL, leading, "note")
    return None


def _match_qualifier(person: PersonInput) -> _QualifierMatch | None:
    for field_name, value in (
        ("surname", person.surname),
        *(("forename", forename) for forename in person.forenames),
    ):
        if value:
            match = _match_name_field(field_name, value)
            if match is not None:
                return match
    if person.note:
        return _match_note(person.note)
    return None


class ParentheticalQualifierMethod:
    """Structural :class:`~gendertagger.methods.base.GenderMethod` implementation."""

    descriptor: Final = MethodDescriptor(
        name="parenthetical_qualifier",
        implementation_version="parenthetical_qualifier_v1",
        normalization_version=PARENTHETICAL_QUALIFIER_NORMALIZATION.normalization_version,
    )
    config_model: Final = ParentheticalQualifierConfig

    def predict_batch(
        self,
        people: list[PersonInput],
        config: ParentheticalQualifierConfig,
    ) -> list[PredictionResult]:
        """Classify each person from its relational qualifier evidence in order."""
        del config  # The deterministic rule takes no resolved configuration.
        return [self._predict_one(person) for person in people]

    @staticmethod
    def _predict_one(person: PersonInput) -> PredictionResult:
        match = _match_qualifier(person)
        if match is None:
            return normalize_raw_label(PARENTHETICAL_QUALIFIER_NORMALIZATION, None)
        return normalize_raw_label(
            PARENTHETICAL_QUALIFIER_NORMALIZATION,
            match.raw_label,
            raw_output={
                "matched_keyword": match.matched_keyword,
                "matched_field": match.matched_field,
            },
        )
