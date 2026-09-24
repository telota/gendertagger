"""Project-membership and manager break-glass commands (ADR-0041)."""

from __future__ import annotations

import argparse
import json
from argparse import _SubParsersAction
from functools import partial

from gendertagger.config.settings import DatabaseSettings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.auth import normalize_username
from gendertagger.models.project import ProjectManagerUpdate
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
    set_manager = project_commands.add_parser(
        "set-manager", help="Transfer a project's manager without changing project roles"
    )
    set_manager.add_argument("--project", required=True, help="Project slug.")
    set_manager.add_argument("--username", required=True, help="New manager username.")
    set_manager.add_argument(
        "--expected-manager-username",
        required=True,
        help="Current manager username, used to reject stale transfers.",
    )


def run(args: argparse.Namespace, settings: DatabaseSettings) -> str:
    """Operate on team-eligible project memberships and managers through application services."""
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
                if args.project_command not in {"list-members"}
                else None
            )
            expected_manager_credential = (
                unit_of_work.auth.get_credential_by_username(
                    normalize_username(str(args.expected_manager_username))
                )
                if args.project_command == "set-manager"
                else None
            )
        if project is None:
            msg = f"project {args.project!r} does not exist"
            raise ValueError(msg)
        if args.project_command == "list-members":
            state = access_service.list_members(project.id)
            return json.dumps(state.model_dump(mode="json"), sort_keys=True)
        if credential is None:
            msg = f"user {args.username!r} does not exist"
            raise ValueError(msg)
        if args.project_command == "set-manager":
            if expected_manager_credential is None:
                msg = f"user {args.expected_manager_username!r} does not exist"
                raise ValueError(msg)
            state = access_service.transfer_manager(
                project.id,
                ProjectManagerUpdate(
                    manager_user_id=credential.user_id,
                    expected_manager_user_id=expected_manager_credential.user_id,
                ),
                actor_user_id=None,
            )
            return json.dumps(state.model_dump(mode="json"), sort_keys=True)
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
