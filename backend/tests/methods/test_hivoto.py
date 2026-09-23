from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from gendertagger.methods.adapters.hivoto import (
    HivotoConfig,
    HivotoMethod,
    SqliteHivotoLookup,
    build_hivoto_index,
    compile_hivoto_lookup,
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

_LOOKUP_SHA256 = "a" * 64
_CONFIG = HivotoConfig(lookup_sha256=_LOOKUP_SHA256)


class _Resolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def materialize(self, logical_type: str, sha256: str) -> Path:
        self.calls.append((logical_type, sha256))
        return Path("/verified/hivoto.sqlite3")


class _Lookup:
    def __init__(self, index: dict[str, tuple[str, str]]) -> None:
        self._index = index

    def get_many(self, names: Sequence[str]) -> dict[str, tuple[str, str]]:
        return {name: self._index[name] for name in names if name in self._index}


def _method(index: dict[str, tuple[str, str]]) -> HivotoMethod:
    return HivotoMethod(
        lookup_asset_resolver=_Resolver(),
        lookup_factory=lambda _path: _Lookup(index),
    )


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


def test_config_requires_a_lookup_digest_and_forbids_paths() -> None:
    with pytest.raises(ValueError, match="lookup_sha256"):
        HivotoConfig.model_validate({})
    with pytest.raises(ValueError, match="extra"):
        HivotoConfig.model_validate(
            {"lookup_sha256": _LOOKUP_SHA256, "dataset_path": "/mutable/hivoto.csv"}
        )


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


def test_lookup_is_materialized_and_opened_once_per_digest() -> None:
    resolver = _Resolver()
    built: list[Path] = []

    def factory(path: Path) -> _Lookup:
        built.append(path)
        return _Lookup({"karl": ("male", "sicher")})

    method = HivotoMethod(lookup_asset_resolver=resolver, lookup_factory=factory)
    method.predict_batch([_person("Karl")], _CONFIG)
    method.predict_batch([_person("Karl")], _CONFIG)

    assert resolver.calls == [("hivoto_lookup", _LOOKUP_SHA256)]
    assert built == [Path("/verified/hivoto.sqlite3")]


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
    index = build_hivoto_index(snapshot)

    assert index["karl"] == ("male", "sicher")
    assert index["maria"] == ("female", "sicher")
    assert index["kim"] == ("female", "mittlere Sicherheit")


def test_compiled_sqlite_lookup_preserves_the_frozen_index(tmp_path: Path) -> None:
    source = tmp_path / "hivoto.csv"
    source.write_text(
        "Originalschreibung;Klassifizierte_Originalschreibung;"
        "Namensgeschlecht;Sicherheit_Geschlechtszuordnung\n"
        "Karl;Karl;männlich (Q6581097);sicher\n"
        "Maria;Maria.;weiblich (Q17);sicher\n",
        encoding="utf-8",
    )
    lookup_path = tmp_path / "hivoto.sqlite3"

    record_count = compile_hivoto_lookup(
        source,
        lookup_path,
        source_sha256="f" * 64,
        source_version="1.0.0",
    )
    lookup = SqliteHivotoLookup(lookup_path)

    assert record_count == 2
    assert lookup.get_many(["maria", "missing", "karl"]) == {
        "karl": ("male", "sicher"),
        "maria": ("female", "sicher"),
    }


def test_hivoto_compiler_rejects_missing_required_columns(tmp_path: Path) -> None:
    source = tmp_path / "hivoto.csv"
    source.write_text("name;gender\nKarl;male\n", encoding="utf-8")

    with pytest.raises(ValueError, match="lacks required columns"):
        compile_hivoto_lookup(
            source,
            tmp_path / "lookup.sqlite3",
            source_sha256="f" * 64,
        )
