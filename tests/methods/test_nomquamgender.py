from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import pytest

from gendertagger.methods.name_tokens import NO_NAME_LABEL
from gendertagger.methods.nomquamgender import (
    NomquamgenderConfig,
    NomquamgenderMethod,
    classify,
)
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.person import PersonInput

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_CONFIG = NomquamgenderConfig()


class _FakeAnnotator:
    """Returns ``nomquamgender``-shaped rows from a name -> p(gf) mapping."""

    def __init__(self, mapping: dict[str, float | None]) -> None:
        self._mapping = mapping

    def annotate(self, names: Sequence[str]) -> list[list[Any]]:
        rows: list[list[Any]] = []
        for name in names:
            pgf = self._mapping.get(name, math.nan)
            rows.append([name, name.lower(), 0, 0, pgf])
        return rows


def _method(mapping: dict[str, float | None]) -> NomquamgenderMethod:
    return NomquamgenderMethod(annotator_factory=lambda: _FakeAnnotator(mapping))


def _person(*forenames: str) -> PersonInput:
    return PersonInput(tei_id="p1", forenames=list(forenames))


def _predict(
    mapping: dict[str, float | None],
    person: PersonInput,
    config: NomquamgenderConfig = _CONFIG,
) -> PredictionResult:
    (result,) = _method(mapping).predict_batch([person], config)
    return result


def test_descriptor_declares_versioned_confidence_free_method() -> None:
    descriptor = NomquamgenderMethod.descriptor
    assert descriptor.name == "nomquamgender"
    assert descriptor.implementation_version == "nomquamgender_v1"
    assert descriptor.normalization_version == "nomquamgender_v1"
    assert descriptor.method_confidence_range is None


def test_default_threshold_is_the_reference_value() -> None:
    assert NomquamgenderConfig().threshold == 0.1


@pytest.mark.parametrize("threshold", [0.0, 0.5, 0.6, -0.1])
def test_threshold_outside_the_open_zero_half_range_is_rejected(threshold: float) -> None:
    with pytest.raises(ValueError, match="threshold"):
        NomquamgenderConfig.model_validate({"threshold": threshold})


@pytest.mark.parametrize(
    ("pgf", "expected"),
    [
        (0.0, "male"),
        (0.1, "male"),
        (0.9, "female"),
        (1.0, "female"),
        (0.5, "uncertain"),
        (0.11, "uncertain"),
        (None, "unknown"),
    ],
)
def test_classify_thresholds_probability_into_a_label(pgf: float | None, expected: str) -> None:
    assert classify(pgf, 0.1) == expected


def test_low_probability_token_is_male() -> None:
    result = _predict({"Karl": 0.02}, _person("Karl"))
    assert result.label is CanonicalLabel.male
    assert result.raw_label == "male"
    assert result.raw_output == {
        "tokens": ["Karl"],
        "pgf": [0.02],
        "token_results": ["male"],
    }


def test_high_probability_token_is_female() -> None:
    result = _predict({"Maria": 0.97}, _person("Maria"))
    assert result.label is CanonicalLabel.female
    assert result.raw_label == "female"


def test_mid_probability_token_is_substantive_unknown() -> None:
    result = _predict({"Kim": 0.5}, _person("Kim"))
    assert result.status is PredictionStatus.success
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "uncertain"


def test_unseen_token_probability_is_unknown() -> None:
    result = _predict({}, _person("Xristophoros"))
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "unknown"
    # A NaN probability is preserved as null in the raw output.
    assert result.raw_output["pgf"] == [None]


def test_disagreeing_definite_tokens_are_conflict_unknown() -> None:
    result = _predict({"Karl": 0.0, "Maria": 1.0}, _person("Karl", "Maria"))
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "conflict"


def test_forename_without_usable_tokens_abstains() -> None:
    result = _predict({}, _person("(Frau)"))
    assert result.status is PredictionStatus.abstain
    assert result.raw_label == NO_NAME_LABEL
    assert result.raw_output == {"tokens": [], "pgf": [], "token_results": []}


def test_threshold_widens_the_definite_bands() -> None:
    # p(gf)=0.85 is uncertain at the reference threshold but female at 0.2.
    assert _predict({"Andrea": 0.85}, _person("Andrea")).label is CanonicalLabel.unknown
    wide = _predict({"Andrea": 0.85}, _person("Andrea"), NomquamgenderConfig(threshold=0.2))
    assert wide.label is CanonicalLabel.female


def test_predict_batch_returns_one_result_per_input_in_order() -> None:
    method = _method({"Karl": 0.0, "Maria": 1.0})
    results = method.predict_batch([_person("Karl"), _person(), _person("Maria")], _CONFIG)
    assert [result.label for result in results] == [
        CanonicalLabel.male,
        None,
        CanonicalLabel.female,
    ]


def test_annotator_is_built_once() -> None:
    built = 0

    def factory() -> _FakeAnnotator:
        nonlocal built
        built += 1
        return _FakeAnnotator({"Karl": 0.0})

    method = NomquamgenderMethod(annotator_factory=factory)
    method.predict_batch([_person("Karl")], _CONFIG)
    method.predict_batch([_person("Karl")], _CONFIG)
    assert built == 1


# --- Real backend: nomquamgender model ----------------------------------------


def test_real_backend_classifies_common_names() -> None:
    method = NomquamgenderMethod()
    (male,) = method.predict_batch([_person("Karl")], _CONFIG)
    assert male.label is CanonicalLabel.male
    (female,) = method.predict_batch([_person("Maria")], _CONFIG)
    assert female.label is CanonicalLabel.female
