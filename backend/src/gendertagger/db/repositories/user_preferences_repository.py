"""SQLAlchemy repository for account-owned presentation preferences."""

from uuid import UUID

from sqlalchemy.orm import Session

from gendertagger.db.rows.user_preferences import UserPreferencesRow
from gendertagger.models.user_preferences import UserPreferences


class SqlAlchemyUserPreferencesRepository:
    """Map explicit preferences columns to contracts within the caller's transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_preferences(self, user_id: UUID) -> UserPreferences | None:
        """Read saved preferences without initializing absent account state."""
        row = self._session.get(UserPreferencesRow, user_id)
        if row is None:
            return None
        return UserPreferences(
            locale=row.locale,
            theme=row.theme,
            desktop_sidebar_collapsed=row.desktop_sidebar_collapsed,
            interface_mode=row.interface_mode,
            revision=row.revision,
        )

    def save_preferences(self, user_id: UUID, preferences: UserPreferences) -> None:
        """Flush a complete resource after the caller locks its user and checks the revision.

        The parent-user lock also serializes insertion when no preferences row exists yet.
        This repository never acquires an independent transaction or commits the caller's work.
        """
        row = self._session.get(UserPreferencesRow, user_id)
        if row is None:
            row = UserPreferencesRow(user_id=user_id)
            self._session.add(row)
        row.locale = preferences.locale
        row.theme = preferences.theme
        row.desktop_sidebar_collapsed = preferences.desktop_sidebar_collapsed
        row.interface_mode = preferences.interface_mode
        row.revision = preferences.revision
        self._session.flush()
