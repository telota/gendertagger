"""Delegated project-membership HTTP resources (ADR-0041)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from gendertagger.api.authorization import (
    ProjectMembershipManagementGuard,
    get_project_membership_management_guard,
)
from gendertagger.api.dependencies import get_project_access_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.project import (
    ProjectEligibleUser,
    ProjectManagerUpdate,
    ProjectMember,
    ProjectMembershipState,
    ProjectMemberUpdate,
)
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.project_access import (
    ProjectAccessService,
    ProjectManagerConflictError,
    TeamMembershipConflictError,
)

router = APIRouter(tags=["project members"])


@router.get("/projects/{project_id}/members", response_model=ProjectMembershipState)
def list_project_members(
    project_id: UUID,
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
    guard: Annotated[
        ProjectMembershipManagementGuard,
        Depends(get_project_membership_management_guard),
    ],
) -> ProjectMembershipState:
    """List one delegated roster's explicit memberships and manager assignment."""
    guard.require(project_id)
    try:
        return service.list_members(project_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.get(
    "/projects/{project_id}/eligible-users",
    response_model=CursorPage[ProjectEligibleUser],
)
def list_eligible_users(
    project_id: UUID,
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
    guard: Annotated[
        ProjectMembershipManagementGuard,
        Depends(get_project_membership_management_guard),
    ],
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[ProjectEligibleUser]:
    """Search active direct-team-member candidates without exposing account administration."""
    guard.require(project_id)
    try:
        return service.list_eligible_users(project_id, query=query, limit=limit, cursor=cursor)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.put("/projects/{project_id}/members/{user_id}", response_model=ProjectMember)
def set_project_member(
    project_id: UUID,
    user_id: UUID,
    command: ProjectMemberUpdate,
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
    guard: Annotated[
        ProjectMembershipManagementGuard,
        Depends(get_project_membership_management_guard),
    ],
) -> ProjectMember:
    """Grant or change one eligible user's role in a project."""
    guard.require(project_id)
    try:
        return service.set_member_role(
            project_id,
            user_id,
            command.role,
            actor_user_id=guard.user.id,
        )
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except TeamMembershipConflictError as error:
        raise _team_membership_conflict() from error


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
    guard: Annotated[
        ProjectMembershipManagementGuard,
        Depends(get_project_membership_management_guard),
    ],
) -> None:
    """Revoke one eligible user's explicit project role."""
    guard.require(project_id)
    try:
        service.remove_member(project_id, user_id, actor_user_id=guard.user.id)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except TeamMembershipConflictError as error:
        raise _team_membership_conflict() from error


@router.put("/projects/{project_id}/manager", response_model=ProjectMembershipState)
def transfer_project_manager(
    project_id: UUID,
    command: ProjectManagerUpdate,
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
    guard: Annotated[
        ProjectMembershipManagementGuard,
        Depends(get_project_membership_management_guard),
    ],
) -> ProjectMembershipState:
    """Transfer delegated manager authority without modifying ordinary project roles."""
    guard.require(project_id)
    try:
        return service.transfer_manager(project_id, command, actor_user_id=guard.user.id)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except ProjectManagerConflictError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="project_manager_conflict",
            message="The project manager changed; refresh and retry.",
        ) from error
    except TeamMembershipConflictError as error:
        raise _team_membership_conflict() from error


def _team_membership_conflict() -> ApiRequestError:
    """Build the stable race outcome for a target removed from the direct team."""
    return ApiRequestError(
        status_code=status.HTTP_409_CONFLICT,
        code="team_membership_conflict",
        message="The user's direct team membership changed; refresh and retry.",
    )


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
