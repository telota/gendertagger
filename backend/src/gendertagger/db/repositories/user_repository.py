"""SQLAlchemy repository for provider-neutral users and global roles."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from gendertagger.db.rows.users import UserRoleRow, UserRow
from gendertagger.models.user import GlobalRole, User, UserCreate


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

    def lock_active_administrator_ids(self) -> set[UUID]:
        """Lock every active administrator before validating a role-state change.

        Locking this complete set serializes mutations that could remove the final active
        administrator. PostgreSQL re-evaluates the query after a concurrent transaction releases
        its lock under ``READ COMMITTED``, so each waiter observes the previous committed mutation.
        """
        statement = (
            select(UserRow.id)
            .join(UserRoleRow, UserRoleRow.user_id == UserRow.id)
            .where(UserRow.is_active.is_(True), UserRoleRow.role == GlobalRole.admin)
            .with_for_update(of=UserRow)
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
