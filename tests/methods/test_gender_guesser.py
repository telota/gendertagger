from __future__ import annotations

import pytest

from gendertagger.methods.adapters.gender_guesser import (
    GenderGuesserConfig,
    GenderGuesserMethod,
)
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.person import PersonInput

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_CONFIG = GenderGuesserConfig()


class _FakeDetector:
    """Deterministic stand-in for the ``gender-guesser`` detector."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping
        self.calls: list[str] = []

    def get_gender(self, name: str) -> str:
        self.calls.append(name)
        return self._mapping.get(name, "unknown")


def _method(mapping: dict[str, str]) -> GenderGuesserMethod:
    detector = _FakeDetector(mapping)
    return GenderGuesserMethod(detector_factory=lambda: detector)


def _person(*forenames: str) -> PersonInput:
    return PersonInput(tei_id="p1", forenames=list(forenames))


def _predict(mapping: dict[str, str], person: PersonInput) -> PredictionResult:
    (result,) = _method(mapping).predict_batch([person], _CONFIG)
    return result


def test_descriptor_declares_versioned_confidence_free_method() -> None:
    descriptor = GenderGuesserMethod.descriptor
    assert descriptor.name == "gender_guesser"
    assert descriptor.implementation_version == "gender_guesser_v1"
    assert descriptor.normalization_version == "gender_guesser_v1"
    assert descriptor.method_confidence_range is None


def test_config_model_is_closed() -> None:
    with pytest.raises(ValueError, match="extra"):
        GenderGuesserConfig.model_validate({"unexpected": 1})


def test_single_definite_token_is_a_successful_label() -> None:
    result = _predict({"Karl": "male"}, _person("Karl"))
    assert result.label is CanonicalLabel.male
    assert result.status is PredictionStatus.success
    assert result.raw_label == "male"
    assert result.raw_output == {"tokens": ["Karl"], "token_results": ["male"]}


def test_leaning_label_normalizes_to_the_definite_canonical_label() -> None:
    result = _predict({"Andrea": "mostly_female"}, _person("Andrea"))
    assert result.label is CanonicalLabel.female
    assert result.raw_label == "mostly_female"


def test_disagreeing_definite_tokens_are_substantive_unknown() -> None:
    result = _predict({"Karl": "male", "Maria": "female"}, _person("Karl", "Maria"))
    assert result.status is PredictionStatus.success
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "conflict"


def test_ambiguous_andy_token_is_substantive_unknown() -> None:
    result = _predict({"Kim": "andy"}, _person("Kim"))
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "andy"


def test_forename_without_usable_tokens_abstains() -> None:
    result = _predict({}, _person("(Frau)", "von"))
    assert result.status is PredictionStatus.abstain
    assert result.label is None
    assert result.raw_label == "no_name"
    assert result.metadata["normalization_reason"] == "no_input"
    assert result.raw_output == {"tokens": [], "token_results": []}


def test_dictionary_miss_reported_as_unknown_is_substantive_unknown() -> None:
    result = _predict({}, _person("Xristophoros"))
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "unknown"


def test_predict_batch_returns_one_result_per_input_in_order() -> None:
    method = _method({"Karl": "male", "Maria": "female"})
    people = [_person("Karl"), _person(), _person("Maria")]
    results = method.predict_batch(people, _CONFIG)
    assert [result.label for result in results] == [
        CanonicalLabel.male,
        None,
        CanonicalLabel.female,
    ]


def test_detector_is_built_once_and_reused_across_batches() -> None:
    built = 0

    def factory() -> _FakeDetector:
        nonlocal built
        built += 1
        return _FakeDetector({"Karl": "male"})

    method = GenderGuesserMethod(detector_factory=factory)
    method.predict_batch([_person("Karl")], _CONFIG)
    method.predict_batch([_person("Karl")], _CONFIG)
    assert built == 1
