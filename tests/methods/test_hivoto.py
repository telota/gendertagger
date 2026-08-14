from __future__ import annotations

from pathlib import Path

import pytest

from gendertagger.methods.hivoto import (
    HivotoConfig,
    HivotoMethod,
    build_hivoto_index,
    map_gender,
)
from gendertagger.methods.name_tokens import NO_NAME_LABEL
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.person import PersonInput

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_CONFIG = HivotoConfig(dataset_path="/snapshots/hivoto.csv")


def _method(index: dict[str, tuple[str, str]]) -> HivotoMethod:
    return HivotoMethod(index_factory=lambda _path: index)


def _person(*forenames: str) -> PersonInput:
    return PersonInput(tei_id="p1", forenames=list(forenames))


def _predict(index: dict[str, tuple[str, str]], person: PersonInput) -> PredictionResult:
    (result,) = _method(index).predict_batch([person], _CONFIG)
    return result


def test_descriptor_declares_versioned_confidence_free_method() -> None:
    descriptor = HivotoMethod.descriptor
    assert descriptor.name == "hivoto"
    assert descriptor.implementation_version == "hivoto_v1"
    assert descriptor.normalization_version == "hivoto_v1"
    assert descriptor.method_confidence_range is None


def test_config_requires_a_dataset_path() -> None:
    with pytest.raises(ValueError, match="dataset_path"):
        HivotoConfig.model_validate({})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("männlich (Q6581097)", "male"),
        ("weiblich (Q17)", "female"),
        ("männlich, vorwiegend", "mostly_male"),
        ("weiblich, vorwiegend", "mostly_female"),
        ("uneindeutig (Q369534)", "andy"),
        ("", "unknown"),
        ("etwas anderes", "unknown"),
    ],
)
def test_map_gender_ports_the_reference_label_mapping(raw: str, expected: str) -> None:
    assert map_gender(raw) == expected


def test_token_key_is_lowercased_and_trailing_punctuation_stripped() -> None:
    result = _predict({"karl": ("male", "sicher")}, _person("Karl."))
    assert result.label is CanonicalLabel.male
    assert result.raw_output["token_results"] == ["male"]
    assert result.raw_output["certainties"] == ["sicher"]


def test_leaning_label_normalizes_to_the_definite_canonical_label() -> None:
    result = _predict({"andrea": ("mostly_female", "mittlere Sicherheit")}, _person("Andrea"))
    assert result.label is CanonicalLabel.female
    assert result.raw_label == "mostly_female"


def test_ambiguous_token_is_substantive_unknown() -> None:
    result = _predict({"kim": ("andy", "mittlere Sicherheit")}, _person("Kim"))
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "andy"


def test_disagreeing_definite_tokens_are_conflict_unknown() -> None:
    index = {"karl": ("male", "sicher"), "maria": ("female", "sicher")}
    result = _predict(index, _person("Karl", "Maria"))
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "conflict"


def test_token_missing_from_the_index_is_unknown() -> None:
    result = _predict({}, _person("Xristophoros"))
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "unknown"


def test_forename_without_usable_tokens_abstains() -> None:
    result = _predict({}, _person("(Frau)"))
    assert result.status is PredictionStatus.abstain
    assert result.raw_label == NO_NAME_LABEL
    assert result.raw_output == {"tokens": [], "token_results": [], "certainties": []}


def test_predict_batch_returns_one_result_per_input_in_order() -> None:
    method = _method({"karl": ("male", "sicher"), "maria": ("female", "sicher")})
    results = method.predict_batch([_person("Karl"), _person(), _person("Maria")], _CONFIG)
    assert [result.label for result in results] == [
        CanonicalLabel.male,
        None,
        CanonicalLabel.female,
    ]


def test_index_is_built_once_per_dataset_path() -> None:
    built: list[str] = []

    def factory(path: str) -> dict[str, tuple[str, str]]:
        built.append(path)
        return {"karl": ("male", "sicher")}

    method = HivotoMethod(index_factory=factory)
    method.predict_batch([_person("Karl")], _CONFIG)
    method.predict_batch([_person("Karl")], _CONFIG)
    assert built == ["/snapshots/hivoto.csv"]


def test_build_index_aggregates_by_majority_vote_and_certainty(tmp_path: Path) -> None:
    snapshot = tmp_path / "hivoto.csv"
    snapshot.write_text(
        "Originalschreibung;Klassifizierte_Originalschreibung;"
        "Namensgeschlecht;Sicherheit_Geschlechtszuordnung\n"
        "Karl;Karl;männlich (Q6581097);sicher\n"
        "Maria;Maria.;weiblich (Q17);sicher\n"
        "Kim;Kim;männlich (Q6581097);sicher\n"
        "Kim;Kim;weiblich (Q17);mittlere Sicherheit\n",
        encoding="utf-8",
    )
    index = build_hivoto_index(str(snapshot))

    assert index["karl"] == ("male", "sicher")
    # The classified spelling "Maria." is keyed without its trailing period.
    assert index["maria"] == ("female", "sicher")
    # A 1-1 male/female tie is broken by the index priority (female outranks male),
    # and mixed certainties collapse to "mittlere Sicherheit".
    assert index["kim"] == ("female", "mittlere Sicherheit")
