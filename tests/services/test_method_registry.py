import pytest
from pydantic import Field

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.methods.base import MethodConfig
from gendertagger.models.method import MethodDescriptor
from gendertagger.services.method_registry import (
    InvalidMethodConfigError,
    MethodRegistration,
    MethodRegistry,
    MethodRegistryError,
    UnknownMethodError,
)


class DemoMethodConfig(MethodConfig):
    threshold: float = Field(default=0.5, gt=0, lt=1)


def _registration() -> MethodRegistration:
    return MethodRegistration(
        descriptor=MethodDescriptor(
            name="demo_method",
            implementation_version="demo_v1",
            normalization_version="demo_normalization_v1",
        ),
        config_model=DemoMethodConfig,
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


def test_registry_rejects_duplicate_method_names() -> None:
    with pytest.raises(MethodRegistryError, match="more than once"):
        MethodRegistry([_registration(), _registration()])
