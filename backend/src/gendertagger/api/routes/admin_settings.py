"""Global-administrator deployment-settings resources (ADR-0040)."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request, Response, status

from gendertagger.api.authorization import require_admin
from gendertagger.api.dependencies import get_admin_settings_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.admin_settings import (
    AdminSettings,
    AdminSettingsReset,
    AdminSettingsUpdate,
    AggregationSettingsUpdate,
)
from gendertagger.models.api import ApiErrorEnvelope
from gendertagger.models.user import CurrentUser
from gendertagger.services.admin_settings import (
    AdminSettingsService,
    SettingsRevisionConflictError,
)
from gendertagger.services.ports.persistence_errors import SettingsUnavailableError

router = APIRouter(tags=["admin settings"])

_SETTINGS_UNAVAILABLE_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ApiErrorEnvelope,
        "description": "Settings storage unavailable",
    }
}


@router.get(
    "/admin/settings",
    response_model=AdminSettings,
    responses=_SETTINGS_UNAVAILABLE_RESPONSE,
)
def get_admin_settings(
    response: Response,
    service: Annotated[AdminSettingsService, Depends(get_admin_settings_service)],
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminSettings:
    """Return effective deployment branding and the fallback values visible to administrators."""
    try:
        result = service.get_settings()
    except SettingsUnavailableError as error:
        raise _settings_unavailable_error() from error
    response.headers["Cache-Control"] = "no-store"
    return result


@router.patch(
    "/admin/settings",
    response_model=AdminSettings,
    responses=_SETTINGS_UNAVAILABLE_RESPONSE,
)
def update_admin_settings(
    command: AdminSettingsUpdate,
    request: Request,
    response: Response,
    service: Annotated[AdminSettingsService, Depends(get_admin_settings_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminSettings:
    """Set explicit branding overrides under the requested singleton revision."""
    try:
        result = service.update_settings(
            command,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except SettingsRevisionConflictError as error:
        raise _settings_revision_conflict_error(error) from error
    except SettingsUnavailableError as error:
        raise _settings_unavailable_error() from error
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/admin/settings/reset",
    response_model=AdminSettings,
    responses=_SETTINGS_UNAVAILABLE_RESPONSE,
)
def reset_admin_settings(
    command: AdminSettingsReset,
    request: Request,
    response: Response,
    service: Annotated[AdminSettingsService, Depends(get_admin_settings_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminSettings:
    """Remove selected branding overrides under the requested singleton revision."""
    try:
        result = service.reset_settings(
            command,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except SettingsRevisionConflictError as error:
        raise _settings_revision_conflict_error(error) from error
    except SettingsUnavailableError as error:
        raise _settings_unavailable_error() from error
    response.headers["Cache-Control"] = "no-store"
    return result


@router.patch(
    "/admin/settings/aggregation",
    response_model=AdminSettings,
    responses=_SETTINGS_UNAVAILABLE_RESPONSE,
)
def update_aggregation_settings(
    command: AggregationSettingsUpdate,
    request: Request,
    response: Response,
    service: Annotated[AdminSettingsService, Depends(get_admin_settings_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminSettings:
    """Set whether `reference_partial_v1` aggregations may run (ADR-0051)."""
    try:
        result = service.update_aggregation_settings(
            command,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except SettingsRevisionConflictError as error:
        raise _settings_revision_conflict_error(error) from error
    except SettingsUnavailableError as error:
        raise _settings_unavailable_error() from error
    response.headers["Cache-Control"] = "no-store"
    return result


def _settings_revision_conflict_error(error: SettingsRevisionConflictError) -> ApiRequestError:
    """Translate a stale singleton revision to the stable public conflict envelope."""
    return ApiRequestError(
        status_code=status.HTTP_409_CONFLICT,
        code="settings_revision_conflict",
        message="The administrative settings have changed.",
        details={
            "expected_revision": error.expected_revision,
            "current_revision": error.current_revision,
        },
        headers={"Cache-Control": "no-store"},
    )


def _settings_unavailable_error() -> ApiRequestError:
    """Return the safe settings-storage outage response without persistence diagnostics."""
    return ApiRequestError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="settings_unavailable",
        message="Administrative settings are currently unavailable.",
        headers={"Cache-Control": "no-store"},
    )
