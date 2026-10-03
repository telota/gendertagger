"""Collection smoke tests for explicit PostgreSQL rollback isolation opt-ins."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
pytest_plugins = ("pytester",)


def _collect_module(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, source: str
) -> pytest.RunResult:
    """Exercise real collection hooks in pytester's isolated configuration and module scope."""
    module = pytester.makepyfile(test_rollback_contract="import pytest\n\n" + dedent(source))
    monkeypatch.delenv("GENDERTAGGER_TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("GENDERTAGGER_TEST_REDIS_URL", raising=False)
    # These collection-only cases require the repository plugin, not third-party runtime plugins.
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    return pytester.runpytest_inprocess(
        "-p",
        "tests.conftest",
        "-c",
        str(_BACKEND_ROOT / "pyproject.toml"),
        "--collect-only",
        "-q",
        str(module),
    )


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        pytest.param(
            """
            pytestmark = [pytest.mark.postgres, pytest.mark.postgres_rollback]

            def test_case(db_session):
                raise AssertionError("test body must not run during collection")
            """,
            "must be applied to each audited test, not a module or class",
            id="inherited-module-opt-in",
        ),
        pytest.param(
            """
            pytestmark = [pytest.mark.postgres, pytest.mark.postgres_rollback]

            @pytest.mark.postgres_rollback
            def test_case(db_session):
                raise AssertionError("test body must not run during collection")
            """,
            "must be applied to each audited test, not a module or class",
            id="function-opt-in-cannot-hide-inherited-marker",
        ),
        pytest.param(
            """
            pytestmark = [pytest.mark.postgres, pytest.mark.postgres_rollback(audited=True)]

            @pytest.mark.postgres_rollback
            def test_case(db_session):
                raise AssertionError("test body must not run during collection")
            """,
            "does not accept arguments",
            id="function-opt-in-cannot-hide-inherited-arguments",
        ),
        pytest.param(
            """
            @pytest.mark.postgres
            @pytest.mark.postgres_rollback
            class TestInherited:
                def test_case(self, db_session):
                    raise AssertionError("test body must not run during collection")
            """,
            "must be applied to each audited test, not a module or class",
            id="inherited-class-opt-in",
        ),
        pytest.param(
            """
            @pytest.mark.postgres_rollback
            def test_case(db_session):
                raise AssertionError("test body must not run during collection")
            """,
            "requires the postgres marker",
            id="missing-postgres-marker",
        ),
        pytest.param(
            """
            @pytest.mark.postgres
            @pytest.mark.postgres_rollback
            def test_case():
                raise AssertionError("test body must not run during collection")
            """,
            "requires the provided db_session fixture",
            id="missing-db-session",
        ),
        pytest.param(
            """
            @pytest.mark.postgres
            @pytest.mark.postgres_rollback
            @pytest.mark.redis
            def test_case(db_session):
                raise AssertionError("test body must not run during collection")
            """,
            "cannot be combined with Redis or a separate unit-of-work fixture",
            id="redis-combination",
        ),
        pytest.param(
            """
            @pytest.mark.postgres
            @pytest.mark.postgres_rollback
            def test_case(db_session, postgres_unit_of_work):
                raise AssertionError("test body must not run during collection")
            """,
            "cannot be combined with Redis or a separate unit-of-work fixture",
            id="separate-unit-of-work",
        ),
        pytest.param(
            """
            @pytest.mark.postgres
            @pytest.mark.postgres_rollback("audited")
            def test_case(db_session):
                raise AssertionError("test body must not run during collection")
            """,
            "does not accept arguments",
            id="marker-positional-argument",
        ),
        pytest.param(
            """
            @pytest.mark.postgres
            @pytest.mark.postgres_rollback(audited=True)
            def test_case(db_session):
                raise AssertionError("test body must not run during collection")
            """,
            "does not accept arguments",
            id="marker-keyword-argument",
        ),
    ],
)
def test_invalid_rollback_opt_in_fails_before_fixture_setup(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, source: str, reason: str
) -> None:
    result = _collect_module(pytester, monkeypatch, source)
    output = result.stdout.str() + result.stderr.str()

    assert result.ret == pytest.ExitCode.USAGE_ERROR, output
    assert f"postgres_rollback {reason}" in output
    assert "::test_case: postgres_rollback" in output
    assert "Unknown pytest.mark" not in output
    assert "fixture 'db_session' not found" not in output


def test_function_level_rollback_opt_in_collects_without_running_services(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _collect_module(
        pytester,
        monkeypatch,
        """
        @pytest.fixture(autouse=True)
        def fixture_setup_must_not_run():
            raise AssertionError("fixture setup must not run during collection")

        @pytest.mark.postgres
        @pytest.mark.postgres_rollback
        def test_case(db_session):
            raise AssertionError("test body must not run during collection")
        """,
    )
    output = result.stdout.str() + result.stderr.str()

    assert result.ret == pytest.ExitCode.OK, output
    assert "::test_case" in output
    assert "1 test collected" in output
    assert "Ordinary test profiles: core=0, postgres=1, redis=0" in output
    assert "fixture setup must not run during collection" not in output


@pytest.mark.parametrize("valid", [False, True])
def test_collection_policy_loads_in_a_fresh_process_without_running_services(
    tmp_path: Path, valid: bool
) -> None:
    """Keep real interpreter/bootstrap coverage alongside the faster in-process policy matrix."""
    module = tmp_path / "test_fresh_collection.py"
    parameters = "db_session" if valid else ""
    module.write_text(
        dedent(
            """
            import pytest
            pytestmark = [pytest.mark.postgres]

            @pytest.fixture(autouse=True)
            def fixture_setup_must_not_run():
                raise AssertionError("fixture setup must not run during collection")
            """
        )
        + f"\n@pytest.mark.postgres_rollback\ndef test_case({parameters}):\n"
        + '    raise AssertionError("test body must not run during collection")\n',
        encoding="utf-8",
    )
    environment = os.environ.copy()
    for name in ("GENDERTAGGER_TEST_DATABASE_URL", "GENDERTAGGER_TEST_REDIS_URL", "PYTEST_ADDOPTS"):
        environment.pop(name, None)
    result = subprocess.run(  # noqa: S603 -- the interpreter, plugin and generated paths are test-owned.
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tests.conftest",
            "-c",
            str(_BACKEND_ROOT / "pyproject.toml"),
            "--collect-only",
            "-q",
            str(module),
        ],
        cwd=_BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout + result.stderr
    expected_exit = pytest.ExitCode.OK if valid else pytest.ExitCode.USAGE_ERROR
    assert result.returncode == expected_exit, output
    assert "fixture setup must not run during collection" not in output
    assert "test body must not run during collection" not in output
    if valid:
        assert "1 test collected" in output
        assert "Ordinary test profiles: core=0, postgres=1, redis=0" in output
    else:
        assert "postgres_rollback requires the provided db_session fixture" in output
