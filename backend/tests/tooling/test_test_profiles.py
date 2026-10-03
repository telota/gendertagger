from __future__ import annotations

import pytest
from scripts.run_tests import PROFILES, main, partition_tests, pytest_arguments


@pytest.mark.parametrize(
    ("markers", "expected"),
    [
        (set(), "core"),
        ({"unit", "scientific"}, "core"),
        ({"contract"}, "core"),
        ({"postgres"}, "postgres"),
        ({"integration", "postgres"}, "postgres"),
        ({"redis", "integration", "e2e"}, "redis"),
        ({"redis", "postgres", "integration"}, "redis"),
    ],
)
def test_ordinary_tests_are_assigned_to_one_infrastructure_profile(
    markers: set[str], expected: str
) -> None:
    partitions = partition_tests({"tests/example.py::test_case": markers})

    assert partitions[expected] == ["tests/example.py::test_case"]
    assert sum(len(items) for items in partitions.values()) == 1


@pytest.mark.parametrize("marker", ["slow", "gpu", "external"])
def test_protected_tests_are_excluded_from_every_ordinary_profile(marker: str) -> None:
    partitions = partition_tests({"protected": {marker, "postgres", "redis"}})

    assert all(not items for items in partitions.values())


@pytest.mark.parametrize("markers", [{"integration"}, {"e2e"}])
def test_unassigned_infrastructure_tests_fail_with_the_node_id(markers: set[str]) -> None:
    with pytest.raises(
        ValueError, match=r"tests/missing\.py::test_case: matched no ordinary profile"
    ):
        partition_tests({"tests/missing.py::test_case": markers})


@pytest.mark.parametrize("name", list(PROFILES))
@pytest.mark.parametrize(
    "markers",
    [
        set(),
        {"integration"},
        {"postgres"},
        {"postgres", "redis"},
        {"redis", "e2e"},
        {"slow", "postgres"},
        {"external", "redis"},
        {"gpu"},
    ],
)
def test_generated_marker_expressions_match_the_partition_rules(
    name: str, markers: set[str]
) -> None:
    from _pytest.mark.expression import Expression

    expression = Expression.compile(PROFILES[name].expression)

    def matches(marker: str, /, **_kwargs: str | int | bool | None) -> bool:
        return marker in markers

    assert expression.evaluate(matches) == PROFILES[name].accepts(markers)


@pytest.mark.parametrize(("name", "floor"), [("core", "70"), ("postgres", "0"), ("redis", "0")])
def test_covered_profiles_preserve_the_partial_coverage_gates(name: str, floor: str) -> None:
    arguments = pytest_arguments(name, coverage=True, junitxml=f"junit-{name}.xml")

    assert f"--cov-fail-under={floor}" in arguments
    assert f"--cov-report=xml:coverage-{name}.xml" in arguments
    assert f"--junitxml=junit-{name}.xml" in arguments
    assert "--hypothesis-profile=ci" in arguments
    assert "--durations=20" in arguments


def test_uncovered_focused_profile_does_not_require_a_full_coverage_percentage() -> None:
    arguments = pytest_arguments("core", extra_arguments=["tests/contracts", "-k", "prediction"])

    assert not any(argument.startswith("--cov") for argument in arguments)
    assert arguments[-3:] == ["tests/contracts", "-k", "prediction"]


def test_redis_profile_preserves_the_real_worker_plugin_exception() -> None:
    assert pytest_arguments("redis")[-2:] == ["-p", "no:unraisableexception"]


@pytest.mark.parametrize("profile", ["postgres", "redis"])
def test_missing_infrastructure_configuration_fails_before_tests_can_skip(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    monkeypatch.delenv("GENDERTAGGER_TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("GENDERTAGGER_TEST_REDIS_URL", raising=False)

    with pytest.raises(SystemExit, match="2"):
        main([profile])


@pytest.mark.parametrize(
    "argument", ["-m", "-mredis", "--markexpr=redis", "--cov-fail-under=0", "--no-cov"]
)
def test_pytest_extras_cannot_replace_the_authoritative_profile_or_coverage(argument: str) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(["core", "--", argument])


def test_collection_only_does_not_probe_testclient_or_require_service_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def collect(arguments: list[str]) -> int:
        captured.extend(arguments)
        return 5

    monkeypatch.setattr(pytest, "main", collect)
    assert main(["postgres", "--collect-only"]) == 5
    assert "--collect-only" in captured
    assert "--cov" not in captured
