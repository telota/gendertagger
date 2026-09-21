"""Validated and reproducible run configuration contracts."""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from gendertagger.models.method import METHOD_NAME_PATTERN


class _ClosedConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AggregationStrategy(StrEnum):
    """Supported versioned aggregation strategies."""

    reference_v1 = "reference_v1"


class MethodRunConfig(_ClosedConfigModel):
    """Configuration envelope for one method in a run."""

    name: str = Field(
        pattern=METHOD_NAME_PATTERN,
        description="Stable lowercase snake-case method identifier.",
    )
    enabled: bool = True
    config: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Adapter values resolved and validated by the server-side method registry.",
    )

    @field_validator("config")
    @classmethod
    def _validate_finite_config(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        _ensure_finite_json(value)
        return value


class AggregationConfig(_ClosedConfigModel):
    """Resolved configuration for the selected aggregation strategy."""

    strategy: AggregationStrategy = AggregationStrategy.reference_v1


class ExecutionConfig(_ClosedConfigModel):
    """Resolved orchestration behavior for a run."""

    fail_run_on_optional_method_error: bool = False


class RunConfig(_ClosedConfigModel):
    """Canonical configuration envelope for one run."""

    methods: list[MethodRunConfig]
    aggregation: AggregationConfig = Field(default_factory=AggregationConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

    @model_validator(mode="after")
    def _validate_unique_method_names(self) -> Self:
        seen: set[str] = set()
        for method in self.methods:
            if method.name in seen:
                msg = f"method names must be unique; repeated '{method.name}'"
                raise ValueError(msg)
            seen.add(method.name)
        return self

    def to_canonical_json(self) -> str:
        """Serialize the resolved configuration to canonical JSON."""
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def canonical_sha256(self) -> str:
        """Return the SHA-256 provenance hash of the canonical UTF-8 JSON."""
        return hashlib.sha256(self.to_canonical_json().encode("utf-8")).hexdigest()


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects ambiguous duplicate mapping keys."""

    # The positional ``deep`` flag is PyYAML's ``BaseConstructor.construct_mapping`` signature.
    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:  # noqa: FBT001, FBT002
        self.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                if key in mapping:
                    raise ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"found duplicate key ({key!r})",
                        key_node.start_mark,
                    )
            except TypeError as error:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found an unhashable mapping key",
                    key_node.start_mark,
                ) from error
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _ensure_finite_json(value: JsonValue) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        msg = "configuration numbers must be finite"
        raise ValueError(msg)
    if isinstance(value, list):
        for item in value:
            _ensure_finite_json(item)
    elif isinstance(value, dict):
        for item in value.values():
            _ensure_finite_json(item)


def parse_run_config_yaml(source: str) -> RunConfig:
    """Parse one safely constructed YAML document into a validated run configuration."""
    loader = _UniqueKeySafeLoader(source)
    try:
        payload: object = loader.get_single_data()
    finally:
        # types-PyYAML omits the type for SafeLoader cleanup.
        loader.dispose()  # type: ignore[no-untyped-call]
    return RunConfig.model_validate(payload)


def load_run_config(path: str | Path) -> RunConfig:
    """Load and validate a UTF-8 YAML run configuration from ``path``."""
    return parse_run_config_yaml(Path(path).read_text(encoding="utf-8"))
