"""Administrator-only project membership HTTP resources (ADR-0033)."""

from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from gendertagger.api.authorization import require_admin
from gendertagger.api.dependencies import get_project_access_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.project import ProjectMember, ProjectMemberUpdate
from gendertagger.models.user import CurrentUser
from gendertagger.services.persistence_errors import ResourceNotFoundError
from gendertagger.services.project_access import ProjectAccessService

router = APIRouter(tags=["project members"])


@router.get("/projects/{project_id}/members", response_model=list[ProjectMember])
def list_project_members(
    project_id: UUID,
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> Sequence[ProjectMember]:
    """List one project's members and their roles, ordered by display name."""
    try:
        return service.list_members(project_id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.put("/projects/{project_id}/members/{user_id}", response_model=ProjectMember)
def set_project_member(
    project_id: UUID,
    user_id: UUID,
    command: ProjectMemberUpdate,
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> ProjectMember:
    """Grant a user a role in one project, or change the role the user already holds."""
    try:
        return service.set_member_role(
            project_id,
            user_id,
            command.role,
            actor_user_id=admin.id,
        )
    except ResourceNotFoundError as error:
        raise _not_found() from error


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    service: Annotated[ProjectAccessService, Depends(get_project_access_service)],
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> None:
    """Revoke one user's membership in a project."""
    try:
        service.remove_member(project_id, user_id, actor_user_id=admin.id)
    except ResourceNotFoundError as error:
        raise _not_found() from error


def _not_found() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource does not exist.",
    )
