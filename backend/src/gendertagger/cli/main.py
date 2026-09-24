"""Command-line provisioning for assets, accounts, project members, and direct teams."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from gendertagger.cli import assets, projects, teams, users
from gendertagger.cli.settings import AssetCliSettings
from gendertagger.config.settings import DatabaseSettings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gendertagger")
    commands = parser.add_subparsers(dest="command", required=True)
    assets.add_parser(commands)
    users.add_parser(commands)
    projects.add_parser(commands)
    teams.add_parser(commands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Provision assets, accounts, project members, or direct teams as one JSON line."""
    args = _build_parser().parse_args(argv)
    if args.command == "users":
        users_settings = DatabaseSettings()  # type: ignore[call-arg]  # Loaded from environment.
        payload = users.run(args, users_settings)
    elif args.command == "teams":
        teams_settings = DatabaseSettings()  # type: ignore[call-arg]  # Loaded from environment.
        payload = teams.run(args, teams_settings)
    elif args.command == "projects":
        projects_settings = DatabaseSettings()  # type: ignore[call-arg]  # Loaded from environment.
        payload = projects.run(args, projects_settings)
    else:
        settings = AssetCliSettings()  # type: ignore[call-arg]  # Loaded from environment.
        payload = assets.run(args, settings)
    sys.stdout.write(f"{payload}\n")
    return 0
