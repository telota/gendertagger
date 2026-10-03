"""Component selection must avoid omissions while preserving fail-fast verification."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from scripts import check_project

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clear_push_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    monkeypatch.delenv("PRE_COMMIT_TO_REF", raising=False)


@pytest.mark.parametrize(
    ("path", "components"),
    [
        ("backend/src/gendertagger/services/deleted_service.py", {"backend"}),
        ("backend/tests/fixtures/foo.md", {"backend"}),
        ("frontend/src/deleted_view.vue", {"frontend"}),
        ("./frontend/src/views/Review View.vue", {"frontend"}),
        ("contracts/openapi-v1.json", {"backend", "frontend"}),
        ("contracts/README.md", {"backend", "frontend"}),
        ("backend/src/gendertagger/api/router.py", {"backend", "frontend"}),
        ("backend/src/gendertagger/models/person.py", {"backend", "frontend"}),
        ("backend/src/gendertagger/config/run.py", {"backend", "frontend"}),
        ("backend/scripts/update_openapi_snapshot.py", {"backend", "frontend"}),
        ("compose.test.yaml", {"backend", "frontend"}),
        ("deploy/nginx.conf", {"backend", "frontend"}),
        ("README.md", set()),
        ("backend/README.md", set()),
        ("frontend/README.md", set()),
        ("docs/22-future-development.md", set()),
        ("docs/07-methods-and-aggregation.md", {"backend"}),
        ("docs/decisions/ADR-9999-scientific-contract.md", {"backend"}),
        ("docs/03-pydantic-contracts.md", {"backend", "frontend"}),
        ("docs/14-testing.md", {"backend", "frontend"}),
        ("docs/18-engineering-and-quality.md", {"backend", "frontend"}),
        ("docs/19-coding-and-documentation-style.md", {"backend", "frontend"}),
        ("SPEC.md", {"backend", "frontend"}),
    ],
)
def test_changed_paths_select_owners_without_requiring_file_existence(
    tmp_path: Path, path: str, components: set[str]
) -> None:
    selection = check_project.select_checks([path], repository_root=tmp_path)

    assert selection.components == components


def test_absolute_paths_and_mixed_components_preserve_repository_context(tmp_path: Path) -> None:
    selection = check_project.select_checks(
        [str(tmp_path / "frontend/src/view.vue"), "backend/tests/domain/test_aggregation.py"],
        repository_root=tmp_path,
    )

    assert selection.components == {"backend", "frontend"}


@pytest.mark.parametrize(
    "paths",
    [
        [],
        ["unexpected/root_script.py"],
        ["unexpected/readme.md"],
        ["docs/image.png"],
        ["docs/decisions/ADR-9999-image.png"],
        ["../outside/frontend/view.vue"],
        ["frontend/src/view.vue", ".gitlab-ci.yml"],
        [".github/workflows/verification.yml"],
        ["AGENTS.md"],
        ["CONTRIBUTING.md"],
        [".pre-commit-config.yaml"],
        ["backend/scripts/check_project.py"],
        ["backend/scripts/run_tests.py"],
    ],
)
def test_uncertain_paths_and_verification_changes_fall_back_to_full_checks(
    tmp_path: Path, paths: list[str]
) -> None:
    selection = check_project.select_checks(paths, repository_root=tmp_path)

    assert selection.components == {"backend", "frontend"}
    assert "full checks" in selection.reason


def test_full_option_overrides_known_component_selection(tmp_path: Path) -> None:
    selection = check_project.select_checks(
        ["frontend/src/view.vue"], full=True, repository_root=tmp_path
    )

    assert selection.components == {"backend", "frontend"}
    assert "explicitly requested" in selection.reason


def _push_environment() -> dict[str, str]:
    return {"PRE_COMMIT_FROM_REF": "a" * 40, "PRE_COMMIT_TO_REF": "b" * 40}


@pytest.mark.parametrize(
    "changed_paths",
    [
        b"frontend/src/modified.vue\0backend/src/deleted.py\0",
        b"backend/src/old_name.py\0frontend/src/new_name.vue\0",
    ],
)
def test_push_diff_preserves_deleted_files_and_both_sides_of_component_renames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_paths: bytes
) -> None:
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=changed_paths))
    monkeypatch.setattr(subprocess, "run", run)

    selection = check_project.select_push_checks(
        ["frontend/src/modified.vue"], environment=_push_environment(), repository_root=tmp_path
    )

    assert selection.components == {"backend", "frontend"}
    arguments = run.call_args.args[0]
    assert "--no-renames" in arguments
    assert "--no-ext-diff" in arguments
    assert "--no-textconv" in arguments
    assert "-z" in arguments
    assert arguments[-1] == "--"
    assert run.call_args.kwargs["cwd"] == tmp_path
    assert "shell" not in run.call_args.kwargs


@pytest.mark.parametrize(
    "output",
    [b"frontend/src/truncated.vue", b"\xff\0", b"frontend/src/view.vue\0\0", b"\0"],
)
def test_unparseable_push_diff_selects_full_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output: bytes
) -> None:
    monkeypatch.setattr(
        subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=output))
    )

    selection = check_project.select_push_checks(
        ["frontend/src/view.vue"], environment=_push_environment(), repository_root=tmp_path
    )

    assert selection.components == {"backend", "frontend"}
    assert "full checks" in selection.reason


def test_failed_push_range_selects_full_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 128, stdout=b""))
    )

    selection = check_project.select_push_checks(
        ["frontend/src/view.vue"], environment=_push_environment()
    )

    assert selection.components == {"backend", "frontend"}
    assert "could not inspect pushed range" in selection.reason


@pytest.mark.parametrize(
    "environment",
    [
        {"PRE_COMMIT_FROM_REF": "a" * 40},
        {"PRE_COMMIT_TO_REF": "b" * 40},
        {"PRE_COMMIT_FROM_REF": "main", "PRE_COMMIT_TO_REF": "b" * 40},
        {"PRE_COMMIT_FROM_REF": "a" * 40, "PRE_COMMIT_TO_REF": "--output=untrusted"},
    ],
)
def test_unsupported_or_incomplete_refs_do_not_run_git(
    monkeypatch: pytest.MonkeyPatch, environment: dict[str, str]
) -> None:
    run = Mock(side_effect=AssertionError("unvalidated refs must not reach git"))
    monkeypatch.setattr(subprocess, "run", run)

    selection = check_project.select_push_checks(["frontend/src/view.vue"], environment=environment)

    assert selection.components == {"backend", "frontend"}
    assert not run.called


def test_explicit_full_checks_do_not_inspect_push_range(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock(side_effect=AssertionError("full checks do not need a push diff"))
    monkeypatch.setattr(subprocess, "run", run)

    selection = check_project.select_push_checks(
        ["frontend/src/view.vue"], full=True, environment=_push_environment()
    )

    assert selection.components == {"backend", "frontend"}
    assert not run.called


def test_cli_supplements_filtered_hook_filenames_from_push_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in _push_environment().items():
        monkeypatch.setenv(name, value)
    run = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, stdout=b"backend/src/deleted.py\0frontend/src/view.vue\0"
        )
    )
    monkeypatch.setattr(subprocess, "run", run)

    assert check_project.main(["--dry-run", "frontend/src/view.vue"]) == 0

    assert run.call_count == 1
    assert "documentation, backend, frontend" in capsys.readouterr().out


def test_docs_only_changes_run_documentation_without_component_checks() -> None:
    commands = check_project.verification_commands(check_project.select_checks(["README.md"]))

    assert len(commands) == 1
    assert commands[0].arguments[-1] == "scripts/check_documentation.py"
    assert commands[0].cwd.is_absolute()


def test_backend_checks_keep_fast_coverage_and_frontend_changes_do_not_run_backend_tests() -> None:
    backend_commands = check_project.verification_commands(
        check_project.select_checks(["backend/tests/domain/test_aggregation.py"])
    )
    frontend_commands = check_project.verification_commands(
        check_project.select_checks(["frontend/src/view.vue"])
    )

    assert any(
        command.arguments[-3:] == ("scripts/run_tests.py", "fast", "--coverage")
        for command in backend_commands
    )
    assert all("scripts/run_tests.py" not in command.arguments for command in frontend_commands)
    assert any(command.arguments == ("npm", "run", "check") for command in frontend_commands)


def test_dry_run_works_from_unrelated_directory_without_starting_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = Mock(side_effect=AssertionError("dry runs must not execute checks"))
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.chdir(tmp_path)

    assert check_project.main(["--dry-run", "frontend/src/view.vue"]) == 0

    assert not run.called
    output = capsys.readouterr().out
    assert "documentation, frontend" in output
    assert "Reason:" in output
    assert "npm run check" in output


def test_failed_command_returns_failure_and_does_not_start_later_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock(side_effect=[subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 7)])
    monkeypatch.setattr(subprocess, "run", run)

    assert check_project.main(["frontend/src/view.vue"]) == 7

    assert run.call_count == 2
    assert all(call.kwargs["cwd"].is_absolute() for call in run.call_args_list)
    assert all("shell" not in call.kwargs for call in run.call_args_list)


def test_unavailable_command_fails_without_starting_remaining_checks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = Mock(side_effect=FileNotFoundError("verification executable missing"))
    monkeypatch.setattr(subprocess, "run", run)

    assert check_project.main(["--full"]) == 1

    assert run.call_count == 1
    assert "Could not start check" in capsys.readouterr().err


def test_hook_filename_that_looks_like_an_option_cannot_disable_verification(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(subprocess, "run", run)

    assert check_project.main(["--", "--dry-run"]) == 0

    assert run.call_count > 1
    assert "unknown ownership: --dry-run" in capsys.readouterr().out
