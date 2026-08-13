"""Runnable method registry HTTP resource."""

from typing import Annotated

from fastapi import APIRouter, Depends

from gendertagger.api.authorization import require_viewer
from gendertagger.api.dependencies import get_method_registry
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.user import User
from gendertagger.services.method_registry import MethodRegistry

router = APIRouter(tags=["methods"])


@router.get("/methods", response_model=list[MethodDescriptor])
def list_methods(
    registry: Annotated[MethodRegistry, Depends(get_method_registry)],
    _: Annotated[User, Depends(require_viewer)],
) -> list[MethodDescriptor]:
    """List only adapters whose config contracts are runnable on this server."""
    return [registration.descriptor for registration in registry.registrations]
