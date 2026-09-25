"""Application repository contract for personal presentation preferences."""

from typing import Protocol
from uuid import UUID

from gendertagger.models.user_preferences import UserPreferences


class UserPreferencesRepository(Protocol):
    """Persist account-owned preferences without owning a transaction or resolving defaults."""

    def get_preferences(self, user_id: UUID) -> UserPreferences | None:
        """Return saved preferences or ``None`` without writing defaults."""
        ...

    def save_preferences(self, user_id: UUID, preferences: UserPreferences) -> None:
        """Flush a complete resource after the caller locks the user and checks its revision."""
        ...
