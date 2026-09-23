from __future__ import annotations

import pytest

from gendertagger.methods.adapters.parenthetical_qualifier import (
    ParentheticalQualifierConfig,
    ParentheticalQualifierMethod,
)
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.person import PersonInput

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_METHOD = ParentheticalQualifierMethod()
_CONFIG = ParentheticalQualifierConfig()


def _person(
    *, surname: str | None = None, forenames: list[str] | None = None, note: str | None = None
) -> PersonInput:
    return PersonInput(tei_id="p1", surname=surname, forenames=forenames or [], note=note)


def _predict(person: PersonInput) -> PredictionResult:
    (result,) = _METHOD.predict_batch([person], _CONFIG)
    return result


def test_descriptor_declares_versioned_deterministic_rule() -> None:
    descriptor = ParentheticalQualifierMethod.descriptor
    assert descriptor.name == "parenthetical_qualifier"
    assert descriptor.normalization_version == "parenthetical_qualifier_v1"
    assert descriptor.method_confidence_range is None


def test_config_model_is_closed() -> None:
    with pytest.raises(ValueError, match="extra"):
        ParentheticalQualifierConfig.model_validate({"unexpected": 1})


def test_leading_female_qualifier_in_surname_is_female() -> None:
    result = _predict(_person(surname="Frölich (Frau des Heinrich)"))
    assert result.status is PredictionStatus.success
    assert result.label is CanonicalLabel.female
    assert result.raw_label == "female"
    assert result.raw_output == {"matched_keyword": "frau", "matched_field": "surname"}
    assert result.metadata["normalization_reason"] == "mapped"


def test_leading_male_qualifier_in_forename_is_male() -> None:
    result = _predict(_person(surname="Müller", forenames=["(Sohn des Karl)"]))
    assert result.label is CanonicalLabel.male
    assert result.raw_output["matched_field"] == "forename"


def test_any_word_qualifier_matches_when_not_leading() -> None:
    result = _predict(_person(surname="Weber (erste Tochter des Paul)"))
    assert result.label is CanonicalLabel.female
    assert result.raw_output["matched_keyword"] == "tochter"


def test_family_group_qualifier_is_substantive_unknown() -> None:
    result = _predict(_person(surname="Mendelssohn (Familie des Abraham)"))
    assert result.status is PredictionStatus.success
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "unknown"


def test_organisation_qualifier_is_substantive_institution() -> None:
    result = _predict(_person(surname="Reimer (Firma in Berlin)"))
    assert result.status is PredictionStatus.success
    assert result.label is CanonicalLabel.institution
    assert result.raw_label == "institution"
    assert result.metadata["normalization_reason"] == "mapped"
    assert result.raw_output == {"matched_keyword": "firma", "matched_field": "surname"}


def test_missing_qualifier_abstains_with_no_raw_label() -> None:
    result = _predict(_person(surname="Schleiermacher", forenames=["Friedrich"]))
    assert result.status is PredictionStatus.abstain
    assert result.label is None
    assert result.raw_label is None
    assert result.metadata["normalization_reason"] == "missing_raw_label"


def test_note_is_matched_only_on_its_leading_word() -> None:
    leading = _predict(_person(surname="Anonymous", note="Nichte des Predigers"))
    assert leading.label is CanonicalLabel.female
    assert leading.raw_output["matched_field"] == "note"

    buried = _predict(_person(surname="Anonymous", note="siehe die Nichte des Predigers"))
    assert buried.status is PredictionStatus.abstain
    assert buried.raw_label is None


def test_note_never_asserts_institution() -> None:
    result = _predict(_person(surname="Anonymous", note="Firma des Kaufmanns"))
    assert result.status is PredictionStatus.abstain
    assert result.raw_label is None


def test_name_fields_take_precedence_over_note() -> None:
    result = _predict(_person(surname="Krause (Sohn des Franz)", note="Tochter des Nachbarn"))
    assert result.label is CanonicalLabel.male
    assert result.raw_output["matched_field"] == "surname"


def test_predict_batch_returns_one_result_per_input_in_order() -> None:
    people = [
        _person(surname="Frölich (Frau des Heinrich)"),
        _person(surname="Schleiermacher"),
        _person(surname="Müller (Sohn des Karl)"),
    ]
    results = _METHOD.predict_batch(people, _CONFIG)
    assert [result.label for result in results] == [
        CanonicalLabel.female,
        None,
        CanonicalLabel.male,
    ]
