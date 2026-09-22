"""Public deployment-branding resource (ADR-0036).

Unauthenticated, like `POST /auth/login`: the legal notice it backs must be reachable without a
session, and it carries no scientific or project-scoped data.
"""

from mimetypes import guess_type
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from gendertagger.api.dependencies import get_app_settings
from gendertagger.api.errors import ApiRequestError
from gendertagger.api.settings import AppSettings, BrandingSettings
from gendertagger.models.branding import BrandingInfo

router = APIRouter(tags=["branding"])

# The absolute, same-origin path the browser fetches. This router is mounted under the "/api/v1"
# prefix by create_unauthenticated_router(), so the literal route path alone would omit it.
LOGO_ROUTE_PATH = "/api/v1/branding/logo"


@router.get("/branding", response_model=BrandingInfo)
def get_branding(
    settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> BrandingInfo:
    """Return this deployment's operator-configured branding.

    A field the operator has not set is `None`: nothing here is invented on its behalf.
    """
    return _branding_info(settings.branding)


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


def _branding_info(branding: BrandingSettings) -> BrandingInfo:
    logo_url = LOGO_ROUTE_PATH if _logo_exists(branding.logo_path) else None
    return BrandingInfo(
        institution_name=branding.institution_name,
        institution_url=branding.institution_url,
        logo_url=logo_url,
        editors=list(branding.editors),
        published_since_year=branding.published_since_year,
        initiatives=list(branding.initiatives),
        contact_email=branding.contact_email,
        privacy_notice_url=branding.privacy_notice_url,
        legal_entity=branding.legal_entity,
    )


def _logo_exists(logo_path: Path | None) -> bool:
    return logo_path is not None and logo_path.is_file()


def _logo_not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="No branding logo is configured for this deployment.",
    )
