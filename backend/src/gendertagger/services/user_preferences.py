"""Account-owned presentation preference reads and revision-checked writes (ADR-0043)."""

from uuid import UUID

from gendertagger.models.user import User
from gendertagger.models.user_preferences import UserPreferences, UserPreferencesUpdate
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory


class PreferencesAccountUnavailableError(RuntimeError):
    """Raised when the principal no longer owns an active local account."""


class PreferencesPasswordChangeRequiredError(RuntimeError):
    """Raised when the local account still owes a password change."""


class PreferencesRevisionConflictError(RuntimeError):
    """Raised when a preferences update carries a stale expected revision."""

    def __init__(self, *, expected_revision: int, current_revision: int) -> None:
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__(
            f"stale preferences revision {expected_revision}; current revision is {current_revision}"
        )


class UserPreferencesService:
    """Persist personal choices independently of sessions, projects, and scientific configuration.

    Callers supply the authenticated principal's ID. Each write locks the existing account before
    reading preferences, serializing first writes even when no preferences row exists yet.
    """

    def __init__(self, *, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def get_preferences(self, *, user_id: UUID) -> UserPreferences:
        """Return saved preferences or virtual defaults without initializing a row."""
        with self._unit_of_work_factory() as unit_of_work:
            _validate_local_account(unit_of_work, unit_of_work.users.get_user(user_id))
            stored = unit_of_work.user_preferences.get_preferences(user_id)
            return stored if stored is not None else UserPreferences()

    def update_preferences(
        self, command: UserPreferencesUpdate, *, user_id: UUID
    ) -> UserPreferences:
        """Apply supplied fields atomically; stale writes conflict even for unchanged values.

        Matching no-ops preserve the revision and never materialize virtual defaults. Changed writes
        advance the revision once and return the canonical resource only after a confirmed commit.
        """
        with self._unit_of_work_factory() as unit_of_work:
            _validate_local_account(unit_of_work, unit_of_work.users.get_user_for_update(user_id))
            stored = unit_of_work.user_preferences.get_preferences(user_id)
            current = stored if stored is not None else UserPreferences()
            if command.expected_revision != current.revision:
                raise PreferencesRevisionConflictError(
                    expected_revision=command.expected_revision,
                    current_revision=current.revision,
                )
            values = current.model_dump()
            values.update(command.model_dump(exclude_unset=True, exclude={"expected_revision"}))
            proposed = UserPreferences.model_validate(values)
            if proposed != current:
                values["revision"] = current.revision + 1
                proposed = UserPreferences.model_validate(values)
                unit_of_work.user_preferences.save_preferences(user_id, proposed)
            unit_of_work.commit()
            return proposed


def _validate_local_account(unit_of_work: UnitOfWork, user: User | None) -> None:
    """Freshly enforce active local-account ownership and password eligibility."""
    if user is None or not user.is_active:
        raise PreferencesAccountUnavailableError("An active local account is required.")
    credential = unit_of_work.auth.get_credential(user.id)
    if credential is None:
        raise PreferencesAccountUnavailableError("An active local account is required.")
    if credential.must_change_password:
        raise PreferencesPasswordChangeRequiredError(
            "The password must be changed before continuing."
        )
