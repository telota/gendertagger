"""Application repository contract for provider-neutral users."""

from collections.abc import Collection
from typing import Protocol
from uuid import UUID

from gendertagger.models.user import GlobalRole, User, UserCreate


class UserRepository(Protocol):
    """Persist attributable users without owning the transaction."""

    def add_user(self, command: UserCreate) -> User:
        """Persist a user and its global roles."""
        ...

    def get_user(self, user_id: UUID) -> User | None:
        """Return a user by ID, or ``None`` when absent."""
        ...

    def lock_active_administrator_ids(self) -> Collection[UUID]:
        """Lock and return every currently active global administrator."""
        ...

    def get_user_for_update(self, user_id: UUID) -> User | None:
        """Return one user under a write lock, or ``None`` when absent."""
        ...

    def update_user(
        self,
        *,
        user_id: UUID,
        display_name: str,
        roles: set[GlobalRole],
        is_active: bool,
    ) -> User:
        """Replace mutable user fields while preserving identity and history."""
        ...
