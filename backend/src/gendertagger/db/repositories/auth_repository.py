"""SQLAlchemy repository for local-account credentials and sessions (ADR-0031)."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from gendertagger.db.rows.auth import UserCredentialRow, UserSessionRow
from gendertagger.db.rows.users import UserRoleRow, UserRow
from gendertagger.models.auth import AdminUser, LocalCredential, UserSession
from gendertagger.models.user import GlobalRole
from gendertagger.services.ports.auth_repository import AdminUserCursor
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError


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

    def list_admin_users(
        self,
        *,
        search: str | None,
        limit: int,
        after: AdminUserCursor | None,
    ) -> Sequence[AdminUser]:
        """Return one username-ordered keyset slice of local accounts."""
        statement = select(UserRow, UserCredentialRow).join(
            UserCredentialRow,
            UserCredentialRow.user_id == UserRow.id,
        )
        if search is not None:
            statement = statement.where(
                or_(
                    UserCredentialRow.username.icontains(search, autoescape=True),
                    UserRow.display_name.icontains(search, autoescape=True),
                )
            )
        if after is not None:
            statement = statement.where(
                or_(
                    UserCredentialRow.username > after.username,
                    and_(
                        UserCredentialRow.username == after.username,
                        UserRow.id > after.user_id,
                    ),
                )
            )
        rows = self._session.execute(
            statement.order_by(UserCredentialRow.username, UserRow.id).limit(limit)
        ).all()
        user_ids = [user_row.id for user_row, _ in rows]
        roles_by_user_id: defaultdict[UUID, set[GlobalRole]] = defaultdict(set)
        if user_ids:
            for user_id, role in self._session.execute(
                select(UserRoleRow.user_id, UserRoleRow.role).where(
                    UserRoleRow.user_id.in_(user_ids)
                )
            ):
                roles_by_user_id[user_id].add(role)
        return tuple(
            AdminUser(
                id=user_row.id,
                display_name=user_row.display_name,
                username=credential_row.username,
                roles=roles_by_user_id[user_row.id],
                is_active=user_row.is_active,
                must_change_password=credential_row.must_change_password,
                created_at=user_row.created_at,
            )
            for user_row, credential_row in rows
        )

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
        keep_signed_in: bool,
        expires_at: datetime,
        absolute_expires_at: datetime,
    ) -> None:
        """Persist a new session keyed by the hash of its bearer token."""
        self._session.add(
            UserSessionRow(
                id=session_id,
                user_id=user_id,
                csrf_secret=csrf_secret,
                keep_signed_in=keep_signed_in,
                expires_at=expires_at,
                absolute_expires_at=absolute_expires_at,
            )
        )
        self._session.flush()

    def get_session(self, session_id: str) -> UserSession | None:
        """Return a session by its hashed token, or ``None`` when absent."""
        row = self._session.get(UserSessionRow, session_id)
        return None if row is None else self._session_from_row(row)

    def renew_session(self, session_id: str, *, expires_at: datetime) -> None:
        """Move an unrevoked session's idle expiry forward; never moves it backwards."""
        self._session.execute(
            update(UserSessionRow)
            .where(
                UserSessionRow.id == session_id,
                UserSessionRow.revoked_at.is_(None),
                UserSessionRow.expires_at < expires_at,
            )
            .values(expires_at=expires_at)
        )

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
            keep_signed_in=row.keep_signed_in,
            expires_at=row.expires_at,
            absolute_expires_at=row.absolute_expires_at,
            revoked_at=row.revoked_at,
        )
