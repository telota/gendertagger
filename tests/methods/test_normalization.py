from __future__ import annotations

from collections.abc import Mapping

import pytest

from gendertagger.methods.normalization import (
    GND_NORMALIZATION,
    NORMALIZATION_PROFILES,
    LabelNormalizationProfile,
    NormalizationReason,
    normalize_raw_label,
)
from gendertagger.models.classification import CanonicalLabel, PredictionStatus

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_EXPECTED_MAPPINGS: Mapping[str, Mapping[str, CanonicalLabel]] = {
    "parenthetical_qualifier": {
        "female": CanonicalLabel.female,
        "male": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
    "gnd": {
        "female": CanonicalLabel.female,
        "institution": CanonicalLabel.institution,
        "male": CanonicalLabel.male,
        "männlich": CanonicalLabel.male,
        "organisation": CanonicalLabel.institution,
        "unbekannt": CanonicalLabel.unknown,
        "unknown": CanonicalLabel.unknown,
        "weiblich": CanonicalLabel.female,
    },
    "gender_guesser": {
        "andy": CanonicalLabel.unknown,
        "conflict": CanonicalLabel.unknown,
        "female": CanonicalLabel.female,
        "male": CanonicalLabel.male,
        "mostly_female": CanonicalLabel.female,
        "mostly_male": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
    "wiki_gendersort": {
        "conflict": CanonicalLabel.unknown,
        "f": CanonicalLabel.female,
        "female": CanonicalLabel.female,
        "m": CanonicalLabel.male,
        "male": CanonicalLabel.male,
        "uni": CanonicalLabel.unknown,
        "unisex": CanonicalLabel.unknown,
        "unk": CanonicalLabel.unknown,
        "unknown": CanonicalLabel.unknown,
    },
    "hivoto": {
        "andy": CanonicalLabel.unknown,
        "conflict": CanonicalLabel.unknown,
        "female": CanonicalLabel.female,
        "male": CanonicalLabel.male,
        "mostly_female": CanonicalLabel.female,
        "mostly_male": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
    "nomquamgender": {
        "conflict": CanonicalLabel.unknown,
        "female": CanonicalLabel.female,
        "male": CanonicalLabel.male,
        "uncertain": CanonicalLabel.unknown,
        "unknown": CanonicalLabel.unknown,
    },
    "hf_distilbert": {
        "0": CanonicalLabel.male,
        "1": CanonicalLabel.female,
        "conflict": CanonicalLabel.unknown,
        "female": CanonicalLabel.female,
        "label_0": CanonicalLabel.male,
        "label_1": CanonicalLabel.female,
        "male": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
    "hf_genderize": {
        "0": CanonicalLabel.female,
        "1": CanonicalLabel.male,
        "conflict": CanonicalLabel.unknown,
        "female": CanonicalLabel.female,
        "label_0": CanonicalLabel.female,
        "label_1": CanonicalLabel.male,
        "male": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
    "local_llm": {
        "female": CanonicalLabel.female,
        "institution": CanonicalLabel.institution,
        "male": CanonicalLabel.male,
        "organisation": CanonicalLabel.institution,
        "unknown": CanonicalLabel.unknown,
    },
    "hivoto_xgboost": {
        "andy": CanonicalLabel.unknown,
        "conflict": CanonicalLabel.unknown,
        "female": CanonicalLabel.female,
        "male": CanonicalLabel.male,
        "mostly_female": CanonicalLabel.female,
        "mostly_male": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
}


def test_normalization_registry_contains_exact_versioned_method_profiles() -> None:
    assert {
        method_name: profile.normalization_version
        for method_name, profile in NORMALIZATION_PROFILES.items()
    } == {
        "parenthetical_qualifier": "parenthetical_qualifier_v1",
        "gnd": "gnd_v1",
        "gender_guesser": "gender_guesser_v1",
        "wiki_gendersort": "wiki_gendersort_v1",
        "hivoto": "hivoto_v1",
        "nomquamgender": "nomquamgender_v1",
        "hf_distilbert": "hf_distilbert_v1",
        "hf_genderize": "hf_genderize_v1",
        "local_llm": "local_llm_v1",
        "hivoto_xgboost": "hivoto_xgboost_v1",
    }


@pytest.mark.parametrize(
    "method_name",
    list(_EXPECTED_MAPPINGS),
)
def test_normalization_profiles_expose_exact_scientific_mappings(method_name: str) -> None:
    profile = NORMALIZATION_PROFILES[method_name]

    assert dict(profile.label_map) == _EXPECTED_MAPPINGS[method_name]

    for raw_label, expected_label in _EXPECTED_MAPPINGS[method_name].items():
        result = normalize_raw_label(profile, raw_label)
        assert result.label is expected_label
        assert result.status is PredictionStatus.success
        assert result.raw_label == raw_label
        assert result.metadata == {
            "normalization_version": profile.normalization_version,
            "normalization_reason": NormalizationReason.mapped.value,
        }


@pytest.mark.parametrize(
    "raw_label",
    [None, "", "  ", "nan", "no_answer", "no_gnd", "no_name"],
)
@pytest.mark.parametrize(
    "profile", list(NORMALIZATION_PROFILES.values()), ids=lambda item: item.method_name
)
def test_normalization_profiles_abstain_for_missing_or_no_input(
    profile: LabelNormalizationProfile,
    raw_label: str | None,
) -> None:
    result = normalize_raw_label(profile, raw_label)

    assert result.label is None
    assert result.status is PredictionStatus.abstain
    expected_reason = (
        NormalizationReason.missing_raw_label if raw_label is None else NormalizationReason.no_input
    )
    assert result.metadata["normalization_reason"] == expected_reason.value


@pytest.mark.parametrize(
    "profile", list(NORMALIZATION_PROFILES.values()), ids=lambda item: item.method_name
)
def test_normalization_profiles_preserve_explicit_technical_errors(
    profile: LabelNormalizationProfile,
) -> None:
    result = normalize_raw_label(profile, "error", raw_output={"http_status": 404})

    assert result.label is None
    assert result.status is PredictionStatus.error
    assert result.raw_label == "error"
    assert result.raw_output == {"http_status": 404}
    assert result.metadata["normalization_reason"] == NormalizationReason.technical_error.value


@pytest.mark.parametrize(
    "profile", list(NORMALIZATION_PROFILES.values()), ids=lambda item: item.method_name
)
def test_normalization_profiles_abstain_for_unparseable_labels(
    profile: LabelNormalizationProfile,
) -> None:
    result = normalize_raw_label(profile, "schema_drift_label")

    assert result.label is None
    assert result.status is PredictionStatus.abstain
    assert result.raw_label == "schema_drift_label"
    assert result.metadata["normalization_reason"] == NormalizationReason.unparseable.value


def test_normalization_compares_casefolded_stripped_label_but_preserves_raw_value() -> None:
    raw_label = "  MÄNNLICH  "

    result = normalize_raw_label(GND_NORMALIZATION, raw_label)

    assert result.label is CanonicalLabel.male
    assert result.status is PredictionStatus.success
    assert result.raw_label == raw_label


def test_substantive_unknown_remains_distinct_from_abstention() -> None:
    substantive_unknown = normalize_raw_label(GND_NORMALIZATION, "Unbekannt")
    abstention = normalize_raw_label(GND_NORMALIZATION, "no_gnd")

    assert substantive_unknown.label is CanonicalLabel.unknown
    assert substantive_unknown.status is PredictionStatus.success
    assert abstention.label is None
    assert abstention.status is PredictionStatus.abstain


def test_normalization_preserves_confidence_and_copies_supplied_evidence() -> None:
    raw_output = {"native_label": "UNI"}
    metadata = {
        "dataset_revision": "2026-08",
        "normalization_version": "caller_must_not_override",
        "normalization_reason": "caller_must_not_override",
    }
    profile = NORMALIZATION_PROFILES["wiki_gendersort"]

    result = normalize_raw_label(
        profile,
        "UNI",
        method_confidence=0.5,
        raw_output=raw_output,
        metadata=metadata,
    )
    raw_output["native_label"] = "changed"
    metadata["dataset_revision"] = "changed"

    assert result.method_confidence == 0.5
    assert result.raw_output == {"native_label": "UNI"}
    assert result.metadata == {
        "dataset_revision": "2026-08",
        "normalization_version": "wiki_gendersort_v1",
        "normalization_reason": NormalizationReason.mapped.value,
    }


@pytest.mark.parametrize("key", ["Male", " male"])
def test_normalization_profile_rejects_noncanonical_keys(key: str) -> None:
    with pytest.raises(ValueError, match="must be stripped and case-folded"):
        LabelNormalizationProfile(
            method_name="bad",
            normalization_version="v1",
            label_map={key: CanonicalLabel.male},
        )


@pytest.mark.parametrize(("method_name", "normalization_version"), [("", "v1"), ("x", " ")])
def test_normalization_profile_rejects_blank_identity(
    method_name: str,
    normalization_version: str,
) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        LabelNormalizationProfile(
            method_name=method_name,
            normalization_version=normalization_version,
            label_map={"male": CanonicalLabel.male},
        )


def test_normalization_profile_rejects_overlapping_outcomes() -> None:
    with pytest.raises(ValueError, match="outcomes overlap"):
        LabelNormalizationProfile(
            method_name="bad",
            normalization_version="v1",
            label_map={"unknown": CanonicalLabel.unknown},
            abstain_labels=frozenset({"unknown"}),
        )
