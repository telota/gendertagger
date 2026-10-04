from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, datetime
from threading import Event, Lock
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import Field, JsonValue

from gendertagger.methods.adapters.gender_guesser import GenderGuesserMethod
from gendertagger.methods.adapters.nomquamgender import NomquamgenderMethod
from gendertagger.methods.adapters.parenthetical_qualifier import ParentheticalQualifierMethod
from gendertagger.methods.base import LookupMethodConfig, MethodConfig, MethodDependencyError
from gendertagger.models.aggregation import AggregationOutcome, OverrideSource
from gendertagger.models.artifact import Artifact
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.method import MethodConfidenceRange, MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.method_registry import (
    MethodRegistration,
    MethodRegistry,
    UnknownMethodError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWork


class _StubCountingMethod:
    descriptor = MethodDescriptor(
        name="counting_method",
        implementation_version="counting_v1",
        normalization_version="counting_norm_v1",
    )
    config_model = MethodConfig

    def __init__(self) -> None:
        self.call_count = 0
        self.total_people_classified = 0

    def predict_batch(self, people: Sequence[PersonInput], config: Any) -> list[PredictionResult]:
        del config
        self.call_count += 1
        self.total_people_classified += len(people)
        return [
            PredictionResult(
                label=CanonicalLabel.female if "Maria" in p.forenames else CanonicalLabel.male,
                status=PredictionStatus.success,
                raw_label="custom",
            )
            for p in people
        ]


class _StubFailingMethod:
    descriptor = MethodDescriptor(
        name="failing_method",
        implementation_version="failing_v1",
        normalization_version="failing_norm_v1",
    )
    config_model = MethodConfig

    def predict_batch(self, people: Sequence[PersonInput], config: Any) -> list[PredictionResult]:
        del people, config
        msg = "Failing adapter dependency missing"
        raise MethodDependencyError(msg)


class _FakeNomquamAnnotator:
    def annotate(self, names: Sequence[str]) -> list[list[Any]]:
        return [[name, name.lower(), 0, 0, 0.95 if name == "Maria" else 0.05] for name in names]


def _build_test_registry(counting_method: _StubCountingMethod | None = None) -> MethodRegistry:
    registrations = [
        MethodRegistration(
            descriptor=ParentheticalQualifierMethod.descriptor,
            config_model=ParentheticalQualifierMethod.config_model,
            adapter=ParentheticalQualifierMethod(),
            queue_name="cpu",
            batch_size=100,
        ),
        MethodRegistration(
            descriptor=GenderGuesserMethod.descriptor,
            config_model=GenderGuesserMethod.config_model,
            adapter=GenderGuesserMethod(),
            queue_name="cpu",
            batch_size=100,
        ),
        MethodRegistration(
            descriptor=NomquamgenderMethod.descriptor,
            config_model=NomquamgenderMethod.config_model,
            adapter=NomquamgenderMethod(annotator_factory=_FakeNomquamAnnotator),
            queue_name="cpu",
            batch_size=100,
        ),
        MethodRegistration(
            descriptor=_StubFailingMethod.descriptor,
            config_model=_StubFailingMethod.config_model,
            adapter=_StubFailingMethod(),
            queue_name="cpu",
            batch_size=100,
        ),
    ]
    if counting_method is not None:
        registrations.append(
            MethodRegistration(
                descriptor=counting_method.descriptor,
                config_model=counting_method.config_model,
                adapter=counting_method,
                queue_name="cpu",
                batch_size=100,
            )
        )
    return MethodRegistry(registrations)


def test_classify_names_runs_registered_methods_and_returns_predictions() -> None:
    registry = _build_test_registry()
    service = DirectClassificationService(method_registry=registry)

    response = service.classify_names(
        names=["Maria", "Heinrich", "Schmidt (Frau des Heinrich)"],
        methods=["parenthetical_qualifier", "gender_guesser"],
    )

    assert len(response.results) == 3

    maria_res = response.results[0]
    assert maria_res.name == "Maria"
    assert maria_res.classifications["gender_guesser"].label == CanonicalLabel.female
    assert maria_res.classifications["gender_guesser"].status == PredictionStatus.success
    assert maria_res.classifications["parenthetical_qualifier"].label is None
    assert maria_res.classifications["parenthetical_qualifier"].status == PredictionStatus.abstain
    # Aggregated verdict for Maria
    assert maria_res.aggregated.label == CanonicalLabel.female
    assert maria_res.aggregated.outcome == AggregationOutcome.decided
    assert maria_res.aggregated.vote_counts.female == 1
    assert maria_res.aggregated.agreement_tier == AgreementTier.single_rater

    heinrich_res = response.results[1]
    assert heinrich_res.name == "Heinrich"
    assert heinrich_res.classifications["gender_guesser"].label == CanonicalLabel.male
    assert heinrich_res.classifications["gender_guesser"].status == PredictionStatus.success
    assert heinrich_res.aggregated.label == CanonicalLabel.male
    assert heinrich_res.aggregated.outcome == AggregationOutcome.decided

    frau_res = response.results[2]
    assert frau_res.name == "Schmidt (Frau des Heinrich)"
    assert frau_res.classifications["parenthetical_qualifier"].label == CanonicalLabel.female
    assert frau_res.classifications["parenthetical_qualifier"].status == PredictionStatus.success
    assert frau_res.aggregated.label == CanonicalLabel.female
    assert frau_res.aggregated.override_source == OverrideSource.parenthetical_qualifier


def test_classify_names_handles_adapter_error_gracefully() -> None:
    registry = _build_test_registry()
    service = DirectClassificationService(method_registry=registry)

    response = service.classify_names(
        names=["Maria"],
        methods=["gender_guesser", "failing_method"],
    )

    assert len(response.results) == 1
    maria_res = response.results[0]
    assert maria_res.classifications["gender_guesser"].label == CanonicalLabel.female
    assert maria_res.classifications["gender_guesser"].status == PredictionStatus.success

    failing_res = maria_res.classifications["failing_method"]
    assert failing_res.label is None
    assert failing_res.status == PredictionStatus.error
    assert failing_res.error_message is not None
    assert "Failing adapter dependency missing" in failing_res.error_message


def test_classify_names_rejects_unknown_methods() -> None:
    registry = _build_test_registry()
    service = DirectClassificationService(method_registry=registry)

    with pytest.raises(UnknownMethodError, match="method 'unknown_method' is not registered"):
        service.classify_names(names=["Maria"], methods=["unknown_method"])


def test_classify_names_with_custom_method_config() -> None:
    registry = _build_test_registry()
    service = DirectClassificationService(method_registry=registry)

    response = service.classify_names(
        names=["Maria"],
        methods=["nomquamgender"],
        method_configs={"nomquamgender": {"threshold": 0.2}},
    )

    assert len(response.results) == 1
    assert response.results[0].classifications["nomquamgender"].label == CanonicalLabel.female


def test_classify_names_lru_cache_avoids_redundant_adapter_calls() -> None:
    counter = _StubCountingMethod()
    registry = _build_test_registry(counting_method=counter)
    service = DirectClassificationService(method_registry=registry)

    # First call: 2 names
    resp1 = service.classify_names(names=["Maria", "Heinrich"], methods=["counting_method"])
    assert len(resp1.results) == 2
    assert counter.call_count == 1
    assert counter.total_people_classified == 2

    # Second call with duplicate + 1 new name
    resp2 = service.classify_names(
        names=["Maria", "Maria", "Heinrich", "Anna"], methods=["counting_method"]
    )
    assert len(resp2.results) == 4
    # Only "Anna" should have been a cache miss and executed
    assert counter.call_count == 2
    assert counter.total_people_classified == 3


class _ScriptedMethod:
    descriptor = _StubCountingMethod.descriptor
    config_model = MethodConfig

    def __init__(self, batches: Sequence[list[PredictionResult] | Exception]) -> None:
        self._batches = iter(batches)
        self.inputs: list[list[str]] = []

    def predict_batch(
        self, people: Sequence[PersonInput], config: MethodConfig
    ) -> list[PredictionResult]:
        del config
        self.inputs.append([person.forenames[0] for person in people])
        batch = next(self._batches)
        if isinstance(batch, Exception):
            raise batch
        return batch


class _CacheIdentityConfig(LookupMethodConfig):
    threshold: float = 0.5
    model_name: str = "first_model"
    options: dict[str, int] = Field(default_factory=dict)


def _cache_registry(
    adapter: _ScriptedMethod,
    *,
    descriptor: MethodDescriptor | None = None,
    config_model: type[MethodConfig] = MethodConfig,
) -> MethodRegistry:
    return MethodRegistry(
        [
            MethodRegistration(
                descriptor=descriptor or adapter.descriptor,
                config_model=config_model,
                adapter=adapter,
                queue_name="cpu",
                batch_size=100,
            )
        ]
    )


def _success_prediction() -> PredictionResult:
    return PredictionResult(
        label=CanonicalLabel.female,
        status=PredictionStatus.success,
        raw_label="female",
        raw_output={"tokens": [{"label": "female"}]},
        metadata={"normalization": {"steps": ["original"]}},
    )


@pytest.mark.parametrize(
    "failed_batch",
    [
        [
            PredictionResult(
                label=None, status=PredictionStatus.error, raw_output={"error": "offline"}
            )
        ],
        MethodDependencyError("asset unavailable"),
        RuntimeError("backend unavailable"),
        [],
        [
            PredictionResult(
                label=CanonicalLabel.female,
                status=PredictionStatus.success,
                method_confidence=0.5,
            )
        ],
    ],
    ids=["returned_error", "dependency_failure", "runtime_failure", "cardinality", "confidence"],
)
def test_classify_names_retries_technical_failure_after_recovery(
    failed_batch: list[PredictionResult] | Exception,
) -> None:
    adapter = _ScriptedMethod([failed_batch, [_success_prediction()]])
    service = DirectClassificationService(method_registry=_cache_registry(adapter))

    failed = service.classify_names(["Maria"])
    assert failed.results[0].classifications["counting_method"].status is PredictionStatus.error
    assert adapter.inputs == [["Maria"]]

    recovered = service.classify_names(["Maria"])
    hit = service.classify_names(["Maria"])
    assert recovered.results[0].classifications["counting_method"].label is CanonicalLabel.female
    assert (
        recovered.results[0].classifications["counting_method"].status is PredictionStatus.success
    )
    assert hit == recovered
    assert adapter.inputs == [["Maria"], ["Maria"]]


@pytest.mark.parametrize(
    ("status", "label"),
    [
        (PredictionStatus.success, CanonicalLabel.female),
        (PredictionStatus.success, CanonicalLabel.unknown),
        (PredictionStatus.abstain, None),
    ],
)
def test_classify_names_caches_scientific_outcomes(
    status: PredictionStatus, label: CanonicalLabel | None
) -> None:
    adapter = _ScriptedMethod([[PredictionResult(status=status, label=label)]])
    service = DirectClassificationService(method_registry=_cache_registry(adapter))

    first = service.classify_names(["Maria"])
    assert service.classify_names(["Maria"]) == first
    assert first.results[0].classifications["counting_method"].status is status
    assert first.results[0].classifications["counting_method"].label is label
    assert adapter.inputs == [["Maria"]]


def test_classify_names_retries_only_errors_in_mixed_cached_batch() -> None:
    adapter = _ScriptedMethod(
        [
            [
                _success_prediction(),
                PredictionResult(label=None, status=PredictionStatus.error),
                PredictionResult(label=CanonicalLabel.unknown, status=PredictionStatus.success),
                PredictionResult(label=None, status=PredictionStatus.abstain),
            ],
            [_success_prediction()],
        ]
    )
    service = DirectClassificationService(method_registry=_cache_registry(adapter))
    names = ["Maria", "Anna", "Unresolved", "Excluded"]

    first = service.classify_names(names)
    second = service.classify_names(names)
    assert adapter.inputs == [names, ["Anna"]]
    assert second.results[1].classifications["counting_method"].status is PredictionStatus.success
    assert second.results[0] == first.results[0]
    assert second.results[2:] == first.results[2:]


def test_classify_names_cache_deep_copies_adapter_and_returned_evidence() -> None:
    prediction = _success_prediction()
    adapter = _ScriptedMethod([[prediction]])
    service = DirectClassificationService(method_registry=_cache_registry(adapter))

    _, first_evidence = service.classify_names_with_evidence(["Maria"])
    prediction.raw_output["tokens"][0]["label"] = "male"
    first_evidence[0]["counting_method"].metadata["normalization"]["steps"].append("mutated")
    _, hit_evidence = service.classify_names_with_evidence(["Maria", "Maria"])
    assert hit_evidence[0]["counting_method"] == _success_prediction()
    assert hit_evidence[1]["counting_method"] == _success_prediction()

    hit_evidence[0]["counting_method"].raw_output["tokens"].clear()
    hit_evidence[0]["counting_method"].metadata["normalization"]["steps"].clear()
    assert hit_evidence[1]["counting_method"] == _success_prediction()
    _, later_evidence = service.classify_names_with_evidence(["Maria"])
    assert later_evidence[0]["counting_method"] == _success_prediction()
    assert adapter.inputs == [["Maria"]]


def test_classify_names_errors_do_not_evict_and_hits_refresh_lru_recency() -> None:
    adapter = _ScriptedMethod(
        [
            [_success_prediction(), _success_prediction()],
            [PredictionResult(label=None, status=PredictionStatus.error)],
            [_success_prediction()],
            [_success_prediction()],
        ]
    )
    service = DirectClassificationService(
        method_registry=_cache_registry(adapter), cache_max_size=2
    )

    service.classify_names(["Maria", "Anna"])
    service.classify_names(["Offline"])
    service.classify_names(["Anna"])
    service.classify_names(["Maria"])
    service.classify_names(["Heinrich"])
    service.classify_names(["Maria"])
    service.classify_names(["Anna"])
    assert adapter.inputs == [["Maria", "Anna"], ["Offline"], ["Heinrich"], ["Anna"]]


def test_classify_names_zero_capacity_reexecutes_successes() -> None:
    adapter = _ScriptedMethod([[_success_prediction()], [_success_prediction()]])
    service = DirectClassificationService(
        method_registry=_cache_registry(adapter), cache_max_size=0
    )

    assert service.classify_names(["Maria"]) == service.classify_names(["Maria"])
    assert adapter.inputs == [["Maria"], ["Maria"]]


@pytest.mark.parametrize("raises_failure", [False, True], ids=["returned_error", "raised_failure"])
def test_classify_names_late_failure_cannot_replace_recovered_success(
    raises_failure: bool,
) -> None:
    entered = Event()
    release = Event()
    call_lock = Lock()

    class ConcurrentMethod(_ScriptedMethod):
        def predict_batch(
            self, people: Sequence[PersonInput], config: MethodConfig
        ) -> list[PredictionResult]:
            del config
            with call_lock:
                self.inputs.append([person.forenames[0] for person in people])
                first_call = len(self.inputs) == 1
            if first_call:
                entered.set()
                if not release.wait(timeout=5):
                    raise AssertionError("late failure was not released")
                if raises_failure:
                    raise MethodDependencyError("late backend failure")
                return [PredictionResult(label=None, status=PredictionStatus.error)]
            return [_success_prediction()]

    adapter = ConcurrentMethod([])
    service = DirectClassificationService(
        method_registry=_cache_registry(adapter), cache_max_size=1
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        late = executor.submit(service.classify_names, ["Maria"])
        try:
            assert entered.wait(timeout=5)
            recovered = service.classify_names(["Maria"])
            assert recovered.results[0].classifications["counting_method"].status is (
                PredictionStatus.success
            )
        finally:
            release.set()
        failed = late.result(timeout=5)
    assert failed.results[0].classifications["counting_method"].status is PredictionStatus.error
    assert service.classify_names(["Maria"]) == recovered
    assert adapter.inputs == [["Maria"], ["Maria"]]


def test_classify_names_canonicalizes_validated_equivalent_configs() -> None:
    adapter = _ScriptedMethod([[_success_prediction()]])
    service = DirectClassificationService(
        method_registry=_cache_registry(adapter, config_model=_CacheIdentityConfig)
    )

    implicit_defaults: dict[str, JsonValue] = {
        "lookup_sha256": "a" * 64,
        "options": {"one": 1, "two": 2},
    }
    explicit_defaults: dict[str, JsonValue] = {
        "options": {"two": 2, "one": 1},
        "threshold": "0.5",
        "model_name": "first_model",
        "lookup_sha256": "a" * 64,
    }
    first = service.classify_names(["Maria"], method_configs={"counting_method": implicit_defaults})
    second = service.classify_names(
        ["Maria"], method_configs={"counting_method": explicit_defaults}
    )
    assert second == first
    assert adapter.inputs == [["Maria"]]


@pytest.mark.parametrize(
    "changed_config",
    [
        {"lookup_sha256": "b" * 64},
        {"lookup_sha256": "a" * 64, "threshold": 0.7},
        {"lookup_sha256": "a" * 64, "model_name": "second_model"},
        {"lookup_sha256": "a" * 64, "options": {"one": 1}},
    ],
    ids=["artifact_digest", "scientific_setting", "model_selection", "nested_setting"],
)
def test_classify_names_changed_configuration_misses_cache(
    changed_config: dict[str, Any],
) -> None:
    second_prediction = PredictionResult(label=CanonicalLabel.male, status=PredictionStatus.success)
    adapter = _ScriptedMethod([[_success_prediction()], [second_prediction]])
    service = DirectClassificationService(
        method_registry=_cache_registry(adapter, config_model=_CacheIdentityConfig)
    )

    service.classify_names(
        ["Maria"], method_configs={"counting_method": {"lookup_sha256": "a" * 64}}
    )
    changed = service.classify_names(["Maria"], method_configs={"counting_method": changed_config})
    assert changed.results[0].classifications["counting_method"].label is CanonicalLabel.male
    assert (
        service.classify_names(["Maria"], method_configs={"counting_method": changed_config})
        == changed
    )
    assert adapter.inputs == [["Maria"], ["Maria"]]


@pytest.mark.parametrize(
    "descriptor_update",
    [
        {"implementation_version": "changed_implementation"},
        {"normalization_version": "changed_normalization"},
        {"method_confidence_range": MethodConfidenceRange(minimum=0, maximum=1)},
    ],
    ids=["implementation", "normalization", "confidence_contract"],
)
def test_classify_names_revised_same_name_descriptor_misses_cache(
    monkeypatch: pytest.MonkeyPatch, descriptor_update: dict[str, Any]
) -> None:
    second_prediction = PredictionResult(label=CanonicalLabel.male, status=PredictionStatus.success)
    adapter = _ScriptedMethod([[_success_prediction()], [second_prediction]])
    original_registry = _cache_registry(adapter)
    service = DirectClassificationService(method_registry=original_registry)
    original = service.classify_names(["Maria"])

    revised_descriptor = adapter.descriptor.model_copy(update=descriptor_update)
    revised_registry = _cache_registry(adapter, descriptor=revised_descriptor)
    monkeypatch.setattr(service, "_method_registry", revised_registry)
    changed = service.classify_names(["Maria"])
    assert changed.results[0].classifications["counting_method"].label is CanonicalLabel.male
    assert service.classify_names(["Maria"]) == changed
    monkeypatch.setattr(service, "_method_registry", original_registry)
    assert service.classify_names(["Maria"]) == original
    assert adapter.inputs == [["Maria"], ["Maria"]]


def test_classify_names_invalid_config_does_not_reuse_or_poison_valid_cache() -> None:
    adapter = _ScriptedMethod([[_success_prediction()]])
    service = DirectClassificationService(
        method_registry=_cache_registry(adapter, config_model=_CacheIdentityConfig)
    )

    invalid = service.classify_names(
        ["Maria"], method_configs={"counting_method": {"lookup_sha256": "not-a-digest"}}
    )
    assert invalid.results[0].classifications["counting_method"].status is PredictionStatus.error
    assert adapter.inputs == []
    valid_config = {"counting_method": {"lookup_sha256": "a" * 64}}
    recovered = service.classify_names(["Maria"], method_configs=valid_config)
    assert (
        recovered.results[0].classifications["counting_method"].status is PredictionStatus.success
    )
    service.classify_names(
        ["Maria"], method_configs={"counting_method": {"lookup_sha256": "not-a-digest"}}
    )
    assert service.classify_names(["Maria"], method_configs=valid_config) == recovered
    assert adapter.inputs == [["Maria"]]


@pytest.mark.parametrize("logical_type", ["test_lookup", "test_model_manifest"])
def test_classify_names_resolves_recovered_and_revised_artifact_before_cache_lookup(
    logical_type: str,
) -> None:
    class LatestArtifacts:
        latest: Artifact | None = None

        def get_latest_artifact(self, requested_type: str) -> Artifact | None:
            assert requested_type == logical_type
            return self.latest

    artifacts = LatestArtifacts()
    unit_of_work = cast(UnitOfWork, SimpleNamespace(artifacts=artifacts))
    adapter = _ScriptedMethod(
        [
            [_success_prediction()],
            [PredictionResult(label=CanonicalLabel.male, status=PredictionStatus.success)],
        ]
    )
    registry = MethodRegistry(
        [
            MethodRegistration(
                descriptor=adapter.descriptor,
                config_model=LookupMethodConfig,
                adapter=adapter,
                queue_name="cpu",
                batch_size=100,
                data_artifact_logical_type=logical_type,
            )
        ]
    )
    service = DirectClassificationService(
        method_registry=registry,
        unit_of_work_factory=lambda: cast(UnitOfWork, nullcontext(unit_of_work)),
    )
    unavailable = service.classify_names(["Maria"])
    assert (
        unavailable.results[0].classifications["counting_method"].status is PredictionStatus.error
    )
    assert adapter.inputs == []

    artifacts.latest = Artifact(
        id=uuid4(),
        logical_type=logical_type,
        storage_uri="artifact://synthetic",
        sha256="a" * 64,
        byte_size=1,
        media_type="application/octet-stream",
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )
    recovered = service.classify_names(["Maria"])
    assert recovered.results[0].classifications["counting_method"].label is CanonicalLabel.female
    assert (
        service.classify_names(
            ["Maria"], method_configs={"counting_method": {"lookup_sha256": "a" * 64}}
        )
        == recovered
    )

    artifacts.latest = artifacts.latest.model_copy(update={"id": uuid4(), "sha256": "b" * 64})
    revised = service.classify_names(["Maria"])
    assert revised.results[0].classifications["counting_method"].label is CanonicalLabel.male
    assert service.classify_names(["Maria"]) == revised
    assert (
        service.classify_names(
            ["Maria"], method_configs={"counting_method": {"lookup_sha256": "a" * 64}}
        )
        == recovered
    )
    assert adapter.inputs == [["Maria"], ["Maria"]]
