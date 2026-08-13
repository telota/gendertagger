"""Application repository contract for provider-neutral users."""

from typing import Protocol
from uuid import UUID

from gendertagger.models.user import User, UserCreate


class UserRepository(Protocol):
    """Persist attributable users without owning the transaction."""

    def add_user(self, command: UserCreate) -> User:
        """Persist a user and its global roles."""
        ...

    def get_user(self, user_id: UUID) -> User | None:
        """Return a user by ID, or ``None`` when absent."""
        ...
