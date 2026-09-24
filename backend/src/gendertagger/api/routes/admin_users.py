"""Global-administrator local-account resources (ADR-0039)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from gendertagger.api.authorization import require_admin
from gendertagger.api.dependencies import get_user_administration_service
from gendertagger.api.errors import invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.auth import AdminUser
from gendertagger.models.user import CurrentUser
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.user_administration import UserAdministrationService

router = APIRouter(tags=["admin users"])


@router.get("/admin/users", response_model=CursorPage[AdminUser])
def list_admin_users(
    service: Annotated[UserAdministrationService, Depends(get_user_administration_service)],
    _: Annotated[CurrentUser, Depends(require_admin)],
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[AdminUser]:
    """List local accounts in normalized-username order for administration."""
    try:
        return service.list_users(query=query, limit=limit, cursor=cursor)
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error
