"""Project-membership administration commands (ADR-0033)."""

from __future__ import annotations

import argparse
import json
from argparse import _SubParsersAction
from functools import partial

from gendertagger.config.settings import DatabaseSettings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.auth import normalize_username
from gendertagger.models.user import ProjectRole
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.project_access import ProjectAccessService


def add_parser(commands: _SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``projects`` command group and its subcommands."""
    projects = commands.add_parser("projects", help="Administer project memberships (ADR-0033)")
    project_commands = projects.add_subparsers(dest="project_command", required=True)
    add_member = project_commands.add_parser(
        "add-member", help="Grant a local-account user a role in a project, or change it"
    )
    add_member.add_argument("--project", required=True, help="Project slug.")
    add_member.add_argument("--username", required=True)
    add_member.add_argument("--role", required=True, choices=[role.value for role in ProjectRole])
    remove_member = project_commands.add_parser(
        "remove-member", help="Revoke a local-account user's membership in a project"
    )
    remove_member.add_argument("--project", required=True, help="Project slug.")
    remove_member.add_argument("--username", required=True)
    list_members = project_commands.add_parser("list-members", help="List a project's members")
    list_members.add_argument("--project", required=True, help="Project slug.")


def run(args: argparse.Namespace, settings: DatabaseSettings) -> str:
    """Grant, revoke, or list project memberships (ADR-0033) and emit the result as JSON.

    Projects are addressed by slug and members by local-account username. The admin-only
    ``/api/v1/projects/{project_id}/members`` endpoints offer the same operations over HTTP.
    """
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    access_service = ProjectAccessService(
        unit_of_work_factory=unit_of_work_factory,
        cursor_codec=CursorCodec(),
    )
    try:
        with unit_of_work_factory() as unit_of_work:
            project = unit_of_work.projects.get_project_by_slug(str(args.project))
            credential = (
                unit_of_work.auth.get_credential_by_username(normalize_username(str(args.username)))
                if args.project_command != "list-members"
                else None
            )
        if project is None:
            msg = f"project {args.project!r} does not exist"
            raise ValueError(msg)
        if args.project_command == "list-members":
            members = access_service.list_members(project.id)
            return json.dumps(
                [member.model_dump(mode="json") for member in members], sort_keys=True
            )
        if credential is None:
            msg = f"user {args.username!r} does not exist"
            raise ValueError(msg)
        if args.project_command == "add-member":
            member = access_service.set_member_role(
                project.id,
                credential.user_id,
                ProjectRole(args.role),
                actor_user_id=None,
            )
            return json.dumps(member.model_dump(mode="json"), sort_keys=True)
        access_service.remove_member(project.id, credential.user_id, actor_user_id=None)
        return json.dumps(
            {"project_id": str(project.id), "user_id": str(credential.user_id)}, sort_keys=True
        )
    finally:
        engine.dispose()
