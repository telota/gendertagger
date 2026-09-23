from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from gendertagger.models.aggregation import (
    AggregationOutcome,
    OverrideSource,
    ReferenceAggregationDecision,
    ReferenceAggregationResult,
    ResultMethodPrediction,
    VoteCounts,
)
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    PredictionResult,
    PredictionStatus,
)

pytestmark = pytest.mark.contract


def test_aggregation_enums_expose_exact_public_values() -> None:
    assert {name: member.value for name, member in AggregationOutcome.__members__.items()} == {
        "decided": "decided",
        "unresolved_tie": "unresolved_tie",
        "no_data": "no_data",
    }
    assert {name: member.value for name, member in OverrideSource.__members__.items()} == {
        "parenthetical_qualifier": "parenthetical_qualifier",
        "gnd": "gnd",
    }


def test_vote_counts_expose_complete_fixed_label_shape() -> None:
    counts = VoteCounts(male=2, female=1, unknown=3, institution=4)

    assert counts.total == 10
    assert {label: counts.for_label(label) for label in CanonicalLabel} == {
        CanonicalLabel.male: 2,
        CanonicalLabel.female: 1,
        CanonicalLabel.unknown: 3,
        CanonicalLabel.institution: 4,
    }
    assert counts.model_dump(mode="json") == {
        "male": 2,
        "female": 1,
        "unknown": 3,
        "institution": 4,
    }


def test_reference_aggregation_decision_serializes_override_evidence() -> None:
    decision = ReferenceAggregationDecision(
        outcome=AggregationOutcome.decided,
        label=CanonicalLabel.female,
        pooled_vote_counts=VoteCounts(male=1, female=2, unknown=1),
        override_source=OverrideSource.gnd,
        override_agreeing_count=2,
        override_comparison_count=4,
    )

    assert decision.model_dump(mode="json") == {
        "outcome": "decided",
        "label": "female",
        "pooled_vote_counts": {
            "male": 1,
            "female": 2,
            "unknown": 1,
            "institution": 0,
        },
        "tied_labels": [],
        "override_source": "gnd",
        "override_agreeing_count": 2,
        "override_comparison_count": 4,
    }


def test_reference_aggregation_decision_serializes_transparent_tie() -> None:
    decision = ReferenceAggregationDecision(
        outcome=AggregationOutcome.unresolved_tie,
        label=None,
        pooled_vote_counts=VoteCounts(male=2, female=2, unknown=1),
        tied_labels=(CanonicalLabel.male, CanonicalLabel.female),
    )

    assert decision.model_dump(mode="json")["tied_labels"] == ["male", "female"]
    assert decision.label is None


@pytest.mark.parametrize(
    "payload",
    [
        {"outcome": "decided", "label": None},
        {"outcome": "decided", "label": "male", "tied_labels": ["male", "female"]},
        {"outcome": "decided", "label": "male"},
        {"outcome": "unresolved_tie", "label": "unknown", "tied_labels": ["male", "female"]},
        {"outcome": "unresolved_tie", "label": None, "tied_labels": ["male"]},
        {
            "outcome": "unresolved_tie",
            "label": None,
            "tied_labels": ["male", "female"],
        },
        {
            "outcome": "unresolved_tie",
            "label": None,
            "pooled_vote_counts": {"male": 1, "female": 1},
            "tied_labels": ["male", "male"],
        },
        {"outcome": "no_data", "label": None, "pooled_vote_counts": {"male": 1}},
        {"outcome": "no_data", "label": None, "override_source": "gnd"},
        {"outcome": "no_data", "label": None, "tied_labels": ["male", "female"]},
    ],
)
def test_reference_aggregation_decision_rejects_inconsistent_outcomes(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ReferenceAggregationDecision.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "outcome": "decided",
            "label": "male",
            "pooled_vote_counts": {"male": 1},
            "override_agreeing_count": 1,
            "override_comparison_count": 1,
        },
        {
            "outcome": "decided",
            "label": "male",
            "override_source": "gnd",
        },
        {
            "outcome": "decided",
            "label": "male",
            "override_source": "gnd",
            "override_agreeing_count": 2,
            "override_comparison_count": 1,
        },
    ],
)
def test_reference_aggregation_decision_rejects_inconsistent_override_support(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ReferenceAggregationDecision.model_validate(payload)


def test_reference_aggregation_decision_accepts_unsupported_override() -> None:
    decision = ReferenceAggregationDecision(
        outcome=AggregationOutcome.decided,
        label=CanonicalLabel.institution,
        override_source=OverrideSource.parenthetical_qualifier,
        override_agreeing_count=0,
        override_comparison_count=0,
    )

    assert decision.override_agreeing_count == 0
    assert decision.override_comparison_count == 0


def test_aggregation_contracts_reject_unknown_fields_and_negative_counts() -> None:
    with pytest.raises(ValidationError):
        VoteCounts.model_validate({"male": -1})

    with pytest.raises(ValidationError):
        ReferenceAggregationDecision.model_validate(
            {"outcome": "no_data", "label": None, "agreement": 1.0}
        )


def test_reference_aggregation_json_schema_exposes_stable_shape() -> None:
    schema = ReferenceAggregationDecision.model_json_schema()

    assert set(schema["properties"]) == {
        "outcome",
        "label",
        "pooled_vote_counts",
        "tied_labels",
        "override_source",
        "override_agreeing_count",
        "override_comparison_count",
    }
    assert schema["required"] == ["outcome", "label"]
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["VoteCounts"]["additionalProperties"] is False


def test_reference_aggregation_result_serializes_assessment() -> None:
    result = ReferenceAggregationResult(
        outcome=AggregationOutcome.decided,
        label=CanonicalLabel.female,
        pooled_vote_counts=VoteCounts(male=1, female=2),
        agreement_score=0.667,
        agreement_tier=AgreementTier.weak_majority,
        certainty_tier=CertaintyTier.low,
    )

    assert result.model_dump(mode="json") == {
        "outcome": "decided",
        "label": "female",
        "pooled_vote_counts": {
            "male": 1,
            "female": 2,
            "unknown": 0,
            "institution": 0,
        },
        "tied_labels": [],
        "override_source": None,
        "override_agreeing_count": None,
        "override_comparison_count": None,
        "agreement_score": 0.667,
        "agreement_tier": "weak_majority",
        "certainty_tier": "low",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "outcome": "no_data",
            "label": None,
            "agreement_score": 0.0,
            "agreement_tier": "no_answer",
            "certainty_tier": "no_data",
        },
        {
            "outcome": "no_data",
            "label": None,
            "agreement_score": None,
            "agreement_tier": "single_rater",
            "certainty_tier": "no_data",
        },
        {
            "outcome": "no_data",
            "label": None,
            "agreement_score": None,
            "agreement_tier": "no_answer",
            "certainty_tier": "uncertain",
        },
        {
            "outcome": "decided",
            "label": "male",
            "pooled_vote_counts": {"male": 1},
            "agreement_score": None,
            "agreement_tier": "unanimous",
            "certainty_tier": "high",
        },
        {
            "outcome": "decided",
            "label": "male",
            "pooled_vote_counts": {"male": 1},
            "agreement_score": 1.0,
            "agreement_tier": "no_answer",
            "certainty_tier": "uncertain",
        },
        {
            "outcome": "unresolved_tie",
            "label": None,
            "pooled_vote_counts": {"male": 1, "female": 1},
            "tied_labels": ["male", "female"],
            "agreement_score": 0.5,
            "agreement_tier": "weak_majority",
            "certainty_tier": "contested",
        },
        {
            "outcome": "unresolved_tie",
            "label": None,
            "pooled_vote_counts": {"male": 1, "female": 1},
            "tied_labels": ["male", "female"],
            "agreement_score": 0.5,
            "agreement_tier": "no_consensus",
            "certainty_tier": "low",
        },
        {
            "outcome": "decided",
            "label": "male",
            "override_source": "gnd",
            "override_agreeing_count": 0,
            "override_comparison_count": 0,
            "agreement_score": 1.0,
            "agreement_tier": "single_rater",
            "certainty_tier": "low",
        },
    ],
)
def test_reference_aggregation_result_rejects_inconsistent_assessment(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ReferenceAggregationResult.model_validate(payload)


def test_reference_aggregation_result_rejects_invalid_score() -> None:
    with pytest.raises(ValidationError):
        ReferenceAggregationResult.model_validate(
            {
                "outcome": "decided",
                "label": "male",
                "pooled_vote_counts": {"male": 1},
                "agreement_score": 1.01,
                "agreement_tier": "unanimous",
                "certainty_tier": "high",
            }
        )


def test_result_method_prediction_keeps_absence_distinct_from_abstention() -> None:
    execution_id = UUID("20000000-0000-0000-0000-000000000001")
    absent = ResultMethodPrediction(
        method_execution_id=execution_id,
        method_name="gnd",
        implementation_version="1",
        normalization_version="1",
    )
    abstained = ResultMethodPrediction(
        method_execution_id=execution_id,
        method_name="gnd",
        implementation_version="1",
        normalization_version="1",
        prediction_id=UUID("30000000-0000-0000-0000-000000000001"),
        prediction=PredictionResult(label=None, status=PredictionStatus.abstain),
    )

    assert absent.prediction is None
    assert abstained.prediction is not None
    assert abstained.prediction.status is PredictionStatus.abstain
    with pytest.raises(ValidationError, match="present together"):
        ResultMethodPrediction(
            method_execution_id=execution_id,
            method_name="gnd",
            implementation_version="1",
            normalization_version="1",
            prediction_id=UUID("30000000-0000-0000-0000-000000000001"),
        )
