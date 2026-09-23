from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from gendertagger.methods.adapters.hf_genderize import (
    HF_GENDERIZE_MODEL_FILE_LOGICAL_TYPE,
    HF_GENDERIZE_MODEL_MANIFEST_LOGICAL_TYPE,
    HfGenderizeConfig,
    HfGenderizeMethod,
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
_CONFIG = HfGenderizeConfig(lookup_sha256=_LOOKUP_SHA256)
_MODEL_DIRECTORY = Path("/verified/hf-genderize-model")


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
        return _MODEL_DIRECTORY


class _Backend:
    def __init__(self, indices_by_token: dict[str, int]) -> None:
        self._indices_by_token = indices_by_token
        self.batches: list[list[str]] = []

    def classify_many(self, names: Sequence[str]) -> list[int]:
        self.batches.append(list(names))
        return [self._indices_by_token[name] for name in names]


def _method(indices_by_token: dict[str, int]) -> tuple[HfGenderizeMethod, _Resolver, _Backend]:
    resolver = _Resolver()
    backend = _Backend(indices_by_token)
    method = HfGenderizeMethod(
        model_directory_resolver=resolver,
        backend_factory=lambda _directory: backend,
    )
    return method, resolver, backend


def _person(*forenames: str) -> PersonInput:
    return PersonInput(tei_id="p1", forenames=list(forenames))


def _predict(indices_by_token: dict[str, int], person: PersonInput) -> PredictionResult:
    method, _, _ = _method(indices_by_token)
    (result,) = method.predict_batch([person], _CONFIG)
    return result


def test_descriptor_declares_versioned_confidence_free_method() -> None:
    descriptor = HfGenderizeMethod.descriptor
    assert descriptor.name == "hf_genderize"
    assert descriptor.implementation_version == "hf_genderize_v1"
    assert descriptor.normalization_version == "hf_genderize_v1"
    assert descriptor.method_confidence_range is None


def test_config_requires_a_lookup_digest_and_forbids_extra_fields() -> None:
    with pytest.raises(ValueError, match="lookup_sha256"):
        HfGenderizeConfig.model_validate({})
    with pytest.raises(ValueError, match="extra"):
        HfGenderizeConfig.model_validate(
            {"lookup_sha256": _LOOKUP_SHA256, "model": "imranali291/genderize"}
        )


def test_index_zero_is_female_and_index_one_is_male() -> None:
    female_result = _predict({"Maria": 0}, _person("Maria"))
    assert female_result.label is CanonicalLabel.female
    assert female_result.raw_label == "female"

    male_result = _predict({"Karl": 1}, _person("Karl"))
    assert male_result.label is CanonicalLabel.male
    assert male_result.raw_label == "male"


def test_index_polarity_is_inverted_relative_to_distilbert() -> None:
    # The same index means the opposite label across the two HF adapters.
    result = _predict({"Alex": 0}, _person("Alex"))
    assert result.label is CanonicalLabel.female


def test_disagreeing_tokens_are_conflict_unknown() -> None:
    result = _predict({"Karl": 1, "Maria": 0}, _person("Karl", "Maria"))
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "conflict"
    assert result.status is PredictionStatus.success


def test_forename_without_usable_tokens_abstains() -> None:
    result = _predict({}, _person("(Frau)"))
    assert result.status is PredictionStatus.abstain
    assert result.raw_label == NO_NAME_LABEL
    assert result.raw_output == {"tokens": [], "token_results": []}


def test_predict_batch_returns_one_result_per_input_in_order() -> None:
    method, _, _ = _method({"Karl": 1, "Maria": 0})
    results = method.predict_batch([_person("Karl"), _person(), _person("Maria")], _CONFIG)
    assert [result.label for result in results] == [
        CanonicalLabel.male,
        None,
        CanonicalLabel.female,
    ]


def test_backend_is_materialized_and_loaded_once_per_digest() -> None:
    method, resolver, backend = _method({"Karl": 1})

    method.predict_batch([_person("Karl")], _CONFIG)
    method.predict_batch([_person("Karl")], _CONFIG)

    assert resolver.calls == [
        (
            HF_GENDERIZE_MODEL_MANIFEST_LOGICAL_TYPE,
            HF_GENDERIZE_MODEL_FILE_LOGICAL_TYPE,
            _LOOKUP_SHA256,
            "hf_genderize",
        )
    ]
    assert backend.batches == [["Karl"], ["Karl"]]
