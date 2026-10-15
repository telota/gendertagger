"""Runnable method registry HTTP resource."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from gendertagger.api.authorization import require_any_grant
from gendertagger.api.dependencies import get_method_registry
from gendertagger.models.method import RunnableMethod
from gendertagger.models.user import CurrentUser
from gendertagger.services.method_registry import MethodRegistration, MethodRegistry

router = APIRouter(tags=["methods"])


def _is_available(registration: MethodRegistration) -> bool:
    """Whether an empty `{}` config — what every caller sends by default — resolves for real.

    The same check `MethodRegistry.resolve_run_config` applies to an actual run, so this can never
    drift from what submitting a run would actually do.
    """
    try:
        registration.config_model.model_validate({})
    except ValidationError:
        return False
    return True


@router.get("/methods", response_model=list[RunnableMethod])
def list_methods(
    registry: Annotated[MethodRegistry, Depends(get_method_registry)],
    _: Annotated[CurrentUser, Depends(require_any_grant)],
) -> list[RunnableMethod]:
    """List only adapters whose config contracts are runnable on this server."""
    return [
        RunnableMethod(
            **registration.descriptor.model_dump(),
            available=_is_available(registration),
        )
        for registration in registry.registrations
    ]
