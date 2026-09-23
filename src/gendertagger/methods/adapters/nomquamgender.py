"""Adapter for the ``nomquamgender`` statistical first-name classifier.

The adapter tokenizes each person's forename with the shared name-token filter,
annotates each token with ``nomquamgender`` to obtain a female-probability
``p(gf)``, thresholds each probability into a categorical label, and reduces the
per-token labels by the method's priority consensus. The raw label is
normalized against the frozen ``nomquamgender_v1`` profile. See ADR-0019.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any, Final, Protocol, cast

from pydantic import Field

from gendertagger.methods.base import MethodConfig
from gendertagger.methods.name_tokens import consensus_label, usable_forename_tokens
from gendertagger.methods.normalization import NOMQUAMGENDER_NORMALIZATION, normalize_raw_label
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput

_DEFAULT_THRESHOLD: Final = 0.1
_PRIORITY: Final[tuple[str, ...]] = ("no_name", "unknown", "uncertain", "male", "female")
_MALE_LABELS: Final[frozenset[str]] = frozenset({"male"})
_FEMALE_LABELS: Final[frozenset[str]] = frozenset({"female"})
_PGF_INDEX: Final = 4


class NomquamgenderConfig(MethodConfig):
    """Resolved configuration for the ``nomquamgender`` probability threshold."""

    threshold: float = Field(
        default=_DEFAULT_THRESHOLD,
        gt=0.0,
        lt=0.5,
        allow_inf_nan=False,
        description=(
            "Female-probability decision margin: p(gf) <= threshold is male, "
            ">= 1 - threshold is female, otherwise uncertain. The reference value is 0.1."
        ),
    )


class NomquamAnnotator(Protocol):
    """Structural contract for the ``nomquamgender`` annotator used per batch."""

    def annotate(self, names: Sequence[str]) -> Sequence[Sequence[Any]]:
        """Return one ``nomquamgender`` annotation row per input name in order."""
        ...


AnnotatorFactory = Callable[[], NomquamAnnotator]


def _default_annotator_factory() -> NomquamAnnotator:
    import nomquamgender

    # The dependency's annotation exposes a DataFrame-or-list union even though
    # ``as_df=False`` (the default used here) returns the list rows this adapter
    # consumes. Keep that incomplete third-party typing at this boundary.
    return cast(NomquamAnnotator, nomquamgender.NBGC())


def _pgf_value(row: Sequence[Any]) -> float | None:
    """Extract the female probability from one annotation row, ``None`` if absent."""
    probability = row[_PGF_INDEX]
    if probability is None:
        return None
    value = float(probability)
    return None if math.isnan(value) else value


def classify(pgf: float | None, threshold: float) -> str:
    """Map a female probability to a categorical label at the given threshold."""
    if pgf is None:
        return "unknown"
    if pgf <= threshold:
        return "male"
    if pgf >= 1 - threshold:
        return "female"
    return "uncertain"


class NomquamgenderMethod:
    """Structural :class:`~gendertagger.methods.base.GenderMethod` implementation."""

    descriptor = MethodDescriptor(
        name="nomquamgender",
        implementation_version="nomquamgender_v1",
        normalization_version=NOMQUAMGENDER_NORMALIZATION.normalization_version,
    )
    config_model = NomquamgenderConfig

    def __init__(self, annotator_factory: AnnotatorFactory | None = None) -> None:
        self._annotator_factory = annotator_factory or _default_annotator_factory
        self._annotator: NomquamAnnotator | None = None

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: NomquamgenderConfig,
    ) -> list[PredictionResult]:
        """Classify each person from its forename tokens in input order."""
        annotator = self._get_annotator()
        return [self._predict_one(annotator, person, config.threshold) for person in people]

    def _get_annotator(self) -> NomquamAnnotator:
        if self._annotator is None:
            self._annotator = self._annotator_factory()
        return self._annotator

    @staticmethod
    def _predict_one(
        annotator: NomquamAnnotator, person: PersonInput, threshold: float
    ) -> PredictionResult:
        tokens = usable_forename_tokens(person.forenames)
        pgf_values: list[float | None] = []
        token_results: list[str] = []
        if tokens:
            pgf_values = [_pgf_value(row) for row in annotator.annotate(tokens)]
            token_results = [classify(pgf, threshold) for pgf in pgf_values]
        raw_label = consensus_label(
            token_results,
            priority=_PRIORITY,
            male_labels=_MALE_LABELS,
            female_labels=_FEMALE_LABELS,
        )
        return normalize_raw_label(
            NOMQUAMGENDER_NORMALIZATION,
            raw_label,
            raw_output={
                "tokens": tokens,
                "pgf": pgf_values,
                "token_results": token_results,
            },
        )
