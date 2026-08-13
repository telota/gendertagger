"""Versioned API router composition."""

from fastapi import APIRouter, Depends

from gendertagger.api.aggregations import router as aggregations_router
from gendertagger.api.authentication import require_csrf_protection
from gendertagger.api.methods import router as methods_router
from gendertagger.api.projects import router as projects_router
from gendertagger.api.runs import router as runs_router


def create_api_router() -> APIRouter:
    """Create the fail-closed ``/api/v1`` router boundary."""
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(require_csrf_protection)],
    )
    router.include_router(aggregations_router)
    router.include_router(methods_router)
    router.include_router(projects_router)
    router.include_router(runs_router)
    return router
