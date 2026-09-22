"""SQLAlchemy repository for provider-neutral users and global roles."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gendertagger.db.reviews import UserRoleRow, UserRow
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
