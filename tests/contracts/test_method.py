from __future__ import annotations

import math
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from gendertagger.methods.base import (
    GenderMethod,
    MethodConfig,
    MethodContractError,
    validate_prediction_batch,
)
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.method import MethodConfidenceRange, MethodDescriptor
from gendertagger.models.person import PersonInput

pytestmark = pytest.mark.contract


class _StubConfig(MethodConfig):
    label: CanonicalLabel = CanonicalLabel.unknown


class _StubMethod:
    descriptor: MethodDescriptor = MethodDescriptor(
        name="stub_method",
        implementation_version="1.0.0",
        normalization_version="stub_v1",
        method_confidence_range=MethodConfidenceRange(minimum=0.0, maximum=1.0),
    )
    config_model: type[_StubConfig] = _StubConfig

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: _StubConfig,
    ) -> list[PredictionResult]:
        return [
            PredictionResult(
                label=config.label,
                status=PredictionStatus.success,
                method_confidence=1.0,
                raw_label=person.tei_id,
            )
            for person in people
        ]


def _invoke_typed_adapter(
    method: GenderMethod[_StubConfig],
    people: list[PersonInput],
) -> list[PredictionResult]:
    config = method.config_model.model_validate({})
    predictions = method.predict_batch(people, config)
    return validate_prediction_batch(method.descriptor, people, predictions)


def test_method_descriptor_serializes_minimal_provenance_contract() -> None:
    descriptor = MethodDescriptor(
        name="gender_guesser",
        implementation_version="2.1.0",
        normalization_version="gender_guesser_v1",
        method_confidence_range=MethodConfidenceRange(minimum=0.0, maximum=1.0),
    )

    assert descriptor.model_dump(mode="json") == {
        "name": "gender_guesser",
        "implementation_version": "2.1.0",
        "normalization_version": "gender_guesser_v1",
        "method_confidence_range": {"minimum": 0.0, "maximum": 1.0},
    }


@pytest.mark.parametrize(
    "name",
    ["GenderGuesser", "gender-guesser", "_gender_guesser", "gender__guesser", "gender ", ""],
)
def test_method_descriptor_rejects_unstable_names(name: str) -> None:
    with pytest.raises(ValidationError):
        MethodDescriptor(
            name=name,
            implementation_version="1",
            normalization_version="v1",
        )


@pytest.mark.parametrize("field", ["implementation_version", "normalization_version"])
@pytest.mark.parametrize("value", ["", " ", "\t"])
def test_method_descriptor_rejects_blank_versions(field: str, value: str) -> None:
    payload = {
        "name": "example",
        "implementation_version": "1",
        "normalization_version": "v1",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        MethodDescriptor.model_validate(payload)


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [
        (0.0, 0.0),
        (1.0, 0.0),
        (math.nan, 1.0),
        (0.0, math.inf),
        (-math.inf, 1.0),
    ],
)
def test_method_confidence_range_requires_finite_ordered_bounds(
    minimum: float,
    maximum: float,
) -> None:
    with pytest.raises(ValidationError):
        MethodConfidenceRange(minimum=minimum, maximum=maximum)


def test_method_descriptor_and_confidence_range_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MethodDescriptor.model_validate(
            {
                "name": "example",
                "implementation_version": "1",
                "normalization_version": "v1",
                "resource_class": "cpu",
            }
        )

    with pytest.raises(ValidationError):
        MethodConfidenceRange.model_validate({"minimum": 0.0, "maximum": 1.0, "unit": "%"})


def test_method_config_rejects_unknown_fields_by_default() -> None:
    with pytest.raises(ValidationError):
        _StubConfig.model_validate({"threshold": 0.75})


def test_gender_method_protocol_supports_typed_config_and_ordered_results() -> None:
    people = [PersonInput(tei_id="p2"), PersonInput(tei_id="p1")]

    predictions = _invoke_typed_adapter(_StubMethod(), people)

    assert [prediction.raw_label for prediction in predictions] == ["p2", "p1"]
    assert [prediction.label for prediction in predictions] == [
        CanonicalLabel.unknown,
        CanonicalLabel.unknown,
    ]


@pytest.mark.parametrize("method_confidence", [0.0, 0.5, 1.0])
def test_prediction_batch_accepts_confidence_at_inclusive_declared_bounds(
    method_confidence: float,
) -> None:
    people = [PersonInput(tei_id="p1")]
    predictions = [
        PredictionResult(
            label=CanonicalLabel.female,
            status=PredictionStatus.success,
            method_confidence=method_confidence,
        )
    ]

    validated = validate_prediction_batch(_StubMethod.descriptor, people, predictions)

    assert validated is predictions


@pytest.mark.parametrize("prediction_count", [0, 2])
def test_prediction_batch_rejects_wrong_result_cardinality(prediction_count: int) -> None:
    people = [PersonInput(tei_id="p1")]
    predictions = [
        PredictionResult(label=None, status=PredictionStatus.abstain)
        for _ in range(prediction_count)
    ]

    with pytest.raises(MethodContractError, match=r"returned .* predictions for 1 people"):
        validate_prediction_batch(_StubMethod.descriptor, people, predictions)


@pytest.mark.parametrize("method_confidence", [-0.01, 1.01])
def test_prediction_batch_rejects_confidence_outside_declared_range(
    method_confidence: float,
) -> None:
    prediction = PredictionResult(
        label=CanonicalLabel.male,
        status=PredictionStatus.success,
        method_confidence=method_confidence,
    )

    with pytest.raises(MethodContractError, match="outside"):
        validate_prediction_batch(
            _StubMethod.descriptor,
            [PersonInput(tei_id="p1")],
            [prediction],
        )


def test_prediction_batch_rejects_confidence_without_declared_range() -> None:
    descriptor = MethodDescriptor(
        name="rule_method",
        implementation_version="1",
        normalization_version="rule_v1",
    )
    prediction = PredictionResult(
        label=CanonicalLabel.female,
        status=PredictionStatus.success,
        method_confidence=1.0,
    )

    with pytest.raises(MethodContractError, match="without declaring a range"):
        validate_prediction_batch(descriptor, [PersonInput(tei_id="p1")], [prediction])


def test_prediction_batch_accepts_record_level_error_results() -> None:
    prediction = PredictionResult(
        label=None,
        status=PredictionStatus.error,
        raw_output={"error_type": "invalid_input"},
    )

    validated = validate_prediction_batch(
        _StubMethod.descriptor,
        [PersonInput(tei_id="p1")],
        [prediction],
    )

    assert validated == [prediction]
