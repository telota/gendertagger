"""SQLAlchemy repository for provider-neutral users and global roles."""

import hashlib
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from gendertagger.db.rows.users import UserRoleRow, UserRow
from gendertagger.models.user import GlobalRole, User, UserCreate

_ADMINISTRATOR_UPDATE_LOCK_CLASS_ID = 0x47454E44
_ADMINISTRATOR_UPDATE_LOCK_OBJECT_ID = 0x41444D49


class SqlAlchemyUserRepository:
    """Map user contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_user(self, command: UserCreate) -> User:
        """Persist and flush a user and its role memberships without committing."""
        row = UserRow(display_name=command.display_name, is_active=command.is_active)
        self._session.add(row)
        self._session.flush()
        self._session.add_all(
            [
                UserRoleRow(user_id=row.id, role=role)
                for role in sorted(command.roles, key=lambda role: role.value)
            ]
        )
        self._session.flush()
        return self._user_from_row(row, command.roles)

    def get_user(self, user_id: UUID) -> User | None:
        """Return a user contract by ID without exposing its row."""
        row = self._session.get(UserRow, user_id)
        if row is None:
            return None
        roles = set(
            self._session.scalars(select(UserRoleRow.role).where(UserRoleRow.user_id == user_id))
        )
        return self._user_from_row(row, roles)

    def lock_administrator_updates(self) -> None:
        """Acquire the stable transaction-scoped lock for local-account mutations."""
        self._session.execute(
            select(
                func.pg_advisory_xact_lock(
                    _ADMINISTRATOR_UPDATE_LOCK_CLASS_ID,
                    _ADMINISTRATOR_UPDATE_LOCK_OBJECT_ID,
                )
            )
        )

    def lock_membership_updates(self, user_id: UUID) -> None:
        """Acquire the stable transaction-scoped team-derived access lock for one user."""
        self._session.execute(select(func.pg_advisory_xact_lock(_membership_lock_key(user_id))))

    def get_active_administrator_ids(self) -> set[UUID]:
        """Return active global administrator IDs from the current transaction view."""
        statement = (
            select(UserRow.id)
            .join(UserRoleRow, UserRoleRow.user_id == UserRow.id)
            .where(UserRow.is_active.is_(True), UserRoleRow.role == GlobalRole.admin)
            .order_by(UserRow.id)
        )
        return set(self._session.scalars(statement))

    def get_user_for_update(self, user_id: UUID) -> User | None:
        """Return one user under a write lock, or ``None`` when absent."""
        row = self._session.get(UserRow, user_id, with_for_update=True)
        if row is None:
            return None
        roles = set(
            self._session.scalars(select(UserRoleRow.role).where(UserRoleRow.user_id == user_id))
        )
        return self._user_from_row(row, roles)

    def update_user(
        self,
        *,
        user_id: UUID,
        display_name: str,
        roles: set[GlobalRole],
        is_active: bool,
    ) -> User:
        """Replace mutable user fields while preserving identity and history."""
        row = self._session.get(UserRow, user_id, with_for_update=True)
        if row is None:
            msg = f"user {user_id} does not exist"
            raise LookupError(msg)
        row.display_name = display_name
        row.is_active = is_active
        self._session.execute(delete(UserRoleRow).where(UserRoleRow.user_id == user_id))
        self._session.add_all(
            [
                UserRoleRow(user_id=user_id, role=role)
                for role in sorted(roles, key=lambda role: role.value)
            ]
        )
        self._session.flush()
        return self._user_from_row(row, roles)

    @staticmethod
    def _user_from_row(row: UserRow, roles: set[GlobalRole]) -> User:
        return User(
            id=row.id,
            display_name=row.display_name,
            roles=roles,
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def _membership_lock_key(user_id: UUID) -> int:
    """Derive a stable signed advisory-lock key from one user UUID."""
    digest = hashlib.blake2b(user_id.bytes, digest_size=8, person=b"gendertagger").digest()
    return int.from_bytes(digest, byteorder="big", signed=True)
