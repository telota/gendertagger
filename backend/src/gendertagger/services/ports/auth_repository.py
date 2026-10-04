"""Application repository contract for local-account credentials and sessions."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.auth import AdminUser, LocalCredential, UserSession


@dataclass(frozen=True, slots=True)
class AdminUserCursor:
    """Stable keyset position in the username-ordered local-account directory."""

    username: str
    user_id: UUID


class AuthRepository(Protocol):
    """Persist local-account credentials and sessions without owning the transaction."""

    def add_credential(
        self, *, user_id: UUID, username: str, password_hash: str
    ) -> LocalCredential:
        """Create the local credential for an existing user, flagged for a forced password change."""
        ...

    def get_credential_by_username(self, username: str) -> LocalCredential | None:
        """Return the credential for a login identifier, or ``None`` when absent."""
        ...

    def get_credential(self, user_id: UUID) -> LocalCredential | None:
        """Return the credential for a user ID, or ``None`` when the user has no local credential."""
        ...

    def get_credential_for_update(self, user_id: UUID) -> LocalCredential | None:
        """Reread a credential under a write lock after locking its owning user.

        Refresh any previously loaded credential so a transaction waiting for an account lock
        cannot verify or replace a password using stale state. The lock lasts until transaction
        completion; return ``None`` for a user without a local credential.
        """
        ...

    def list_admin_users(
        self,
        *,
        search: str | None,
        limit: int,
        after: AdminUserCursor | None,
    ) -> Sequence[AdminUser]:
        """Return one username-ordered keyset slice of local accounts."""
        ...

    def set_password(
        self, *, user_id: UUID, password_hash: str, must_change_password: bool
    ) -> None:
        """Replace a credential's password hash and forced-change flag."""
        ...

    def create_session(
        self,
        *,
        session_id: str,
        user_id: UUID,
        csrf_secret: str,
        keep_signed_in: bool,
        expires_at: datetime,
        absolute_expires_at: datetime,
    ) -> None:
        """Persist a new session keyed by the hash of its bearer token."""
        ...

    def get_session(self, session_id: str) -> UserSession | None:
        """Return a session by its hashed token, or ``None`` when absent."""
        ...

    def renew_session(self, session_id: str, *, expires_at: datetime) -> None:
        """Move an unrevoked session's idle expiry forward; never moves it backwards."""
        ...

    def revoke_session(self, session_id: str) -> None:
        """Mark one session revoked; a no-op if it does not exist or is already revoked."""
        ...

    def revoke_all_sessions(self, user_id: UUID) -> None:
        """Revoke every unrevoked session belonging to a user."""
        ...
