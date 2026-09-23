"""Command-line provisioning for method lookup assets, local-account users, and project members."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from gendertagger.cli import assets, projects, users
from gendertagger.cli.settings import AssetCliSettings, UsersCliSettings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gendertagger")
    commands = parser.add_subparsers(dest="command", required=True)
    assets.add_parser(commands)
    users.add_parser(commands)
    projects.add_parser(commands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Provision assets, users, or project members and emit the result as one JSON line."""
    args = _build_parser().parse_args(argv)
    if args.command == "users":
        users_settings = UsersCliSettings()  # type: ignore[call-arg]  # Loaded from environment.
        payload = users.run(args, users_settings)
    elif args.command == "projects":
        projects_settings = UsersCliSettings()  # type: ignore[call-arg]  # Loaded from environment.
        payload = projects.run(args, projects_settings)
    else:
        settings = AssetCliSettings()  # type: ignore[call-arg]  # Loaded from environment.
        payload = assets.run(args, settings)
    sys.stdout.write(f"{payload}\n")
    return 0
