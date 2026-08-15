"""Versioned API router composition."""

from fastapi import APIRouter, Depends

from gendertagger.api.aggregations import router as aggregations_router
from gendertagger.api.annotations import router as annotations_router
from gendertagger.api.authentication import (
    require_csrf_protection,
)
from gendertagger.api.authentication import (
    router as authentication_router,
)
from gendertagger.api.evaluations import router as evaluations_router
from gendertagger.api.exports import router as exports_router
from gendertagger.api.methods import router as methods_router
from gendertagger.api.projects import router as projects_router
from gendertagger.api.review_items import router as review_items_router
from gendertagger.api.runs import router as runs_router
from gendertagger.models.api import ApiErrorEnvelope


def create_api_router() -> APIRouter:
    """Create the fail-closed ``/api/v1`` router boundary."""
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(require_csrf_protection)],
        responses={
            400: {"model": ApiErrorEnvelope, "description": "Invalid request"},
            401: {"model": ApiErrorEnvelope, "description": "Authentication required"},
            403: {"model": ApiErrorEnvelope, "description": "Forbidden"},
            404: {"model": ApiErrorEnvelope, "description": "Resource not found"},
            409: {"model": ApiErrorEnvelope, "description": "Resource conflict"},
            413: {"model": ApiErrorEnvelope, "description": "Payload too large"},
            422: {"model": ApiErrorEnvelope, "description": "Validation error"},
            500: {"model": ApiErrorEnvelope, "description": "Internal server error"},
        },
    )
    router.include_router(annotations_router)
    router.include_router(aggregations_router)
    router.include_router(authentication_router)
    router.include_router(evaluations_router)
    router.include_router(exports_router)
    router.include_router(methods_router)
    router.include_router(projects_router)
    router.include_router(review_items_router)
    router.include_router(runs_router)
    return router
