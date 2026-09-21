import subprocess
import sys
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_SNAPSHOT = _REPOSITORY_ROOT / "tests" / "fixtures" / "openapi-v1.json"
SNAPSHOT_SCRIPT = _REPOSITORY_ROOT / "scripts" / "update_openapi_snapshot.py"


def _run_snapshot_script(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- the interpreter and script paths are repository-controlled.
        [sys.executable, str(SNAPSHOT_SCRIPT), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_openapi_matches_committed_public_contract() -> None:
    # The script owns the one rendering of the contract; on drift its output names the fix.
    result = _run_snapshot_script("--check")

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("field", ["storage_uri", "task_id", "queue_name", "worker_metadata"])
def test_committed_public_contract_exposes_no_infrastructure_detail(field: str) -> None:
    assert field not in OPENAPI_SNAPSHOT.read_text(encoding="utf-8")


@pytest.mark.parametrize("committed", [None, "{}\n"])
def test_snapshot_check_rejects_a_missing_or_stale_snapshot_and_names_both_fixes(
    tmp_path: Path, committed: str | None
) -> None:
    if committed is not None:
        snapshot = tmp_path / "tests" / "fixtures" / "openapi-v1.json"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text(committed, encoding="utf-8")

    result = _run_snapshot_script("--check", "--root", str(tmp_path))

    assert result.returncode == 1
    assert "scripts/update_openapi_snapshot.py" in result.stdout
    assert "npm --prefix frontend run api:generate" in result.stdout


def test_snapshot_update_writes_the_committed_rendering(tmp_path: Path) -> None:
    result = _run_snapshot_script("--root", str(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    written = tmp_path / "tests" / "fixtures" / "openapi-v1.json"
    assert written.read_text(encoding="utf-8") == OPENAPI_SNAPSHOT.read_text(encoding="utf-8")
