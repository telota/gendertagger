"""Versioned API router composition.

The ``/api/v1`` surface is split across three router builders with different authentication
requirements (ADR-0031):

- :func:`create_api_router` — authenticated, CSRF-protected, and blocked while a flagged local
  account still owes a password change. Everything except the routes below.
- :func:`create_password_change_exempt_router` — authenticated and CSRF-protected, but reachable
  even while a password change is owed, since a user must be able to reach these to clear the gate:
  ``GET /me``, ``GET /auth/session``, ``POST /auth/logout``, ``POST /me/password``.
- :func:`create_unauthenticated_router` — reachable before a session exists: ``POST /auth/login`` and
  ``GET /branding``/``GET /branding/logo`` (ADR-0036), which carry no scientific or project-scoped
  data and need no grant at all.

``gendertagger.api.app.create_app`` mounts all three.
"""

from typing import Any

from fastapi import APIRouter, Depends

from gendertagger.api.authentication import require_csrf_protection, require_password_current
from gendertagger.api.routes.admin_settings import router as admin_settings_router
from gendertagger.api.routes.admin_users import router as admin_users_router
from gendertagger.api.routes.aggregations import router as aggregations_router
from gendertagger.api.routes.annotations import router as annotations_router
from gendertagger.api.routes.authentication import router as authentication_router
from gendertagger.api.routes.authentication import unauthenticated_router as login_router
from gendertagger.api.routes.branding import router as branding_router
from gendertagger.api.routes.classify import router as classify_router
from gendertagger.api.routes.evaluations import router as evaluations_router
from gendertagger.api.routes.exports import router as exports_router
from gendertagger.api.routes.methods import router as methods_router
from gendertagger.api.routes.project_members import router as project_members_router
from gendertagger.api.routes.projects import router as projects_router
from gendertagger.api.routes.review_items import router as review_items_router
from gendertagger.api.routes.runs import router as runs_router
from gendertagger.api.routes.teams import router as teams_router
from gendertagger.models.api import ApiErrorEnvelope

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ApiErrorEnvelope, "description": "Invalid request"},
    401: {"model": ApiErrorEnvelope, "description": "Authentication required"},
    403: {"model": ApiErrorEnvelope, "description": "Forbidden"},
    404: {"model": ApiErrorEnvelope, "description": "Resource not found"},
    409: {"model": ApiErrorEnvelope, "description": "Resource conflict"},
    413: {"model": ApiErrorEnvelope, "description": "Payload too large"},
    422: {"model": ApiErrorEnvelope, "description": "Validation error"},
    500: {"model": ApiErrorEnvelope, "description": "Internal server error"},
}


def create_api_router() -> APIRouter:
    """Create the fail-closed, password-current-gated ``/api/v1`` router boundary."""
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(require_csrf_protection), Depends(require_password_current)],
        responses=_ERROR_RESPONSES,
    )
    router.include_router(admin_users_router)
    router.include_router(admin_settings_router)
    router.include_router(teams_router)
    router.include_router(annotations_router)
    router.include_router(aggregations_router)
    router.include_router(classify_router)
    router.include_router(evaluations_router)
    router.include_router(exports_router)
    router.include_router(methods_router)
    router.include_router(projects_router)
    router.include_router(project_members_router)
    router.include_router(review_items_router)
    router.include_router(runs_router)
    return router


def create_password_change_exempt_router() -> APIRouter:
    """Authenticated, CSRF-protected ``/api/v1`` routes exempt from the password-change gate."""
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(require_csrf_protection)],
        responses=_ERROR_RESPONSES,
    )
    router.include_router(authentication_router)
    return router


def create_unauthenticated_router() -> APIRouter:
    """``/api/v1`` routes reachable before a session exists."""
    router = APIRouter(prefix="/api/v1", responses=_ERROR_RESPONSES)
    router.include_router(login_router)
    router.include_router(branding_router)
    return router
