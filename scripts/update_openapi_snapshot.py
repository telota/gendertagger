"""Render the live /api/v1 OpenAPI document into the committed contract snapshot.

`tests/fixtures/openapi-v1.json` pins the public contract. The contract test runs this script with
`--check`, and the frontend generates its transport types from the snapshot, so a contract change is
two commands: this script, then `npm --prefix frontend run api:generate`.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import SecretStr

from gendertagger.api.app import create_app
from gendertagger.api.settings import AppSettings
from gendertagger.services.unit_of_work import UnitOfWork

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = Path("tests/fixtures/openapi-v1.json")
UPDATE_COMMAND = "uv run --locked python scripts/update_openapi_snapshot.py"
FRONTEND_COMMAND = "npm --prefix frontend run api:generate"

# Rendering needs valid settings but never opens persistence, so these placeholders reach nothing.
_PLACEHOLDER_SETTINGS = AppSettings(
    database_url=SecretStr("postgresql+psycopg://api:secret@localhost/gendertagger"),
    code_git_commit="a" * 40,
    dependency_lock_sha256="b" * 64,
)


def _unused_unit_of_work_factory() -> UnitOfWork:
    msg = "OpenAPI generation must not open persistence"
    raise AssertionError(msg)


def render_openapi_snapshot() -> str:
    """Return the deterministic JSON rendering of the public OpenAPI document."""
    application = create_app(
        settings=_PLACEHOLDER_SETTINGS,
        unit_of_work_factory=_unused_unit_of_work_factory,
    )
    return json.dumps(application.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Write the snapshot, or with ``--check`` fail when the committed one is stale."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed snapshot differs from the live contract instead of writing it.",
    )
    args = parser.parse_args(argv)

    snapshot = args.root / SNAPSHOT_PATH
    rendered = render_openapi_snapshot()

    if args.check:
        committed = snapshot.read_text(encoding="utf-8") if snapshot.is_file() else None
        if committed != rendered:
            print(
                f"{SNAPSHOT_PATH} does not match the live /api/v1 OpenAPI document.\n"
                f"Run `{UPDATE_COMMAND}`, review the diff as a public contract change, "
                f"then run `{FRONTEND_COMMAND}`."
            )
            return 1
        print("OpenAPI snapshot matches the live /api/v1 contract.")
        return 0

    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(rendered, encoding="utf-8")
    print(f"Wrote {SNAPSHOT_PATH}. Review the diff, then run `{FRONTEND_COMMAND}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
