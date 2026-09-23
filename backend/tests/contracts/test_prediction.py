from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    LlmSelfReportedCertainty,
    PredictionResult,
    PredictionStatus,
)

pytestmark = pytest.mark.contract


@pytest.mark.scientific
def test_classification_enums_expose_exact_member_and_value_mappings() -> None:
    assert {name: member.value for name, member in CanonicalLabel.__members__.items()} == {
        "male": "male",
        "female": "female",
        "unknown": "unknown",
        "institution": "institution",
    }
    assert {name: member.value for name, member in PredictionStatus.__members__.items()} == {
        "success": "success",
        "abstain": "abstain",
        "error": "error",
    }
    assert {name: member.value for name, member in CertaintyTier.__members__.items()} == {
        "high": "high",
        "low": "low",
        "contested": "contested",
        "single": "single",
        "uncertain": "uncertain",
        "no_data": "no_data",
    }
    assert {name: member.value for name, member in AgreementTier.__members__.items()} == {
        "unanimous": "unanimous",
        "strong_majority": "strong_majority",
        "weak_majority": "weak_majority",
        "no_consensus": "no_consensus",
        "single_rater": "single_rater",
        "no_answer": "no_answer",
    }
    assert {
        name: member.value for name, member in LlmSelfReportedCertainty.__members__.items()
    } == {
        "high": "high",
        "low": "low",
        "uncertain": "uncertain",
    }


@pytest.mark.parametrize("label", list(CanonicalLabel))
@pytest.mark.scientific
def test_prediction_result_success_accepts_every_canonical_label(label: CanonicalLabel) -> None:
    result = PredictionResult(label=label, status=PredictionStatus.success)

    assert result.label is label


@pytest.mark.scientific
def test_prediction_result_serialization_distinguishes_unknown_abstain_and_error() -> None:
    substantive_unknown = PredictionResult(
        label=CanonicalLabel.unknown,
        status=PredictionStatus.success,
    )
    abstention = PredictionResult(label=None, status=PredictionStatus.abstain)
    technical_error = PredictionResult(label=None, status=PredictionStatus.error)

    assert substantive_unknown.model_dump(mode="json") == {
        "label": "unknown",
        "status": "success",
        "method_confidence": None,
        "raw_label": None,
        "raw_output": {},
        "metadata": {},
    }
    assert abstention.model_dump(mode="json") == {
        "label": None,
        "status": "abstain",
        "method_confidence": None,
        "raw_label": None,
        "raw_output": {},
        "metadata": {},
    }
    assert technical_error.model_dump(mode="json") == {
        "label": None,
        "status": "error",
        "method_confidence": None,
        "raw_label": None,
        "raw_output": {},
        "metadata": {},
    }


@pytest.mark.parametrize("status", [PredictionStatus.abstain, PredictionStatus.error])
@pytest.mark.parametrize("label", list(CanonicalLabel))
@pytest.mark.scientific
def test_prediction_result_rejects_labels_for_non_success_statuses(
    status: PredictionStatus,
    label: CanonicalLabel,
) -> None:
    with pytest.raises(ValidationError):
        PredictionResult(label=label, status=status)


@pytest.mark.scientific
def test_prediction_result_rejects_success_without_label() -> None:
    with pytest.raises(ValidationError):
        PredictionResult(label=None, status=PredictionStatus.success)


def test_prediction_result_requires_label_and_status() -> None:
    with pytest.raises(ValidationError):
        PredictionResult.model_validate({"status": "abstain"})

    with pytest.raises(ValidationError):
        PredictionResult.model_validate({"label": None})


def test_prediction_result_round_trip_preserves_method_specific_evidence() -> None:
    result = PredictionResult(
        label=CanonicalLabel.female,
        status=PredictionStatus.success,
        method_confidence=1.25,
        raw_label="mostly_female",
        raw_output={"tokens": ["Anne", "Marie"], "scores": {"female": 0.81}},
        metadata={"normalization_version": "gender_guesser_v1", "cache_hit": False},
    )

    restored = PredictionResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.method_confidence == 1.25


def test_prediction_result_error_round_trip_preserves_diagnostics() -> None:
    result = PredictionResult(
        label=None,
        status=PredictionStatus.error,
        raw_label="timeout",
        raw_output={"exception_type": "TimeoutError", "attempts": 3},
        metadata={"adapter_version": "local_llm_v1", "retryable": True},
    )

    restored = PredictionResult.model_validate_json(result.model_dump_json())

    assert restored == result


def test_prediction_result_uses_isolated_evidence_defaults() -> None:
    first = PredictionResult(label=None, status=PredictionStatus.abstain)
    second = PredictionResult(label=None, status=PredictionStatus.abstain)

    first.raw_output["reason"] = "no usable forename"
    first.metadata["input_field"] = "forenames"

    assert second.raw_output == {}
    assert second.metadata == {}


@pytest.mark.parametrize("method_confidence", [math.nan, math.inf, -math.inf])
def test_prediction_result_rejects_non_finite_method_confidence(
    method_confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        PredictionResult(
            label=CanonicalLabel.male,
            status=PredictionStatus.success,
            method_confidence=method_confidence,
        )


def test_prediction_result_rejects_noncanonical_labels_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PredictionResult.model_validate({"label": "organisation", "status": "success"})

    with pytest.raises(ValidationError):
        PredictionResult.model_validate({"label": None, "status": "abstain", "confidence": 0.5})

    legacy_raw = PredictionResult(
        label=CanonicalLabel.institution,
        status=PredictionStatus.success,
        raw_label="organisation",
    )
    assert legacy_raw.raw_label == "organisation"


@pytest.mark.parametrize(
    "payload",
    [
        {"label": "Male", "status": "success"},
        {"label": None, "status": "Abstain"},
    ],
)
def test_prediction_result_rejects_wrong_case_enum_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PredictionResult.model_validate(payload)


def test_prediction_result_json_schema_exposes_stable_public_shape() -> None:
    schema = PredictionResult.model_json_schema()

    assert set(schema["properties"]) == {
        "label",
        "status",
        "method_confidence",
        "raw_label",
        "raw_output",
        "metadata",
    }
    assert schema["required"] == ["label", "status"]
    assert schema["additionalProperties"] is False
