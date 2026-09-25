"""Authenticated self-service presentation preferences (ADR-0043)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from gendertagger.api.authentication import require_password_current
from gendertagger.api.dependencies import get_user_preferences_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.user import CurrentUser
from gendertagger.models.user_preferences import UserPreferences, UserPreferencesUpdate
from gendertagger.services.user_preferences import (
    PreferencesAccountUnavailableError,
    PreferencesPasswordChangeRequiredError,
    PreferencesRevisionConflictError,
    UserPreferencesService,
)

router = APIRouter(tags=["user preferences"])


@router.get("/me/preferences", response_model=UserPreferences)
def get_user_preferences(
    response: Response,
    service: Annotated[UserPreferencesService, Depends(get_user_preferences_service)],
    current_user: Annotated[CurrentUser, Depends(require_password_current)],
) -> UserPreferences:
    """Return only the resolved account's saved preferences or virtual defaults."""
    try:
        result = service.get_preferences(user_id=current_user.id)
    except (PreferencesAccountUnavailableError, PreferencesPasswordChangeRequiredError) as error:
        raise _account_error(error) from error
    response.headers["Cache-Control"] = "no-store"
    return result


@router.patch("/me/preferences", response_model=UserPreferences)
def update_user_preferences(
    command: UserPreferencesUpdate,
    response: Response,
    service: Annotated[UserPreferencesService, Depends(get_user_preferences_service)],
    current_user: Annotated[CurrentUser, Depends(require_password_current)],
) -> UserPreferences:
    """Save an explicit partial update for the authenticated account under its revision."""
    try:
        result = service.update_preferences(command, user_id=current_user.id)
    except (PreferencesAccountUnavailableError, PreferencesPasswordChangeRequiredError) as error:
        raise _account_error(error) from error
    except PreferencesRevisionConflictError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="preferences_revision_conflict",
            message="The user preferences have changed.",
            details={
                "expected_revision": error.expected_revision,
                "current_revision": error.current_revision,
            },
            headers={"Cache-Control": "no-store"},
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return result


def _account_error(
    error: PreferencesAccountUnavailableError | PreferencesPasswordChangeRequiredError,
) -> ApiRequestError:
    """Map fresh account eligibility failures to the existing authentication envelope."""
    if isinstance(error, PreferencesPasswordChangeRequiredError):
        return ApiRequestError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="password_change_required",
            message="The password must be changed before continuing.",
            headers={"Cache-Control": "no-store"},
        )
    return ApiRequestError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="authentication_required",
        message="Authentication is required.",
        headers={"WWW-Authenticate": "Session", "Cache-Control": "no-store"},
    )
