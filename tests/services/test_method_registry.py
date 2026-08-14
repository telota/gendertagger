from collections.abc import Sequence

import pytest
from pydantic import Field

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.methods.base import MethodConfig
from gendertagger.models.classification import PredictionResult, PredictionStatus
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput
from gendertagger.services.method_registry import (
    InvalidMethodConfigError,
    MethodRegistration,
    MethodRegistry,
    MethodRegistryError,
    UnknownMethodError,
    default_method_registry,
)


class DemoMethodConfig(MethodConfig):
    threshold: float = Field(default=0.5, gt=0, lt=1)


class _DemoMethod:
    descriptor = MethodDescriptor(
        name="demo_method",
        implementation_version="demo_v1",
        normalization_version="demo_normalization_v1",
    )
    config_model = DemoMethodConfig

    def predict_batch(
        self, people: Sequence[PersonInput], config: DemoMethodConfig
    ) -> list[PredictionResult]:
        del config
        return [
            PredictionResult(label=None, status=PredictionStatus.abstain, raw_label=None)
            for _ in people
        ]


_DEMO_ADAPTER = _DemoMethod()


def _registration() -> MethodRegistration:
    return MethodRegistration(
        descriptor=_DemoMethod.descriptor,
        config_model=DemoMethodConfig,
        adapter=_DEMO_ADAPTER,
        queue_name="cpu",
        batch_size=100,
    )


def test_registry_applies_adapter_defaults_to_resolved_run_config() -> None:
    registry = MethodRegistry([_registration()])
    raw_config = RunConfig(methods=[MethodRunConfig(name="demo_method")])

    resolved = registry.resolve_run_config(raw_config)

    assert resolved.methods[0].config == {"threshold": 0.5}
    assert raw_config.methods[0].config == {}
    assert registry.registrations == (_registration(),)


def test_registry_rejects_unknown_and_invalid_method_configuration() -> None:
    registry = MethodRegistry([_registration()])

    with pytest.raises(UnknownMethodError, match="not registered"):
        registry.resolve_run_config(RunConfig(methods=[MethodRunConfig(name="unknown_method")]))
    with pytest.raises(InvalidMethodConfigError, match="demo_method"):
        registry.resolve_run_config(
            RunConfig(methods=[MethodRunConfig(name="demo_method", config={"threshold": 2.0})])
        )


def test_default_registry_requires_content_digest_for_lookup_methods() -> None:
    registry = default_method_registry()

    for method_name in (
        "gnd",
        "wiki_gendersort",
        "hivoto",
        "hf_distilbert",
        "hf_genderize",
    ):
        with pytest.raises(InvalidMethodConfigError, match=method_name):
            registry.resolve_run_config(RunConfig(methods=[MethodRunConfig(name=method_name)]))


def test_registry_rejects_duplicate_method_names() -> None:
    with pytest.raises(MethodRegistryError, match="more than once"):
        MethodRegistry([_registration(), _registration()])
