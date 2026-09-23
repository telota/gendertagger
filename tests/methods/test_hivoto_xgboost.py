from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from gendertagger.methods.adapters.hivoto_xgboost import (
    HIVOTO_XGBOOST_MODEL_FILE_LOGICAL_TYPE,
    HIVOTO_XGBOOST_MODEL_MANIFEST_LOGICAL_TYPE,
    HivotoXgboostConfig,
    HivotoXgboostMethod,
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
_CONFIG = HivotoXgboostConfig(lookup_sha256=_LOOKUP_SHA256)
_DIRECTORY = Path("/verified/hivoto-xgboost-bundle")


class _Resolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []

    def materialize_directory(
        self,
        *,
        manifest_logical_type: str,
        member_logical_type: str,
        manifest_sha256: str,
        expected_method_name: str,
    ) -> Path:
        self.calls.append(
            (manifest_logical_type, member_logical_type, manifest_sha256, expected_method_name)
        )
        return _DIRECTORY


class _Lookup:
    def __init__(self, entries: dict[str, tuple[str, str]]) -> None:
        self._entries = entries
        self.queries: list[list[str]] = []

    def get_many(self, names: Sequence[str]) -> dict[str, tuple[str, str]]:
        self.queries.append(list(names))
        return {name: self._entries[name] for name in names if name in self._entries}


class _Model:
    def __init__(self, proba_by_key: dict[str, float]) -> None:
        self._proba_by_key = proba_by_key
        self.batches: list[list[str]] = []

    def predict_female_probability(self, tokens: Sequence[str]) -> list[float]:
        self.batches.append(list(tokens))
        return [self._proba_by_key[token] for token in tokens]


def _method(
    entries: dict[str, tuple[str, str]],
    proba_by_key: dict[str, float],
) -> tuple[HivotoXgboostMethod, _Resolver, _Lookup, _Model]:
    resolver = _Resolver()
    lookup = _Lookup(entries)
    model = _Model(proba_by_key)
    method = HivotoXgboostMethod(
        model_directory_resolver=resolver,
        lookup_factory=lambda _path: lookup,
        model_factory=lambda _path: model,
    )
    return method, resolver, lookup, model


def _person(*forenames: str) -> PersonInput:
    return PersonInput(tei_id="p1", forenames=list(forenames))


def _predict(
    entries: dict[str, tuple[str, str]],
    proba_by_key: dict[str, float],
    person: PersonInput,
) -> PredictionResult:
    method, _, _, _ = _method(entries, proba_by_key)
    (result,) = method.predict_batch([person], _CONFIG)
    return result


def test_descriptor_declares_versioned_confidence_free_method() -> None:
    descriptor = HivotoXgboostMethod.descriptor
    assert descriptor.name == "hivoto_xgboost"
    assert descriptor.implementation_version == "hivoto_xgboost_v1"
    assert descriptor.normalization_version == "hivoto_xgboost_v1"
    assert descriptor.method_confidence_range is None


def test_config_requires_a_lookup_digest_and_forbids_extra_fields() -> None:
    with pytest.raises(ValueError, match="lookup_sha256"):
        HivotoXgboostConfig.model_validate({})
    with pytest.raises(ValueError, match="extra"):
        HivotoXgboostConfig.model_validate(
            {"lookup_sha256": _LOOKUP_SHA256, "vectorizer": "vocabulary.json"}
        )


def test_pure_lookup_hit_wins_without_a_model_prediction() -> None:
    result = _predict({"karl": ("male", "sicher")}, {}, _person("Karl"))
    assert result.label is CanonicalLabel.male
    assert result.raw_label == "male"


def test_pure_model_fallback_uses_the_probability_threshold() -> None:
    result = _predict({}, {"maria": 0.9}, _person("Maria"))
    assert result.label is CanonicalLabel.female
    assert result.raw_label == "female"

    result = _predict({}, {"karl": 0.1}, _person("Karl"))
    assert result.label is CanonicalLabel.male
    assert result.raw_label == "male"


def test_mostly_labels_normalize_to_the_definite_canonical_label() -> None:
    result = _predict({"andrea": ("mostly_female", "mittlere Sicherheit")}, {}, _person("Andrea"))
    assert result.label is CanonicalLabel.female
    assert result.raw_output["token_results"] == ["mostly_female"]


def test_hard_votes_break_ties_by_first_token_order() -> None:
    first_male = _predict(
        {"karl": ("male", "sicher")},
        {"maria": 0.9},
        _person("Karl", "Maria"),
    )
    assert first_male.label is CanonicalLabel.male

    first_female = _predict(
        {"karl": ("male", "sicher")},
        {"maria": 0.9},
        _person("Maria", "Karl"),
    )
    assert first_female.label is CanonicalLabel.female


def test_all_andy_tokens_consensus_to_andy_which_normalizes_to_unknown() -> None:
    entries = {"kim": ("andy", "mittlere Sicherheit"), "robin": ("andy", "mittlere Sicherheit")}
    result = _predict(entries, {}, _person("Kim", "Robin"))
    assert result.raw_label == "andy"
    assert result.label is CanonicalLabel.unknown


def test_andy_and_unknown_hits_average_to_the_probability_threshold() -> None:
    # No token is a hard male/female/mostly_* vote, and not every token is
    # "andy", so the legacy reduction falls through to averaging placeholder
    # probabilities (andy=0.5, unknown-hit=0.5) and thresholds at >= 0.5.
    entries = {
        "kim": ("andy", "mittlere Sicherheit"),
        "xx": ("unbestimmt", "unsicher"),
    }
    result = _predict(entries, {}, _person("Kim", "Xx"))
    assert result.raw_label == "female"
    assert result.raw_output["token_results"] == ["andy", "unknown"]


def test_forename_without_usable_tokens_abstains() -> None:
    result = _predict({}, {}, _person("(Frau)"))
    assert result.status is PredictionStatus.abstain
    assert result.raw_label == NO_NAME_LABEL
    assert result.raw_output == {"tokens": [], "token_results": [], "token_probabilities": []}


def test_predict_batch_returns_one_result_per_input_in_order() -> None:
    method, _, _, _ = _method({"karl": ("male", "sicher")}, {"maria": 0.9})
    results = method.predict_batch([_person("Karl"), _person(), _person("Maria")], _CONFIG)
    assert [result.label for result in results] == [
        CanonicalLabel.male,
        None,
        CanonicalLabel.female,
    ]


def test_only_lookup_misses_are_sent_to_the_model() -> None:
    method, _, lookup, model = _method({"karl": ("male", "sicher")}, {"maria": 0.9})

    method.predict_batch([_person("Karl", "Maria")], _CONFIG)

    assert lookup.queries == [["karl", "maria"]]
    assert model.batches == [["maria"]]


def test_bundle_is_materialized_and_loaded_once_per_digest() -> None:
    method, resolver, _, model = _method({}, {"karl": 0.1})

    method.predict_batch([_person("Karl")], _CONFIG)
    method.predict_batch([_person("Karl")], _CONFIG)

    assert resolver.calls == [
        (
            HIVOTO_XGBOOST_MODEL_MANIFEST_LOGICAL_TYPE,
            HIVOTO_XGBOOST_MODEL_FILE_LOGICAL_TYPE,
            _LOOKUP_SHA256,
            "hivoto_xgboost",
        )
    ]
    assert model.batches == [["karl"], ["karl"]]


def test_lookup_query_key_and_model_key_normalize_independently() -> None:
    # usable_forename_tokens preserves "Karl;" verbatim (trailing punctuation
    # is only stripped for its own particle-membership check, not the
    # returned token). Lookup queries strip the broader ".,;:)\"'" set
    # (matching HivotoMethod), stripping the semicolon; the model receives
    # only period-stripped input (matching the original training
    # preprocessing), so its semicolon survives.
    method, _, lookup, model = _method({}, {"karl;": 0.2})

    method.predict_batch([_person("Karl;")], _CONFIG)

    assert lookup.queries == [["karl"]]
    assert model.batches == [["karl;"]]
