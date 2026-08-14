"""Server-side method registration and configuration resolution."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from gendertagger.config.run import MethodRunConfig, RunConfig
from gendertagger.methods.base import GenderMethod, LookupMethodConfig, MethodConfig
from gendertagger.methods.gender_guesser import GenderGuesserMethod
from gendertagger.methods.gnd import GndMethod
from gendertagger.methods.gnd_snapshot import GND_LOOKUP_LOGICAL_TYPE
from gendertagger.methods.hf_distilbert import (
    HF_DISTILBERT_MODEL_MANIFEST_LOGICAL_TYPE,
    HfDistilbertMethod,
)
from gendertagger.methods.hf_genderize import (
    HF_GENDERIZE_MODEL_MANIFEST_LOGICAL_TYPE,
    HfGenderizeMethod,
)
from gendertagger.methods.hivoto import HIVOTO_LOOKUP_LOGICAL_TYPE, HivotoMethod
from gendertagger.methods.hivoto_xgboost import (
    HIVOTO_XGBOOST_MODEL_MANIFEST_LOGICAL_TYPE,
    HivotoXgboostMethod,
)
from gendertagger.methods.model_manifest import (
    ModelDirectoryResolver,
    UnavailableModelDirectoryResolver,
)
from gendertagger.methods.nomquamgender import NomquamgenderMethod
from gendertagger.methods.parenthetical_qualifier import ParentheticalQualifierMethod
from gendertagger.methods.sqlite_lookup import (
    LookupAssetResolver,
    UnavailableLookupAssetResolver,
)
from gendertagger.methods.wiki_gendersort import (
    WIKI_GENDERSORT_LOOKUP_LOGICAL_TYPE,
    WikiGendersortMethod,
)
from gendertagger.models.artifact import ARTIFACT_TYPE_PATTERN
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.models.run import QUEUE_NAME_PATTERN

# CPU rule/lookup batch size within the docs/06-task-queue.md 100-500 range.
_CPU_BATCH_SIZE = 200


@dataclass(frozen=True, slots=True)
class MethodRegistration:
    """Runnable method metadata and its closed configuration contract."""

    descriptor: MethodDescriptor
    config_model: type[MethodConfig]
    adapter: GenderMethod[Any]
    queue_name: str
    batch_size: int
    data_artifact_logical_type: str | None = None

    def __post_init__(self) -> None:
        """Reject operational routing values a worker could not honor."""
        if re.fullmatch(QUEUE_NAME_PATTERN, self.queue_name) is None:
            msg = f"queue name {self.queue_name!r} is not a valid routing class"
            raise MethodRegistryError(msg)
        if self.batch_size <= 0:
            msg = "batch_size must be positive"
            raise MethodRegistryError(msg)
        if self.data_artifact_logical_type is not None:
            if re.fullmatch(ARTIFACT_TYPE_PATTERN, self.data_artifact_logical_type) is None:
                msg = (
                    f"artifact type {self.data_artifact_logical_type!r} is not a valid logical type"
                )
                raise MethodRegistryError(msg)
            if not issubclass(self.config_model, LookupMethodConfig):
                msg = "data-backed registrations require a LookupMethodConfig"
                raise MethodRegistryError(msg)


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

    def registration_for(self, method_name: str) -> MethodRegistration | None:
        """Return the registration for one method name, or ``None`` when absent."""
        return self._registrations.get(method_name)

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


def default_method_registry(
    lookup_asset_resolver: LookupAssetResolver | None = None,
    model_directory_resolver: ModelDirectoryResolver | None = None,
) -> MethodRegistry:
    """Register every classification adapter runnable on this server."""
    resolver = (
        lookup_asset_resolver
        if lookup_asset_resolver is not None
        else UnavailableLookupAssetResolver()
    )
    model_resolver = (
        model_directory_resolver
        if model_directory_resolver is not None
        else UnavailableModelDirectoryResolver()
    )
    return MethodRegistry(
        [
            MethodRegistration(
                descriptor=ParentheticalQualifierMethod.descriptor,
                config_model=ParentheticalQualifierMethod.config_model,
                adapter=ParentheticalQualifierMethod(),
                queue_name=CPU_QUEUE,
                batch_size=_CPU_BATCH_SIZE,
            ),
            MethodRegistration(
                descriptor=GndMethod.descriptor,
                config_model=GndMethod.config_model,
                adapter=GndMethod(lookup_asset_resolver=resolver),
                queue_name=CPU_QUEUE,
                batch_size=_CPU_BATCH_SIZE,
                data_artifact_logical_type=GND_LOOKUP_LOGICAL_TYPE,
            ),
            MethodRegistration(
                descriptor=GenderGuesserMethod.descriptor,
                config_model=GenderGuesserMethod.config_model,
                adapter=GenderGuesserMethod(),
                queue_name=CPU_QUEUE,
                batch_size=_CPU_BATCH_SIZE,
            ),
            MethodRegistration(
                descriptor=WikiGendersortMethod.descriptor,
                config_model=WikiGendersortMethod.config_model,
                adapter=WikiGendersortMethod(lookup_asset_resolver=resolver),
                queue_name=CPU_QUEUE,
                batch_size=_CPU_BATCH_SIZE,
                data_artifact_logical_type=WIKI_GENDERSORT_LOOKUP_LOGICAL_TYPE,
            ),
            MethodRegistration(
                descriptor=HivotoMethod.descriptor,
                config_model=HivotoMethod.config_model,
                adapter=HivotoMethod(lookup_asset_resolver=resolver),
                queue_name=CPU_QUEUE,
                batch_size=_CPU_BATCH_SIZE,
                data_artifact_logical_type=HIVOTO_LOOKUP_LOGICAL_TYPE,
            ),
            MethodRegistration(
                descriptor=NomquamgenderMethod.descriptor,
                config_model=NomquamgenderMethod.config_model,
                adapter=NomquamgenderMethod(),
                queue_name=CPU_QUEUE,
                batch_size=_CPU_BATCH_SIZE,
            ),
            MethodRegistration(
                descriptor=HfDistilbertMethod.descriptor,
                config_model=HfDistilbertMethod.config_model,
                adapter=HfDistilbertMethod(model_directory_resolver=model_resolver),
                queue_name=CPU_QUEUE,
                batch_size=_CPU_BATCH_SIZE,
                data_artifact_logical_type=HF_DISTILBERT_MODEL_MANIFEST_LOGICAL_TYPE,
            ),
            MethodRegistration(
                descriptor=HfGenderizeMethod.descriptor,
                config_model=HfGenderizeMethod.config_model,
                adapter=HfGenderizeMethod(model_directory_resolver=model_resolver),
                queue_name=CPU_QUEUE,
                batch_size=_CPU_BATCH_SIZE,
                data_artifact_logical_type=HF_GENDERIZE_MODEL_MANIFEST_LOGICAL_TYPE,
            ),
            MethodRegistration(
                descriptor=HivotoXgboostMethod.descriptor,
                config_model=HivotoXgboostMethod.config_model,
                adapter=HivotoXgboostMethod(model_directory_resolver=model_resolver),
                queue_name=CPU_QUEUE,
                batch_size=_CPU_BATCH_SIZE,
                data_artifact_logical_type=HIVOTO_XGBOOST_MODEL_MANIFEST_LOGICAL_TYPE,
            ),
        ]
    )
