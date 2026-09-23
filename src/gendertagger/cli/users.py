"""Local-account user provisioning commands (ADR-0031)."""

from __future__ import annotations

import argparse
import json
import secrets
from argparse import _SubParsersAction
from datetime import UTC, datetime
from functools import partial
from uuid import UUID

from pydantic import JsonValue

from gendertagger.config.settings import DatabaseSettings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.auth import normalize_username, validate_local_password_length
from gendertagger.models.user import GlobalRole
from gendertagger.services.authentication import AuthenticationService, SessionLifetimePolicy
from gendertagger.services.password_hashing import Argon2PasswordHasher
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory


def add_parser(commands: _SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``users`` command group and its subcommands."""
    users = commands.add_parser("users", help="Provision local-account users (ADR-0031)")
    user_commands = users.add_subparsers(dest="user_command", required=True)
    create_user = user_commands.add_parser(
        "create", help="Admin-provision one local account, flagged for a forced password change"
    )
    create_user.add_argument("--display-name", required=True)
    create_user.add_argument("--username", required=True)
    create_user.add_argument(
        "--role",
        action="append",
        default=[],
        dest="roles",
        choices=sorted(role.value for role in GlobalRole),
        help=(
            "Repeatable global role (ADR-0033). Omit for a user who works only through project "
            "memberships; grant those with 'projects add-member'."
        ),
    )
    create_user.add_argument(
        "--password", help="Omit to generate and print a random initial password."
    )
    reset_password = user_commands.add_parser(
        "reset-password",
        help="Force a new password on an existing account and revoke its sessions",
    )
    reset_password.add_argument("--user-id", required=True, type=UUID)
    reset_password.add_argument("--password", help="Omit to generate and print a random password.")


def run(args: argparse.Namespace, settings: DatabaseSettings) -> str:
    """Provision or reset one local-account user (ADR-0031) and emit the result as JSON.

    Account provisioning is deliberately CLI-only: no v1 frontend screen manages users, so there
    is no HTTP surface for it. See ADR-0031.
    """
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    authentication_service = AuthenticationService(
        unit_of_work_factory=unit_of_work_factory,
        password_hasher=Argon2PasswordHasher(),
        clock=partial(datetime.now, UTC),
        # No session is issued by either command below; the lifetime policy is unused.
        session_lifetime=SessionLifetimePolicy(),
    )
    try:
        if args.user_command == "create":
            username = normalize_username(str(args.username))
            generated = args.password is None
            password = secrets.token_urlsafe(16) if generated else str(args.password)
            validate_local_password_length(password)
            user = authentication_service.create_local_account(
                display_name=str(args.display_name),
                roles={GlobalRole(role) for role in args.roles},
                username=username,
                password=password,
            )
            payload: dict[str, JsonValue] = {"user_id": str(user.id), "username": username}
        else:
            user_id = UUID(str(args.user_id))
            generated = args.password is None
            password = secrets.token_urlsafe(16) if generated else str(args.password)
            validate_local_password_length(password)
            authentication_service.reset_password(user_id=user_id, new_password=password)
            payload = {"user_id": str(user_id)}
        if generated:
            payload["generated_password"] = password
        return json.dumps(payload, sort_keys=True)
    finally:
        engine.dispose()
