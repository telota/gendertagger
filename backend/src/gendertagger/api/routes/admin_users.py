"""Global-administrator local-account resources (ADR-0039)."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from gendertagger.api.authorization import require_admin
from gendertagger.api.dependencies import get_user_administration_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.auth import (
    AdminUser,
    AdminUserCreate,
    AdminUserCreateResult,
    AdminUserPasswordResetResult,
    AdminUserUpdate,
)
from gendertagger.models.user import CurrentUser
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    DuplicateUsernameError,
    ResourceNotFoundError,
)
from gendertagger.services.user_administration import (
    AdminUserStateConflictError,
    UserAdministrationService,
)

router = APIRouter(tags=["admin users"])


@router.post(
    "/admin/users",
    response_model=AdminUserCreateResult,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_user(
    command: AdminUserCreate,
    request: Request,
    response: Response,
    service: Annotated[UserAdministrationService, Depends(get_user_administration_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminUserCreateResult:
    """Provision one local account and disclose its temporary password once."""
    try:
        result = service.create_user(
            command,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except DuplicateUsernameError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="username_conflict",
            message="A local account with that username already exists.",
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/admin/users/{user_id}/reset-password",
    response_model=AdminUserPasswordResetResult,
)
def reset_admin_user_password(
    user_id: UUID,
    request: Request,
    response: Response,
    service: Annotated[UserAdministrationService, Depends(get_user_administration_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminUserPasswordResetResult:
    """Reset a local account password and disclose the generated replacement once."""
    try:
        result = service.reset_user_password(
            user_id,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except ResourceNotFoundError as error:
        raise ApiRequestError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message="The local account was not found.",
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return result


@router.patch("/admin/users/{user_id}", response_model=AdminUser)
def update_admin_user(
    user_id: UUID,
    command: AdminUserUpdate,
    request: Request,
    service: Annotated[UserAdministrationService, Depends(get_user_administration_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminUser:
    """Update mutable local-account fields without changing its username."""
    try:
        return service.update_user(
            user_id,
            command,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except ResourceNotFoundError as error:
        raise ApiRequestError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message="The local account was not found.",
        ) from error
    except AdminUserStateConflictError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code=error.code,
            message=error.message,
        ) from error


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
