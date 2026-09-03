"""Versioned API router composition.

The ``/api/v1`` surface is split across three router builders with different authentication
requirements (ADR-0031):

- :func:`create_api_router` — authenticated, CSRF-protected, and blocked while a flagged local
  account still owes a password change. Everything except the routes below.
- :func:`create_password_change_exempt_router` — authenticated and CSRF-protected, but reachable
  even while a password change is owed, since a user must be able to reach these to clear the gate:
  ``GET /me``, ``POST /auth/logout``, ``POST /me/password``.
- :func:`create_unauthenticated_router` — reachable before a session exists: ``POST /auth/login``.

``gendertagger.api.app.create_app`` mounts all three.
"""

from typing import Any

from fastapi import APIRouter, Depends

from gendertagger.api.aggregations import router as aggregations_router
from gendertagger.api.annotations import router as annotations_router
from gendertagger.api.authentication import require_csrf_protection, require_password_current
from gendertagger.api.authentication import router as authentication_router
from gendertagger.api.authentication import unauthenticated_router as login_router
from gendertagger.api.classify import router as classify_router
from gendertagger.api.evaluations import router as evaluations_router
from gendertagger.api.exports import router as exports_router
from gendertagger.api.methods import router as methods_router
from gendertagger.api.projects import router as projects_router
from gendertagger.api.review_items import router as review_items_router
from gendertagger.api.runs import router as runs_router
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
    router.include_router(annotations_router)
    router.include_router(aggregations_router)
    router.include_router(classify_router)
    router.include_router(evaluations_router)
    router.include_router(exports_router)
    router.include_router(methods_router)
    router.include_router(projects_router)
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
    return router
