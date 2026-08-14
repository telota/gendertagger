from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gendertagger.config.run import (
    AggregationConfig,
    AggregationStrategy,
    ExecutionConfig,
    MethodRunConfig,
    RunConfig,
    load_run_config,
    parse_run_config_yaml,
)

pytestmark = pytest.mark.contract

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_example_run_config_loads_as_resolved_contract() -> None:
    config = load_run_config(_REPOSITORY_ROOT / "config/example.yaml")

    assert [method.name for method in config.methods] == [
        "parenthetical_qualifier",
        "gnd",
        "gender_guesser",
        "wiki_gendersort",
        "hivoto",
        "nomquamgender",
        "hf_distilbert",
        "hf_genderize",
        "local_llm",
        "hivoto_xgboost",
    ]
    assert config.methods[1].config == {"lookup_sha256": "a" * 64}
    assert config.methods[3].config == {"lookup_sha256": "b" * 64}
    assert config.methods[4].config == {"lookup_sha256": "c" * 64}
    assert config.methods[5].config == {"threshold": 0.1}
    assert config.methods[-1].enabled is False
    assert config.aggregation.strategy is AggregationStrategy.reference_v1
    assert config.execution.fail_run_on_optional_method_error is False


def test_run_config_defaults_are_resolved_and_mutable_values_are_isolated() -> None:
    first_method = MethodRunConfig(name="gnd")
    second_method = MethodRunConfig(name="gender_guesser")
    first = RunConfig(methods=[first_method])
    second = RunConfig(methods=[second_method])

    first.methods[0].config["snapshot"] = "gnd-2026-03"
    assert second.methods[0].config == {}
    assert first.model_dump(mode="json") == {
        "methods": [
            {
                "name": "gnd",
                "enabled": True,
                "config": {"snapshot": "gnd-2026-03"},
            }
        ],
        "aggregation": {"strategy": "reference_v1"},
        "execution": {"fail_run_on_optional_method_error": False},
    }


@pytest.mark.scientific
def test_aggregation_strategy_exposes_exact_reference_value() -> None:
    assert AggregationStrategy.__members__ == {
        "reference_v1": AggregationStrategy.reference_v1,
    }
    assert AggregationStrategy.reference_v1.value == "reference_v1"


@pytest.mark.parametrize("strategy", ["REFERENCE_V1", "reference", "weighted_v1"])
def test_aggregation_config_rejects_unsupported_strategy(strategy: str) -> None:
    with pytest.raises(ValidationError):
        AggregationConfig.model_validate({"strategy": strategy})


@pytest.mark.parametrize(
    "name",
    ["", " ", "Gender_Guesser", "_gnd", "gnd-api", "gnd lookup"],
)
def test_method_run_config_rejects_unstable_identifiers(name: str) -> None:
    with pytest.raises(ValidationError):
        MethodRunConfig(name=name)


@pytest.mark.parametrize("second_enabled", [True, False])
def test_run_config_rejects_duplicate_method_names_regardless_of_state(
    second_enabled: bool,
) -> None:
    with pytest.raises(ValidationError):
        RunConfig(
            methods=[
                MethodRunConfig(name="gnd"),
                MethodRunConfig(name="gnd", enabled=second_enabled),
            ]
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"methods": [{"name": "gnd"}], "unexpected": True},
        {"methods": [{"name": "gnd", "unexpected": True}]},
        {"methods": [{"name": "gnd"}], "aggregation": {"unexpected": True}},
        {"methods": [{"name": "gnd"}], "execution": {"unexpected": True}},
    ],
)
def test_run_config_rejects_unknown_fields_at_every_closed_level(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RunConfig.model_validate(payload)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_method_run_config_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValidationError):
        MethodRunConfig(name="local_llm", config={"sampling": [{"temperature": value}]})


def test_run_config_canonical_json_and_sha256_match_golden_values() -> None:
    config = RunConfig(
        methods=[
            MethodRunConfig(
                name="local_llm",
                config={
                    "model": "mödél:20b",
                    "seed": None,
                    "stop": [],
                    "temperature": 0.5,
                },
            )
        ]
    )

    assert config.to_canonical_json() == (
        '{"aggregation":{"strategy":"reference_v1"},'
        '"execution":{"fail_run_on_optional_method_error":false},'
        '"methods":[{"config":{"model":"mödél:20b","seed":null,"stop":[],'
        '"temperature":0.5},'
        '"enabled":true,"name":"local_llm"}]}'
    )
    assert config.canonical_sha256() == (
        "49c2b67d41d67adc8630d114dfbf0408d5f2be731d6e42653f2b489be12fa377"
    )


def test_equivalent_yaml_resolves_to_identical_canonical_json_and_hash() -> None:
    compact = """
methods:
  - name: nomquamgender
    config: {model: "nqg-de", threshold: 0.50}
"""
    explicit = """
# Representation changes must not change resolved provenance.
execution:
  fail_run_on_optional_method_error: false
aggregation:
  strategy: reference_v1
methods:
  - config:
      threshold: 0.5
      model: "nqg-de"
    enabled: true
    name: nomquamgender
"""

    first = parse_run_config_yaml(compact)
    second = parse_run_config_yaml(explicit)

    assert first == second
    assert first.to_canonical_json() == second.to_canonical_json()
    assert first.canonical_sha256() == second.canonical_sha256()


def test_semantic_and_method_order_changes_produce_distinct_hashes() -> None:
    baseline = RunConfig(
        methods=[MethodRunConfig(name="gnd"), MethodRunConfig(name="gender_guesser")]
    )
    disabled = RunConfig(
        methods=[
            MethodRunConfig(name="gnd", enabled=False),
            MethodRunConfig(name="gender_guesser"),
        ]
    )
    configured = RunConfig(
        methods=[
            MethodRunConfig(name="gnd", config={"snapshot": "gnd-2026-03"}),
            MethodRunConfig(name="gender_guesser"),
        ]
    )
    reordered = RunConfig(methods=list(reversed(baseline.methods)))

    assert (
        len(
            {
                baseline.canonical_sha256(),
                disabled.canonical_sha256(),
                configured.canonical_sha256(),
                reordered.canonical_sha256(),
            }
        )
        == 4
    )


def test_canonical_json_round_trip_preserves_configuration_and_hash() -> None:
    config = RunConfig(
        methods=[MethodRunConfig(name="gnd", config={"snapshot": "gnd-2026-03"})],
        execution=ExecutionConfig(fail_run_on_optional_method_error=True),
    )

    restored = RunConfig.model_validate_json(config.to_canonical_json())

    assert restored == config
    assert restored.canonical_sha256() == config.canonical_sha256()


@pytest.mark.parametrize("source", ["", "true\n", "- gnd\n- gender_guesser\n"])
def test_yaml_loader_rejects_non_mapping_roots(source: str) -> None:
    with pytest.raises(ValidationError):
        parse_run_config_yaml(source)


@pytest.mark.parametrize(
    "source",
    [
        "methods: [\n",
        "methods: []\n---\nmethods: []\n",
        "!!python/object/apply:builtins.str [unsafe]\n",
        "methods: !include methods.yaml\n",
    ],
)
def test_yaml_loader_rejects_malformed_multiple_or_unsafe_documents(source: str) -> None:
    with pytest.raises(yaml.YAMLError):
        parse_run_config_yaml(source)


@pytest.mark.parametrize(
    "source",
    [
        "methods: []\nmethods: []\n",
        "methods:\n  - name: gnd\n    config:\n      snapshot: one\n      snapshot: two\n",
    ],
)
def test_yaml_loader_rejects_duplicate_mapping_keys(source: str) -> None:
    with pytest.raises(yaml.constructor.ConstructorError):
        parse_run_config_yaml(source)


def test_yaml_loader_rejects_unhashable_mapping_keys() -> None:
    source = "methods: []\n? [duplicate, key]\n: value\n"

    with pytest.raises(yaml.constructor.ConstructorError):
        parse_run_config_yaml(source)


@pytest.mark.parametrize(
    "source",
    [
        "methods:\n  - name: gnd\n    config: {snapshot: 2026-03-01}\n",
        "methods:\n  - name: gnd\n    config: {1: snapshot}\n",
        "methods:\n  - name: local_llm\n    config: {temperature: .nan}\n",
    ],
)
def test_yaml_loader_rejects_values_that_are_not_json_compatible(source: str) -> None:
    with pytest.raises(ValidationError):
        parse_run_config_yaml(source)


def test_run_config_json_schema_exposes_closed_public_shapes() -> None:
    schema = RunConfig.model_json_schema()

    assert set(schema["properties"]) == {"methods", "aggregation", "execution"}
    assert schema["required"] == ["methods"]
    assert schema["additionalProperties"] is False
    for model_name in ("MethodRunConfig", "AggregationConfig", "ExecutionConfig"):
        assert schema["$defs"][model_name]["additionalProperties"] is False
    assert set(schema["$defs"]["MethodRunConfig"]["properties"]) == {
        "name",
        "enabled",
        "config",
    }
    assert set(schema["$defs"]["AggregationConfig"]["properties"]) == {"strategy"}
    assert set(schema["$defs"]["ExecutionConfig"]["properties"]) == {
        "fail_run_on_optional_method_error"
    }
