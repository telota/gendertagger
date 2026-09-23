from __future__ import annotations

from pathlib import Path
from typing import Literal, TypeVar

import pytest
from pydantic import BaseModel, ConfigDict

from gendertagger.domain.aggregation_assessment import assess_reference_predictions
from gendertagger.methods.normalization import NORMALIZATION_PROFILES, normalize_raw_label
from gendertagger.models.aggregation import OverrideSource, ReferenceAggregationResult
from gendertagger.models.classification import (
    CanonicalLabel,
    CertaintyTier,
    LlmSelfReportedCertainty,
    PredictionResult,
    PredictionStatus,
)

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "scientific"
_LEGACY_FIXTURE_PATH = _FIXTURE_DIR / "legacy_characterization.json"
_REFERENCE_FIXTURE_PATH = _FIXTURE_DIR / "reference_v1.json"


class _ClosedFixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _LegacySource(_ClosedFixtureModel):
    repository_commit: str
    aggregator_blob: str
    sha256: dict[str, str]


class _RedistributionApproval(_ClosedFixtureModel):
    approved_on: str
    scope: Literal["tei_id_and_method_outputs_only"]
    excluded_fields: tuple[str, ...]


class _LegacyAggregation(_ClosedFixtureModel):
    label: CanonicalLabel
    answering_count: int
    agreement_score: float
    certainty_tier: CertaintyTier


class _LegacyRecord(_ClosedFixtureModel):
    case: str
    tei_id: str
    raw_labels: dict[str, str | None]
    local_llm_self_reported_certainty: LlmSelfReportedCertainty
    expected_aggregation: _LegacyAggregation


class _LegacyFixture(_ClosedFixtureModel):
    schema_version: Literal[1]
    oracle: Literal["legacy_characterization"]
    description: str
    source: _LegacySource
    redistribution_approval: _RedistributionApproval
    records: tuple[_LegacyRecord, ...]


class _ExpectedPrediction(_ClosedFixtureModel):
    label: CanonicalLabel | None
    status: PredictionStatus


class _ReferenceDifference(_ClosedFixtureModel):
    tei_id: str
    field: str
    legacy: str
    reference_v1: str
    decision: str


class _ReferenceRecord(_ClosedFixtureModel):
    case: str
    tei_id: str
    expected_predictions: dict[str, _ExpectedPrediction]
    expected_aggregation: ReferenceAggregationResult


class _ReferenceFixture(_ClosedFixtureModel):
    schema_version: Literal[1]
    oracle: Literal["reference_v1"]
    strategy: Literal["reference_v1"]
    source_oracle: Literal["legacy_characterization.json"]
    normalization_versions: dict[str, str]
    expected_differences: tuple[_ReferenceDifference, ...]
    records: tuple[_ReferenceRecord, ...]


_FixtureT = TypeVar("_FixtureT", bound=BaseModel)


def _load_fixture(path: Path, model: type[_FixtureT]) -> _FixtureT:
    return model.model_validate_json(path.read_text(encoding="utf-8"))


_LEGACY_FIXTURE = _load_fixture(_LEGACY_FIXTURE_PATH, _LegacyFixture)
_REFERENCE_FIXTURE = _load_fixture(_REFERENCE_FIXTURE_PATH, _ReferenceFixture)
_REFERENCE_RECORDS = {record.tei_id: record for record in _REFERENCE_FIXTURE.records}

_EXPECTED_CASES = {
    "S0010005": "unanimous_pooled_vote",
    "S1083217": "parenthetical_unknown_override",
    "S1122134": "parenthetical_institution_override_against_pooled_vote",
    "S1619063": "parenthetical_institution_reinforces_llm",
    "S8945539": "gnd_override_against_female_majority",
    "S1125482": "unknown_tie_loses_to_substantive_label",
    "S1125426": "lone_high_certainty_llm_institution",
    "S0001049": "lone_uncertain_llm_unknown",
    "S7944779": "leaning_and_ambiguous_normalization",
    "S0002324": "explicit_gnd_error",
}
_EXPECTED_SOURCE_FILES = {
    "data/input/schleiermacher_persons.csv",
    "data/output/gender_summary.csv",
    "data/results/gender_guesser_results.csv",
    "data/results/gnd_gender_results.csv",
    "data/results/hf_gender_classification_results.csv",
    "data/results/hf_genderize_results.csv",
    "data/results/hivoto_results.csv",
    "data/results/hivoto_xgboost_results.csv",
    "data/results/llm_gender_results.csv",
    "data/results/nqg_results.csv",
    "data/results/wiki_gendersort_results.csv",
}


def test_legacy_characterization_has_approved_minimal_provenance() -> None:
    assert _LEGACY_FIXTURE.source.repository_commit == "36522b8"
    assert _LEGACY_FIXTURE.source.aggregator_blob == "9046e867fec577804ce72ddacae4881f07e9fc35"
    assert set(_LEGACY_FIXTURE.source.sha256) == _EXPECTED_SOURCE_FILES
    assert all(
        len(checksum) == 64
        and checksum == checksum.lower()
        and set(checksum) <= set("0123456789abcdef")
        for checksum in _LEGACY_FIXTURE.source.sha256.values()
    )
    assert _LEGACY_FIXTURE.redistribution_approval.approved_on == "2026-08-13"
    assert set(_LEGACY_FIXTURE.redistribution_approval.excluded_fields) == {
        "surname",
        "forenames",
        "birth",
        "death",
        "note",
        "alt_names",
        "llm_reasoning",
    }
    assert {record.tei_id: record.case for record in _LEGACY_FIXTURE.records} == _EXPECTED_CASES


def test_reference_oracle_is_paired_with_legacy_cases_and_runtime_versions() -> None:
    assert {record.tei_id: record.case for record in _REFERENCE_FIXTURE.records} == _EXPECTED_CASES
    assert _REFERENCE_FIXTURE.normalization_versions == {
        method_name: profile.normalization_version
        for method_name, profile in NORMALIZATION_PROFILES.items()
    }
    for record in _LEGACY_FIXTURE.records:
        assert set(record.raw_labels) == set(NORMALIZATION_PROFILES)
        assert set(_REFERENCE_RECORDS[record.tei_id].expected_predictions) == set(
            NORMALIZATION_PROFILES
        )


@pytest.mark.parametrize(
    "legacy_record",
    _LEGACY_FIXTURE.records,
    ids=lambda record: record.case,
)
def test_reference_v1_golden_raw_labels_through_final_result(
    legacy_record: _LegacyRecord,
) -> None:
    reference_record = _REFERENCE_RECORDS[legacy_record.tei_id]
    predictions: dict[str, PredictionResult] = {}

    for method_name, raw_label in legacy_record.raw_labels.items():
        metadata = (
            {"self_reported_certainty": (legacy_record.local_llm_self_reported_certainty.value)}
            if method_name == "local_llm"
            else {}
        )
        prediction = normalize_raw_label(
            NORMALIZATION_PROFILES[method_name],
            raw_label,
            metadata=metadata,
        )
        expected_prediction = reference_record.expected_predictions[method_name]

        assert prediction.label is expected_prediction.label
        assert prediction.status is expected_prediction.status
        assert prediction.raw_label == raw_label
        predictions[method_name] = prediction

    result = assess_reference_predictions(predictions)

    assert result == reference_record.expected_aggregation
    assert result.label is legacy_record.expected_aggregation.label
    assert _legacy_answering_count(result) == legacy_record.expected_aggregation.answering_count
    assert result.agreement_score == legacy_record.expected_aggregation.agreement_score
    assert result.certainty_tier is legacy_record.expected_aggregation.certainty_tier


def test_reference_oracle_records_every_difference_from_legacy() -> None:
    assert [
        difference.model_dump(mode="json") for difference in _REFERENCE_FIXTURE.expected_differences
    ] == [
        {
            "tei_id": "S0002324",
            "field": "predictions.gnd.status",
            "legacy": "no_vote_after_unknown_fallback",
            "reference_v1": "error",
            "decision": "ADR-0007",
        }
    ]
    legacy_record = next(
        record for record in _LEGACY_FIXTURE.records if record.tei_id == "S0002324"
    )
    reference_record = _REFERENCE_RECORDS[legacy_record.tei_id]

    assert legacy_record.raw_labels["gnd"] == "error"
    assert reference_record.expected_predictions["gnd"].label is None
    assert reference_record.expected_predictions["gnd"].status is PredictionStatus.error


def _legacy_answering_count(result: ReferenceAggregationResult) -> int:
    if result.override_source is OverrideSource.parenthetical_qualifier:
        assert result.override_comparison_count is not None
        return result.override_comparison_count + 1
    if result.override_source is OverrideSource.gnd:
        return result.pooled_vote_counts.total + 1
    return result.pooled_vote_counts.total
