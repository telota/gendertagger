"""Public effective-branding resources (ADR-0036 and ADR-0040)."""

from mimetypes import guess_type
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from gendertagger.api.dependencies import get_admin_settings_service, get_app_settings
from gendertagger.api.errors import ApiRequestError
from gendertagger.api.settings import AppSettings
from gendertagger.models.api import ApiErrorEnvelope
from gendertagger.models.branding import BrandingInfo
from gendertagger.services.admin_settings import AdminSettingsService
from gendertagger.services.ports.persistence_errors import SettingsUnavailableError

router = APIRouter(tags=["branding"])

# The absolute, same-origin path the browser fetches. This router is mounted under the "/api/v1"
# prefix by create_unauthenticated_router(), so the literal route path alone would omit it.
LOGO_ROUTE_PATH = "/api/v1/branding/logo"


@router.get(
    "/branding",
    response_model=BrandingInfo,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ApiErrorEnvelope,
            "description": "Settings storage unavailable",
        }
    },
)
def get_branding(
    response: Response,
    service: Annotated[AdminSettingsService, Depends(get_admin_settings_service)],
) -> BrandingInfo:
    """Return the effective public branding resolved from committed overrides and deployment fallback."""
    try:
        branding = service.get_branding()
    except SettingsUnavailableError as error:
        raise _settings_unavailable_error() from error
    response.headers["Cache-Control"] = "no-store"
    return branding


@router.get("/branding/logo")
def get_branding_logo(
    settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> Response:
    """Stream the configured logo file, or `404` when none is configured or it is missing."""
    logo_path = settings.branding.logo_path
    if logo_path is None or not logo_path.is_file():
        raise _logo_not_found()
    media_type, _ = guess_type(logo_path.name)
    return Response(
        content=logo_path.read_bytes(),
        media_type=media_type or "application/octet-stream",
    )


def _logo_not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="No branding logo is configured for this deployment.",
    )


def _settings_unavailable_error() -> ApiRequestError:
    """Return the safe public settings-storage outage response without fallback."""
    return ApiRequestError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="settings_unavailable",
        message="Branding settings are currently unavailable.",
        headers={"Cache-Control": "no-store"},
    )
