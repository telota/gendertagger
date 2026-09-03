"""Application use case for local-account authentication (ADR-0031).

Issuing, resolving, and revoking sessions is deliberately separate from the transport-facing
``AuthenticationBackend`` protocol in ``gendertagger.api.authentication``: this service is plain,
FastAPI-free application logic, and the API layer adapts it to the protocol.
"""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from gendertagger.models.common import UtcDatetime
from gendertagger.models.user import CurrentUser, Role, User, UserCreate
from gendertagger.services.password_hashing import PasswordHasherProtocol
from gendertagger.services.unit_of_work import UnitOfWorkFactory

Clock = Callable[[], UtcDatetime]

_SESSION_TOKEN_BYTES = 32
_CSRF_SECRET_BYTES = 32


class InvalidCredentialsError(Exception):
    """Raised when a login attempt or a password change fails to verify."""


@dataclass(frozen=True)
class IssuedSession:
    """A newly created session's bearer token, CSRF secret, and owning principal."""

    token: str
    csrf_secret: str
    user: CurrentUser


@dataclass(frozen=True)
class ResolvedSession:
    """The state of one presented session, as needed by the request-authentication path."""

    user_id: UUID
    csrf_secret: str
    must_change_password: bool


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class AuthenticationService:
    """Issue, resolve, and revoke local-account sessions; provision and reset credentials."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        password_hasher: PasswordHasherProtocol,
        clock: Clock,
        session_ttl: timedelta,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._password_hasher = password_hasher
        self._clock = clock
        self._session_ttl = session_ttl

    def login(self, *, username: str, password: str) -> IssuedSession:
        """Verify credentials and issue a new session, or raise ``InvalidCredentialsError``."""
        with self._unit_of_work_factory() as unit_of_work:
            credential = unit_of_work.auth.get_credential_by_username(username)
            if credential is None:
                # Hash anyway so a nonexistent username does not respond measurably faster.
                self._password_hasher.hash(password)
                raise InvalidCredentialsError
            user = unit_of_work.users.get_user(credential.user_id)
            if (
                user is None
                or not user.is_active
                or not self._password_hasher.verify(credential.password_hash, password)
            ):
                raise InvalidCredentialsError
            token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
            csrf_secret = secrets.token_urlsafe(_CSRF_SECRET_BYTES)
            unit_of_work.auth.create_session(
                session_id=_hash_token(token),
                user_id=user.id,
                csrf_secret=csrf_secret,
                expires_at=self._clock() + self._session_ttl,
            )
            unit_of_work.commit()
        return IssuedSession(
            token=token,
            csrf_secret=csrf_secret,
            user=CurrentUser(id=user.id, display_name=user.display_name, roles=user.roles),
        )

    def resolve_session(self, *, session_token: str) -> ResolvedSession | None:
        """Return the session behind a bearer token, or ``None`` if absent, expired, or revoked."""
        with self._unit_of_work_factory() as unit_of_work:
            session = unit_of_work.auth.get_session(_hash_token(session_token))
            if (
                session is None
                or session.revoked_at is not None
                or session.expires_at <= self._clock()
            ):
                return None
            credential = unit_of_work.auth.get_credential(session.user_id)
        return ResolvedSession(
            user_id=session.user_id,
            csrf_secret=session.csrf_secret,
            must_change_password=credential is not None and credential.must_change_password,
        )

    def logout(self, *, session_token: str) -> None:
        """Revoke the session identified by a bearer token."""
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.auth.revoke_session(_hash_token(session_token))
            unit_of_work.commit()

    def change_password(self, *, user_id: UUID, current_password: str, new_password: str) -> None:
        """Verify the current password, set a new one, and clear the forced-change flag."""
        with self._unit_of_work_factory() as unit_of_work:
            credential = unit_of_work.auth.get_credential(user_id)
            if credential is None or not self._password_hasher.verify(
                credential.password_hash, current_password
            ):
                raise InvalidCredentialsError
            unit_of_work.auth.set_password(
                user_id=user_id,
                password_hash=self._password_hasher.hash(new_password),
                must_change_password=False,
            )
            unit_of_work.commit()

    def create_local_account(
        self, *, display_name: str, roles: set[Role], username: str, password: str
    ) -> User:
        """Provision one admin-created local account. CLI-only; see ADR-0031."""
        with self._unit_of_work_factory() as unit_of_work:
            user = unit_of_work.users.add_user(
                UserCreate(display_name=display_name, roles=roles, is_active=True)
            )
            unit_of_work.auth.add_credential(
                user_id=user.id,
                username=username,
                password_hash=self._password_hasher.hash(password),
            )
            unit_of_work.commit()
        return user

    def reset_password(self, *, user_id: UUID, new_password: str) -> None:
        """Admin action: set a new password, re-flag it forced, and revoke every session."""
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.auth.set_password(
                user_id=user_id,
                password_hash=self._password_hasher.hash(new_password),
                must_change_password=True,
            )
            unit_of_work.auth.revoke_all_sessions(user_id)
            unit_of_work.commit()
