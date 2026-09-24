"""Application use case for local-account authentication (ADR-0031, ADR-0032).

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
from gendertagger.models.user import CurrentUser, GlobalRole, User, UserCreate
from gendertagger.services.password_hashing import PasswordHasherProtocol
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

Clock = Callable[[], UtcDatetime]

_SESSION_TOKEN_BYTES = 32
_CSRF_SECRET_BYTES = 32
# An active session is written back at most once per interval rather than on every request.
_SESSION_RENEWAL_INTERVAL = timedelta(minutes=5)

DEFAULT_SESSION_IDLE = timedelta(hours=24)
DEFAULT_KEEP_SIGNED_IN_IDLE = timedelta(days=7)
DEFAULT_SESSION_MAX_LIFETIME = timedelta(days=30)


class InvalidCredentialsError(Exception):
    """Raised when a login attempt fails to verify."""


class InvalidCurrentPasswordError(Exception):
    """Raised when a password change presents the wrong current password."""


@dataclass(frozen=True)
class SessionLifetimePolicy:
    """Idle and absolute session limits (ADR-0032); every limit exceeds WCAG 2.2.1's 20 hours."""

    idle: timedelta = DEFAULT_SESSION_IDLE
    keep_signed_in_idle: timedelta = DEFAULT_KEEP_SIGNED_IN_IDLE
    max_lifetime: timedelta = DEFAULT_SESSION_MAX_LIFETIME

    def idle_for(self, *, keep_signed_in: bool) -> timedelta:
        """Return the idle limit for one kind of session."""
        return self.keep_signed_in_idle if keep_signed_in else self.idle


@dataclass(frozen=True)
class IssuedSession:
    """A newly created session's bearer token, CSRF secret, kind, limit, and owning principal."""

    token: str
    csrf_secret: str
    keep_signed_in: bool
    absolute_expires_at: UtcDatetime
    user: CurrentUser


@dataclass(frozen=True)
class ResolvedSession:
    """The state of one presented session, as needed by the request-authentication path."""

    user_id: UUID
    csrf_secret: str
    must_change_password: bool
    keep_signed_in: bool


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
        session_lifetime: SessionLifetimePolicy,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._password_hasher = password_hasher
        self._clock = clock
        self._session_lifetime = session_lifetime

    def login(self, *, username: str, password: str, keep_signed_in: bool = False) -> IssuedSession:
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
            now = self._clock()
            absolute_expires_at = now + self._session_lifetime.max_lifetime
            unit_of_work.auth.create_session(
                session_id=_hash_token(token),
                user_id=user.id,
                csrf_secret=csrf_secret,
                keep_signed_in=keep_signed_in,
                expires_at=min(
                    now + self._session_lifetime.idle_for(keep_signed_in=keep_signed_in),
                    absolute_expires_at,
                ),
                absolute_expires_at=absolute_expires_at,
            )
            unit_of_work.commit()
        return IssuedSession(
            token=token,
            csrf_secret=csrf_secret,
            keep_signed_in=keep_signed_in,
            absolute_expires_at=absolute_expires_at,
            user=CurrentUser(id=user.id, display_name=user.display_name, roles=user.roles),
        )

    def resolve_session(self, *, session_token: str) -> ResolvedSession | None:
        """Return the session behind a bearer token, or ``None`` if absent, expired, or revoked.

        A valid session's idle expiry slides forward with use, up to its absolute limit. The move is
        persisted only once it has advanced by at least ``_SESSION_RENEWAL_INTERVAL``, so an active
        session costs one write per interval rather than one per request.
        """
        session_id = _hash_token(session_token)
        with self._unit_of_work_factory() as unit_of_work:
            session = unit_of_work.auth.get_session(session_id)
            now = self._clock()
            if session is None or session.revoked_at is not None or session.expires_at <= now:
                return None
            credential = unit_of_work.auth.get_credential(session.user_id)
            renewed_expires_at = min(
                now + self._session_lifetime.idle_for(keep_signed_in=session.keep_signed_in),
                session.absolute_expires_at,
            )
            if renewed_expires_at - session.expires_at >= _SESSION_RENEWAL_INTERVAL:
                unit_of_work.auth.renew_session(session_id, expires_at=renewed_expires_at)
                unit_of_work.commit()
        return ResolvedSession(
            user_id=session.user_id,
            csrf_secret=session.csrf_secret,
            must_change_password=credential is not None and credential.must_change_password,
            keep_signed_in=session.keep_signed_in,
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
                raise InvalidCurrentPasswordError
            unit_of_work.auth.set_password(
                user_id=user_id,
                password_hash=self._password_hasher.hash(new_password),
                must_change_password=False,
            )
            unit_of_work.commit()

    def create_local_account(
        self, *, display_name: str, roles: set[GlobalRole], username: str, password: str
    ) -> User:
        """Provision one admin-created local account through a caller-owned interface."""
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
            self.reset_password_in_transaction(
                unit_of_work=unit_of_work,
                user_id=user_id,
                new_password=new_password,
            )
            unit_of_work.commit()

    def reset_password_in_transaction(
        self, *, unit_of_work: UnitOfWork, user_id: UUID, new_password: str
    ) -> None:
        """Apply a password reset using a transaction owned by the calling service."""
        unit_of_work.auth.set_password(
            user_id=user_id,
            password_hash=self._password_hasher.hash(new_password),
            must_change_password=True,
        )
        unit_of_work.auth.revoke_all_sessions(user_id)
