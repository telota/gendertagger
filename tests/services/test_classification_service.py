from collections.abc import Sequence
from typing import Any

import pytest

from gendertagger.methods.base import MethodConfig, MethodDependencyError
from gendertagger.methods.gender_guesser import GenderGuesserMethod
from gendertagger.methods.nomquamgender import NomquamgenderMethod
from gendertagger.methods.parenthetical_qualifier import ParentheticalQualifierMethod
from gendertagger.models.aggregation import AggregationOutcome, OverrideSource
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.method_registry import (
    MethodRegistration,
    MethodRegistry,
    UnknownMethodError,
)


class _StubLookupConfig(MethodConfig):
    lookup_sha256: str


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

    def predict_batch(
        self, people: Sequence[PersonInput], config: Any
    ) -> list[PredictionResult]:
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

    def predict_batch(
        self, people: Sequence[PersonInput], config: Any
    ) -> list[PredictionResult]:
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
    resp2 = service.classify_names(names=["Maria", "Maria", "Heinrich", "Anna"], methods=["counting_method"])
    assert len(resp2.results) == 4
    # Only "Anna" should have been a cache miss and executed
    assert counter.call_count == 2
    assert counter.total_people_classified == 3
