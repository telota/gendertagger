"""Adapter for the ``gender-guesser`` first-name dictionary classifier.

The adapter tokenizes each person's forename with the shared name-token filter,
looks up every token in the ``gender-guesser`` dictionary, and reduces the
per-token labels to one raw label by the method's priority consensus. The raw
label is normalized against the frozen ``gender_guesser_v1`` profile so raw
evidence and canonical outcome stay separable. See ADR-0012.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final, Protocol

from gendertagger.methods.base import MethodConfig
from gendertagger.methods.name_tokens import consensus_label, usable_forename_tokens
from gendertagger.methods.normalization import GENDER_GUESSER_NORMALIZATION, normalize_raw_label
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput

# Priority from weakest to strongest signal; a definite label outranks a leaning
# one, which outranks the ambiguous outcomes. Ported verbatim from the reference
# pipeline.
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


class GenderGuesserConfig(MethodConfig):
    """Closed configuration for the ``gender-guesser`` adapter (no parameters)."""


class GenderGuesserDetector(Protocol):
    """Structural contract for the ``gender-guesser`` detector used per token."""

    def get_gender(self, name: str) -> str:
        """Return the dictionary label for one first-name token."""
        ...


DetectorFactory = Callable[[], GenderGuesserDetector]


def _default_detector_factory() -> GenderGuesserDetector:
    from gender_guesser.detector import Detector

    # Case-insensitive lookup reproduces the reference pipeline's detector setup.
    detector: GenderGuesserDetector = Detector(case_sensitive=False)
    return detector


class GenderGuesserMethod:
    """Structural :class:`~gendertagger.methods.base.GenderMethod` implementation."""

    descriptor = MethodDescriptor(
        name="gender_guesser",
        implementation_version="gender_guesser_v1",
        normalization_version=GENDER_GUESSER_NORMALIZATION.normalization_version,
    )
    config_model = GenderGuesserConfig

    def __init__(self, detector_factory: DetectorFactory | None = None) -> None:
        self._detector_factory = detector_factory or _default_detector_factory
        self._detector: GenderGuesserDetector | None = None

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: GenderGuesserConfig,
    ) -> list[PredictionResult]:
        """Classify each person from its forename tokens in input order."""
        del config  # The dictionary lookup takes no resolved configuration.
        detector = self._get_detector()
        return [self._predict_one(detector, person) for person in people]

    def _get_detector(self) -> GenderGuesserDetector:
        if self._detector is None:
            self._detector = self._detector_factory()
        return self._detector

    @staticmethod
    def _predict_one(detector: GenderGuesserDetector, person: PersonInput) -> PredictionResult:
        tokens = usable_forename_tokens(person.forenames)
        token_results = [detector.get_gender(token) for token in tokens]
        raw_label = consensus_label(
            token_results,
            priority=_PRIORITY,
            male_labels=_MALE_LABELS,
            female_labels=_FEMALE_LABELS,
        )
        return normalize_raw_label(
            GENDER_GUESSER_NORMALIZATION,
            raw_label,
            raw_output={"tokens": tokens, "token_results": token_results},
        )
