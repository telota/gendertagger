"""Run canonical offline test profiles with optional authoritative coverage."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROTECTED_MARKERS = frozenset({"slow", "gpu", "external"})


@dataclass(frozen=True)
class TestProfile:
    """Define infrastructure requirements and exclusions for one ordinary suite."""

    required: frozenset[str]
    excluded: frozenset[str]

    @property
    def expression(self) -> str:
        """Return the pytest marker expression generated from the profile rules."""
        terms = sorted(self.required) + [f"not {marker}" for marker in sorted(self.excluded)]
        return " and ".join(terms)

    def accepts(self, markers: Collection[str]) -> bool:
        """Return whether the test satisfies this suite's marker requirements."""
        return self.required.issubset(markers) and self.excluded.isdisjoint(markers)


PROFILES = {
    "fast": TestProfile(
        required=frozenset(),
        excluded=_PROTECTED_MARKERS | {"integration", "postgres", "redis", "e2e"},
    ),
    "postgres": TestProfile(
        required=frozenset({"postgres"}),
        excluded=_PROTECTED_MARKERS | {"redis"},
    ),
    "redis": TestProfile(required=frozenset({"redis"}), excluded=_PROTECTED_MARKERS),
}


def partition_tests(test_markers: Mapping[str, Collection[str]]) -> dict[str, list[str]]:
    """Assign each ordinary test exactly once, rejecting missing or ambiguous profiles.

    Slow, GPU, and external tests belong to explicitly enabled protected suites and are excluded.
    Redis takes precedence over PostgreSQL for tests that require both services.
    """
    partitions: dict[str, list[str]] = {name: [] for name in PROFILES}
    errors: list[str] = []
    for node_id, markers in test_markers.items():
        if not _PROTECTED_MARKERS.isdisjoint(markers):
            continue
        matches = [name for name, profile in PROFILES.items() if profile.accepts(markers)]
        if len(matches) != 1:
            errors.append(f"{node_id}: matched {matches or 'no ordinary profile'}")
            continue
        partitions[matches[0]].append(node_id)
    if errors:
        raise ValueError(
            "Every ordinary test must belong to exactly one canonical profile.\n"
            + "\n".join(errors)
            + "\nMark infrastructure tests with postgres or redis; mark protected tests explicitly."
        )
    return partitions


def pytest_arguments(
    profile_name: str,
    *,
    coverage: bool = False,
    collect_only: bool = False,
    junitxml: str | None = None,
    extra_arguments: Sequence[str] = (),
) -> list[str]:
    """Build the shared local/hook/CI invocation without starting pytest."""
    arguments = [
        "-m",
        PROFILES[profile_name].expression,
        "--hypothesis-profile=ci",
        "--durations=20",
    ]
    if collect_only:
        arguments.append("--collect-only")
    if coverage:
        threshold = "70" if profile_name == "fast" else "0"
        arguments.extend(
            [
                "--cov",
                "--cov-report=term-missing",
                f"--cov-report=xml:coverage-{profile_name}.xml",
                f"--cov-fail-under={threshold}",
            ]
        )
    if junitxml is not None:
        arguments.append(f"--junitxml={junitxml}")
    if profile_name == "redis":
        arguments.extend(["-p", "no:unraisableexception"])
    arguments.extend(extra_arguments)
    return arguments


def _validate_extra_arguments(arguments: Sequence[str]) -> None:
    for argument in arguments:
        if argument in {"--markexpr", "--collect-only", "--co"} or argument.startswith(
            ("-m", "--markexpr=", "--cov", "--no-cov", "--hypothesis-profile", "--junitxml")
        ):
            raise ValueError("Profile, collection, coverage and report options belong before --.")


def main(argv: Sequence[str] | None = None) -> int:
    """Run a canonical profile, failing early when the runner cannot support TestClient."""
    supplied = list(sys.argv[1:] if argv is None else argv)
    separator = supplied.index("--") if "--" in supplied else len(supplied)
    extra_arguments = supplied[separator + 1 :]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=tuple(PROFILES), nargs="?")
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--junitxml")
    parser.add_argument("--list-profiles", action="store_true")
    args = parser.parse_args(supplied[:separator])
    if args.list_profiles:
        for name, profile in PROFILES.items():
            print(f"{name}: {profile.expression}")
        return 0
    if args.profile is None:
        parser.error("a profile is required unless --list-profiles is used")
    if args.collect_only and (args.coverage or args.junitxml):
        parser.error("collection-only runs do not produce coverage or JUnit results")
    try:
        _validate_extra_arguments(extra_arguments)
    except ValueError as error:
        parser.error(str(error))

    if not args.collect_only and args.profile in {"postgres", "redis"}:
        required_settings = ["GENDERTAGGER_TEST_DATABASE_URL"]
        if args.profile == "redis":
            required_settings.append("GENDERTAGGER_TEST_REDIS_URL")
        missing_settings = [name for name in required_settings if not os.environ.get(name)]
        if missing_settings:
            parser.error("service-backed execution requires " + ", ".join(missing_settings))

    os.chdir(_BACKEND_ROOT)
    # Script invocation puts scripts/, rather than backend/, on sys.path. Use the same root as
    # `python -m pytest` so importlib-mode conftest and tooling imports resolve consistently.
    sys.path.insert(0, str(_BACKEND_ROOT))
    if not args.collect_only and args.profile in {"fast", "postgres"}:
        from scripts.check_asyncio_runner import main as check_runner

        if check_runner(["--timeout-seconds", "5"]) != 0:
            return 1
    if args.coverage:
        os.environ["COVERAGE_FILE"] = f".coverage.{args.profile}"

    import pytest

    arguments = pytest_arguments(
        args.profile,
        coverage=args.coverage,
        collect_only=args.collect_only,
        junitxml=args.junitxml,
        extra_arguments=extra_arguments,
    )
    return int(pytest.main(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
