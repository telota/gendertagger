"""Application repository contract for local-account credentials and sessions (ADR-0031)."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.auth import LocalCredential, UserSession


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
        expires_at: datetime,
    ) -> None:
        """Persist a new session keyed by the hash of its bearer token."""
        ...

    def get_session(self, session_id: str) -> UserSession | None:
        """Return a session by its hashed token, or ``None`` when absent."""
        ...

    def revoke_session(self, session_id: str) -> None:
        """Mark one session revoked; a no-op if it does not exist or is already revoked."""
        ...

    def revoke_all_sessions(self, user_id: UUID) -> None:
        """Revoke every unrevoked session belonging to a user."""
        ...
