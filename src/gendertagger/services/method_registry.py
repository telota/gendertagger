"""Server-side method registration and configuration resolution."""

from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import ValidationError

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.methods.base import MethodConfig
from gendertagger.models.method import MethodDescriptor


@dataclass(frozen=True, slots=True)
class MethodRegistration:
    """Runnable method metadata and its closed configuration contract."""

    descriptor: MethodDescriptor
    config_model: type[MethodConfig]


class MethodRegistryError(ValueError):
    """Base failure for method registration or configuration resolution."""


class UnknownMethodError(MethodRegistryError):
    """Raised when a run names a method without a registered adapter."""


class InvalidMethodConfigError(MethodRegistryError):
    """Raised when adapter-specific configuration validation fails."""

    def __init__(self, method_name: str) -> None:
        self.method_name = method_name
        super().__init__(f"configuration for method {method_name!r} is invalid")


class MethodRegistry:
    """Resolve raw run configuration only through registered method contracts."""

    def __init__(self, registrations: Iterable[MethodRegistration] = ()) -> None:
        registrations_by_name: dict[str, MethodRegistration] = {}
        for registration in registrations:
            method_name = registration.descriptor.name
            if method_name in registrations_by_name:
                msg = f"method {method_name!r} is registered more than once"
                raise MethodRegistryError(msg)
            registrations_by_name[method_name] = registration
        self._registrations = MappingProxyType(registrations_by_name)

    @property
    def registrations(self) -> tuple[MethodRegistration, ...]:
        """Return registrations in stable method-name order."""
        return tuple(self._registrations[name] for name in sorted(self._registrations))

    def resolve_run_config(self, config: RunConfig) -> RunConfig:
        """Apply adapter defaults and reject every unknown or invalid method config."""
        resolved_methods: list[MethodRunConfig] = []
        for method_config in config.methods:
            registration = self._registrations.get(method_config.name)
            if registration is None:
                msg = f"method {method_config.name!r} is not registered"
                raise UnknownMethodError(msg)
            try:
                resolved_config = registration.config_model.model_validate(
                    method_config.config
                ).model_dump(mode="json")
            except ValidationError as error:
                raise InvalidMethodConfigError(method_config.name) from error
            resolved_methods.append(method_config.model_copy(update={"config": resolved_config}))
        return config.model_copy(update={"methods": resolved_methods})
