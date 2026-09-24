"""Administrative team and direct-roster CLI commands (ADR-0041 slice 1)."""

from __future__ import annotations

import argparse
import json
from argparse import _SubParsersAction
from functools import partial

from gendertagger.config.settings import DatabaseSettings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.auth import normalize_username
from gendertagger.models.team import TeamCreate, TeamMemberAdd, TeamUpdate
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.teams import TeamService


def add_parser(commands: _SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``teams`` command group and its administrator break-glass subcommands."""
    teams = commands.add_parser("teams", help="Administer direct teams and memberships (ADR-0041)")
    team_commands = teams.add_subparsers(dest="team_command", required=True)

    list_teams = team_commands.add_parser("list", help="List direct teams")
    list_teams.add_argument("--query")
    list_teams.add_argument("--limit", type=int, default=100)
    list_teams.add_argument("--cursor")

    create = team_commands.add_parser("create", help="Create a direct-membership team")
    create.add_argument("--slug", required=True)
    create.add_argument("--display-name", required=True)

    rename = team_commands.add_parser("rename", help="Rename a team without changing its slug")
    rename.add_argument("--team", required=True, help="Canonical team slug.")
    rename.add_argument("--display-name", required=True)

    delete = team_commands.add_parser("delete", help="Delete an empty direct-membership team")
    delete.add_argument("--team", required=True, help="Canonical team slug.")

    list_members = team_commands.add_parser("list-members", help="List a team's direct members")
    list_members.add_argument("--team", required=True, help="Canonical team slug.")
    list_members.add_argument("--query")
    list_members.add_argument("--limit", type=int, default=100)
    list_members.add_argument("--cursor")

    add_member = team_commands.add_parser(
        "add-member", help="Add an active local account to a team"
    )
    add_member.add_argument("--team", required=True, help="Canonical team slug.")
    add_member.add_argument("--username", required=True)

    remove_member = team_commands.add_parser(
        "remove-member", help="Remove a direct team membership"
    )
    remove_member.add_argument("--team", required=True, help="Canonical team slug.")
    remove_member.add_argument("--username", required=True)


def run(args: argparse.Namespace, settings: DatabaseSettings) -> str:
    """Run a team command through the same application service used by the HTTP API."""
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    service = TeamService(unit_of_work_factory=unit_of_work_factory, cursor_codec=CursorCodec())
    try:
        if args.team_command == "list":
            return json.dumps(
                service.list_admin_teams(
                    query=args.query,
                    limit=args.limit,
                    cursor=args.cursor,
                ).model_dump(mode="json"),
                sort_keys=True,
            )
        if args.team_command == "create":
            return json.dumps(
                service.create_team(
                    TeamCreate(slug=args.slug, display_name=args.display_name),
                    actor_user_id=None,
                    request_id=None,
                ).model_dump(mode="json"),
                sort_keys=True,
            )

        team = service.get_team_by_slug(args.team)
        if team is None:
            msg = f"team {args.team!r} does not exist"
            raise ValueError(msg)
        if args.team_command == "rename":
            return json.dumps(
                service.update_team(
                    team.id,
                    TeamUpdate(display_name=args.display_name),
                    actor_user_id=None,
                    request_id=None,
                ).model_dump(mode="json"),
                sort_keys=True,
            )
        if args.team_command == "delete":
            service.delete_team(team.id, actor_user_id=None, request_id=None)
            return json.dumps({"team_id": str(team.id)}, sort_keys=True)
        if args.team_command == "list-members":
            return json.dumps(
                service.list_members(
                    team.id,
                    query=args.query,
                    limit=args.limit,
                    cursor=args.cursor,
                ).model_dump(mode="json"),
                sort_keys=True,
            )

        with unit_of_work_factory() as unit_of_work:
            credential = unit_of_work.auth.get_credential_by_username(
                normalize_username(str(args.username))
            )
        if credential is None:
            msg = f"user {args.username!r} does not exist"
            raise ValueError(msg)
        if args.team_command == "add-member":
            member, _ = service.add_member(
                team.id,
                TeamMemberAdd(user_id=credential.user_id),
                actor_user_id=None,
                request_id=None,
            )
            return json.dumps(member.model_dump(mode="json"), sort_keys=True)
        service.remove_member(
            team.id,
            credential.user_id,
            actor_user_id=None,
            request_id=None,
        )
        return json.dumps(
            {"team_id": str(team.id), "user_id": str(credential.user_id)}, sort_keys=True
        )
    finally:
        engine.dispose()
