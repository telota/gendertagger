"""SQLAlchemy repository for local-account credentials and sessions (ADR-0031)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from gendertagger.db.auth import UserCredentialRow, UserSessionRow
from gendertagger.models.auth import LocalCredential, UserSession
from gendertagger.services.persistence_errors import ResourceNotFoundError


class SqlAlchemyAuthRepository:
    """Map local-account credential and session contracts to rows within an owned session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_credential(
        self, *, user_id: UUID, username: str, password_hash: str
    ) -> LocalCredential:
        """Create the local credential for an existing user, flagged for a forced password change."""
        row = UserCredentialRow(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            must_change_password=True,
        )
        self._session.add(row)
        self._session.flush()
        return self._credential_from_row(row)

    def get_credential_by_username(self, username: str) -> LocalCredential | None:
        """Return the credential for a login identifier, or ``None`` when absent."""
        row = self._session.scalar(
            select(UserCredentialRow).where(UserCredentialRow.username == username)
        )
        return None if row is None else self._credential_from_row(row)

    def get_credential(self, user_id: UUID) -> LocalCredential | None:
        """Return the credential for a user ID, or ``None`` when the user has no local credential."""
        row = self._session.get(UserCredentialRow, user_id)
        return None if row is None else self._credential_from_row(row)

    def set_password(
        self, *, user_id: UUID, password_hash: str, must_change_password: bool
    ) -> None:
        """Replace a credential's password hash and forced-change flag."""
        row = self._session.get(UserCredentialRow, user_id)
        if row is None:
            msg = f"no local credential for user {user_id}"
            raise ResourceNotFoundError(msg)
        row.password_hash = password_hash
        row.must_change_password = must_change_password
        self._session.flush()

    def create_session(
        self,
        *,
        session_id: str,
        user_id: UUID,
        csrf_secret: str,
        expires_at: datetime,
    ) -> None:
        """Persist a new session keyed by the hash of its bearer token."""
        self._session.add(
            UserSessionRow(
                id=session_id,
                user_id=user_id,
                csrf_secret=csrf_secret,
                expires_at=expires_at,
            )
        )
        self._session.flush()

    def get_session(self, session_id: str) -> UserSession | None:
        """Return a session by its hashed token, or ``None`` when absent."""
        row = self._session.get(UserSessionRow, session_id)
        return None if row is None else self._session_from_row(row)

    def revoke_session(self, session_id: str) -> None:
        """Mark one session revoked; a no-op if it does not exist or is already revoked."""
        self._session.execute(
            update(UserSessionRow)
            .where(UserSessionRow.id == session_id, UserSessionRow.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )

    def revoke_all_sessions(self, user_id: UUID) -> None:
        """Revoke every unrevoked session belonging to a user."""
        self._session.execute(
            update(UserSessionRow)
            .where(UserSessionRow.user_id == user_id, UserSessionRow.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )

    @staticmethod
    def _credential_from_row(row: UserCredentialRow) -> LocalCredential:
        return LocalCredential(
            user_id=row.user_id,
            username=row.username,
            password_hash=row.password_hash,
            must_change_password=row.must_change_password,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _session_from_row(row: UserSessionRow) -> UserSession:
        return UserSession(
            user_id=row.user_id,
            csrf_secret=row.csrf_secret,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )
