from __future__ import annotations

from pathlib import Path

import pytest

from gendertagger.methods.base import MethodDependencyError
from gendertagger.methods.wiki_gendersort import (
    WikiGendersortConfig,
    WikiGendersortMethod,
)
from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.person import PersonInput

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_CONFIG = WikiGendersortConfig(names_db_path="/snapshots/NamesOut.txt")


class _FakeAssigner:
    """Dictionary-backed stand-in for the Wiki-Gendersort name table."""

    def __init__(self, mapping: dict[str, tuple[str, str | None]]) -> None:
        self._mapping = mapping

    def assign(self, name: str) -> tuple[str, str | None]:
        return self._mapping.get(name, ("UNK", None))


def _method(mapping: dict[str, tuple[str, str | None]]) -> WikiGendersortMethod:
    return WikiGendersortMethod(assigner_factory=lambda _path: _FakeAssigner(mapping))


def _person(*forenames: str) -> PersonInput:
    return PersonInput(tei_id="p1", forenames=list(forenames))


def _predict(mapping: dict[str, tuple[str, str | None]], person: PersonInput) -> PredictionResult:
    (result,) = _method(mapping).predict_batch([person], _CONFIG)
    return result


def test_descriptor_declares_versioned_confidence_free_method() -> None:
    descriptor = WikiGendersortMethod.descriptor
    assert descriptor.name == "wiki_gendersort"
    assert descriptor.implementation_version == "wiki_gendersort_v1"
    assert descriptor.normalization_version == "wiki_gendersort_v1"
    assert descriptor.method_confidence_range is None


def test_config_requires_a_names_db_path() -> None:
    with pytest.raises(ValueError, match="names_db_path"):
        WikiGendersortConfig.model_validate({})
    with pytest.raises(ValueError, match="extra"):
        WikiGendersortConfig.model_validate({"names_db_path": "x", "unexpected": 1})


def test_native_male_and_female_labels_map_to_canonical_labels() -> None:
    male = _predict({"Karl": ("M", "Karl")}, _person("Karl"))
    assert male.label is CanonicalLabel.male
    assert male.raw_label == "male"
    assert male.raw_output["native_labels"] == ["M"]
    assert male.raw_output["matched_names"] == ["Karl"]

    female = _predict({"Maria": ("F", "Maria")}, _person("Maria"))
    assert female.label is CanonicalLabel.female


def test_unisex_native_label_is_substantive_unknown() -> None:
    result = _predict({"Kim": ("UNI", "Kim")}, _person("Kim"))
    assert result.status is PredictionStatus.success
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "unisex"


def test_unknown_native_label_is_substantive_unknown() -> None:
    result = _predict({"Xy": ("UNK", None)}, _person("Xy"))
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "unknown"


def test_initials_only_token_abstains_through_the_no_name_label() -> None:
    result = _predict({"J": ("INI", None)}, _person("J"))
    assert result.status is PredictionStatus.abstain
    assert result.label is None
    assert result.raw_label == "no_name"


def test_disagreeing_definite_tokens_are_conflict_unknown() -> None:
    result = _predict(
        {"Karl": ("M", "Karl"), "Maria": ("F", "Maria")},
        _person("Karl", "Maria"),
    )
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "conflict"


def test_forename_without_usable_tokens_abstains() -> None:
    result = _predict({}, _person("(Frau)"))
    assert result.status is PredictionStatus.abstain
    assert result.raw_label == "no_name"
    assert result.raw_output == {
        "tokens": [],
        "native_labels": [],
        "token_results": [],
        "matched_names": [],
    }


def test_predict_batch_returns_one_result_per_input_in_order() -> None:
    method = _method({"Karl": ("M", "Karl"), "Maria": ("F", "Maria")})
    results = method.predict_batch([_person("Karl"), _person(), _person("Maria")], _CONFIG)
    assert [result.label for result in results] == [
        CanonicalLabel.male,
        None,
        CanonicalLabel.female,
    ]


def test_assigner_is_built_once_per_snapshot_path() -> None:
    built: list[str] = []

    def factory(path: str) -> _FakeAssigner:
        built.append(path)
        return _FakeAssigner({"Karl": ("M", "Karl")})

    method = WikiGendersortMethod(assigner_factory=factory)
    method.predict_batch([_person("Karl")], _CONFIG)
    method.predict_batch([_person("Karl")], _CONFIG)
    assert built == ["/snapshots/NamesOut.txt"]


def test_missing_dependency_is_a_permanent_failure() -> None:
    def factory(_path: str) -> _FakeAssigner:
        msg = "wiki_gendersort requires the 'wiki' extra"
        raise MethodDependencyError(msg)

    method = WikiGendersortMethod(assigner_factory=factory)
    with pytest.raises(MethodDependencyError):
        method.predict_batch([_person("Karl")], _CONFIG)


# --- Real backend: nameclean and table lookup (require the wiki extra) --------


def test_clean_name_ports_the_reference_candidate_generation() -> None:
    unidecode_module = pytest.importorskip("unidecode")
    from gendertagger.methods.wiki_gendersort import _clean_name

    transliterate = unidecode_module.unidecode
    assert _clean_name("Anna", transliterate) == ["Anna"]
    assert _clean_name("J.", transliterate) == []
    assert _clean_name("Jean-Paul", transliterate) == ["Jean-paul", "Jean", "Paul"]
    # A transliterated variant is appended when it differs from the normalized form.
    assert _clean_name("Élise", transliterate) == ["Élise", "Elise"]


def test_table_assign_resolves_tokens_against_a_local_snapshot(tmp_path: Path) -> None:
    pytest.importorskip("unidecode")
    from gendertagger.methods.wiki_gendersort import WikiGendersortTable

    snapshot = tmp_path / "NamesOut.txt"
    snapshot.write_text("Karl\tM\nMaria\tF\nKim\tUNI\n", encoding="utf-8")
    table = WikiGendersortTable(str(snapshot))

    assert table.assign("Karl") == ("M", "Karl")
    assert table.assign("maria") == ("F", "Maria")
    assert table.assign("Kim") == ("UNI", "Kim")
    assert table.assign("Unlisted") == ("UNK", None)
    assert table.assign("J.") == ("INI", None)


def test_adapter_end_to_end_over_a_local_snapshot(tmp_path: Path) -> None:
    pytest.importorskip("unidecode")

    snapshot = tmp_path / "NamesOut.txt"
    snapshot.write_text("Karl\tM\nMaria\tF\n", encoding="utf-8")
    method = WikiGendersortMethod()
    config = WikiGendersortConfig(names_db_path=str(snapshot))

    (male,) = method.predict_batch([_person("Karl")], config)
    assert male.label is CanonicalLabel.male
    (female,) = method.predict_batch([_person("Maria")], config)
    assert female.label is CanonicalLabel.female
