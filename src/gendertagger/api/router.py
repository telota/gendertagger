"""Versioned API router composition."""

from fastapi import APIRouter, Depends

from gendertagger.api.authentication import require_csrf_protection


def create_api_router() -> APIRouter:
    """Create the fail-closed ``/api/v1`` router boundary."""
    return APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(require_csrf_protection)],
    )
