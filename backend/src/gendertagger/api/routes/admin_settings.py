"""Global-administrator deployment-settings read resource (ADR-0040)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from gendertagger.api.authorization import require_admin
from gendertagger.api.dependencies import get_admin_settings_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.admin_settings import AdminSettings
from gendertagger.models.api import ApiErrorEnvelope
from gendertagger.models.user import CurrentUser
from gendertagger.services.admin_settings import AdminSettingsService
from gendertagger.services.ports.persistence_errors import SettingsUnavailableError

router = APIRouter(tags=["admin settings"])


@router.get(
    "/admin/settings",
    response_model=AdminSettings,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ApiErrorEnvelope,
            "description": "Settings storage unavailable",
        }
    },
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
        raise ApiRequestError(
            headers={"Cache-Control": "no-store"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="settings_unavailable",
            message="Administrative settings are currently unavailable.",
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return result
