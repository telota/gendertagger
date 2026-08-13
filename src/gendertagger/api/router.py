"""Versioned API router composition."""

from fastapi import APIRouter, Depends

from gendertagger.api.authentication import require_csrf_protection
from gendertagger.api.projects import router as projects_router


def create_api_router() -> APIRouter:
    """Create the fail-closed ``/api/v1`` router boundary."""
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(require_csrf_protection)],
    )
    router.include_router(projects_router)
    return router
