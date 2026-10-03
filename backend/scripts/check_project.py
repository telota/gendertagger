"""Run component-sensitive pre-push checks, with conservative full-check fallbacks."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALL_COMPONENTS = frozenset({"backend", "frontend"})
_COMMIT_REF = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
_FULL_CHECK_PATHS = frozenset(
    {
        "AGENTS.md",
        "CONTRIBUTING.md",
        ".gitlab-ci.yml",
        ".pre-commit-config.yaml",
        "backend/scripts/check_project.py",
        "backend/scripts/run_tests.py",
        "backend/tests/tooling/test_check_project.py",
    }
)
_SHARED_DOCUMENTS = frozenset(
    {
        "SPEC.md",
        "DESIGN.md",
        "docs/01-architecture.md",
        "docs/03-pydantic-contracts.md",
        "docs/05-api.md",
        "docs/13-auth-and-security.md",
        "docs/14-testing.md",
        "docs/18-engineering-and-quality.md",
        "docs/19-coding-and-documentation-style.md",
    }
)
_BACKEND_DOCUMENTS = frozenset(
    {
        "docs/02-domain-model.md",
        "docs/04-persistence.md",
        "docs/06-task-queue.md",
        "docs/07-methods-and-aggregation.md",
        "docs/08-ingestion-and-export.md",
        "docs/10-evaluation.md",
        "docs/11-provenance-and-reproducibility.md",
        "docs/20-method-adapters-reference.md",
    }
)
_SHARED_BACKEND_PREFIXES = (
    "backend/src/gendertagger/api/",
    "backend/src/gendertagger/models/",
    "backend/src/gendertagger/config/",
)


@dataclass(frozen=True)
class CheckSelection:
    """Describe the components to verify and the reason for choosing them."""

    components: frozenset[str]
    reason: str


@dataclass(frozen=True)
class CheckCommand:
    """Keep subprocess arguments separate from their absolute project working directory."""

    arguments: tuple[str, ...]
    cwd: Path


def _path_components(path: str) -> frozenset[str] | None:
    if path.startswith(("contracts/", "deploy/")) or (
        "/" not in path and path.startswith("compose") and path.endswith(".yaml")
    ):
        return _ALL_COMPONENTS
    if path in _SHARED_DOCUMENTS:
        return _ALL_COMPONENTS
    if path in _BACKEND_DOCUMENTS or (
        path.startswith("docs/decisions/ADR-") and path.endswith(".md")
    ):
        return frozenset({"backend"})
    if path.endswith(".md") and (
        "/" not in path
        or path.startswith("docs/")
        or path in {"backend/README.md", "frontend/README.md"}
    ):
        return frozenset()
    if path.startswith(_SHARED_BACKEND_PREFIXES) or (
        path == "backend/scripts/update_openapi_snapshot.py"
    ):
        return _ALL_COMPONENTS
    for component in ("backend", "frontend"):
        if path.startswith(f"{component}/"):
            return frozenset({component})
    return None


def select_checks(
    paths: Sequence[str], *, full: bool = False, repository_root: Path = _REPOSITORY_ROOT
) -> CheckSelection:
    """Select components from repository-relative or absolute paths, including deleted files.

    No filesystem existence or Git state is required. Missing path information, unknown
    ownership, and verification governance changes conservatively select both components.
    """
    if full:
        return CheckSelection(_ALL_COMPONENTS, "full checks explicitly requested")
    if not paths:
        return CheckSelection(_ALL_COMPONENTS, "no changed paths supplied; using full checks")
    components: set[str] = set()
    for supplied_path in paths:
        resolved_path = (repository_root / supplied_path).resolve()
        try:
            path = resolved_path.relative_to(repository_root).as_posix()
        except ValueError:
            return CheckSelection(_ALL_COMPONENTS, "path outside repository; using full checks")
        if path in _FULL_CHECK_PATHS or path.startswith((".github/", ".gitlab/", "ci/")):
            return CheckSelection(
                _ALL_COMPONENTS, f"verification configuration changed: {path}; using full checks"
            )
        owners = _path_components(path)
        if owners is None:
            return CheckSelection(_ALL_COMPONENTS, f"unknown ownership: {path}; using full checks")
        components.update(owners)
    return CheckSelection(frozenset(components), "components selected from changed paths")


def select_push_checks(
    paths: Sequence[str],
    *,
    full: bool = False,
    environment: Mapping[str, str] | None = None,
    repository_root: Path = _REPOSITORY_ROOT,
) -> CheckSelection:
    """Supplement hook filenames with both sides of changes in a validated pushed range.

    Pre-commit may omit deleted or renamed-away paths. A NUL-delimited diff with rename
    detection disabled preserves those paths; an uninspectable range selects full checks.
    Manual invocations without push refs use the supplied path list.
    """
    if full:
        return select_checks(paths, full=True, repository_root=repository_root)
    resolved_environment = os.environ if environment is None else environment
    from_ref = resolved_environment.get("PRE_COMMIT_FROM_REF")
    to_ref = resolved_environment.get("PRE_COMMIT_TO_REF")
    if from_ref is None and to_ref is None:
        return select_checks(paths, repository_root=repository_root)
    if from_ref is None or to_ref is None:
        return CheckSelection(_ALL_COMPONENTS, "incomplete push refs; using full checks")
    if not _COMMIT_REF.fullmatch(from_ref) or not _COMMIT_REF.fullmatch(to_ref):
        return CheckSelection(_ALL_COMPONENTS, "unsupported push refs; using full checks")
    arguments = (
        "git",
        "diff",
        "--no-renames",
        "--name-only",
        "-z",
        "--no-ext-diff",
        "--no-textconv",
        from_ref,
        to_ref,
        "--",
    )
    try:
        result = subprocess.run(  # noqa: S603 -- only complete hexadecimal refs enter this fixed command.
            arguments, cwd=repository_root, capture_output=True, check=False
        )
    except OSError:
        return CheckSelection(_ALL_COMPONENTS, "could not inspect pushed range; using full checks")
    if result.returncode != 0:
        return CheckSelection(_ALL_COMPONENTS, "could not inspect pushed range; using full checks")
    try:
        output = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return CheckSelection(_ALL_COMPONENTS, "undecodable pushed paths; using full checks")
    if output and (not output.endswith("\0") or "" in output[:-1].split("\0")):
        return CheckSelection(_ALL_COMPONENTS, "malformed pushed paths; using full checks")
    changed_paths = output[:-1].split("\0") if output else []
    selection = select_checks([*paths, *changed_paths], repository_root=repository_root)
    return CheckSelection(selection.components, f"{selection.reason}; includes all pushed paths")


def verification_commands(selection: CheckSelection) -> tuple[CheckCommand, ...]:
    """Build self-contained component checks, always starting with documentation policy."""
    backend = _REPOSITORY_ROOT / "backend"
    commands = [CheckCommand((sys.executable, "scripts/check_documentation.py"), cwd=backend)]
    if "backend" in selection.components:
        commands.append(CheckCommand(("uv", "lock", "--check"), cwd=backend))
        commands.extend(
            CheckCommand((sys.executable, f"scripts/{script}"), cwd=backend)
            for script in (
                "check_contract_naming.py",
                "check_package_initializers.py",
                "check_dead_code.py",
            )
        )
        commands.extend(
            CheckCommand(arguments, cwd=backend)
            for arguments in (
                ("uv", "run", "--locked", "ruff", "format", "--check", "."),
                ("uv", "run", "--locked", "ruff", "check", "."),
                ("uv", "run", "--locked", "mypy"),
                ("npm", "run", "typecheck:pyright"),
                ("uv", "run", "--locked", "lint-imports"),
                ("uv", "run", "--locked", "python", "scripts/run_tests.py", "core", "--coverage"),
            )
        )
    if "frontend" in selection.components:
        commands.extend(
            CheckCommand(("npm", "run", script), cwd=_REPOSITORY_ROOT / "frontend")
            for script in ("lint", "format:check", "check")
        )
    return tuple(commands)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected checks, or print their commands without executing in dry-run mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    selection = select_push_checks(args.paths, full=args.full)
    scope = ", ".join(("documentation", *sorted(selection.components)))
    print(f"Checking: {scope}. Reason: {selection.reason}.", flush=True)
    for command in verification_commands(selection):
        print(f"[{command.cwd}] {shlex.join(command.arguments)}", flush=True)
        if args.dry_run:
            continue
        try:
            result = subprocess.run(command.arguments, cwd=command.cwd, check=False)  # noqa: S603 -- commands are repository-defined argument lists, never shell text.
        except OSError as error:
            print(f"Could not start check: {error}", file=sys.stderr)
            return 1
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
