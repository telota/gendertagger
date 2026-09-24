"""Direct-team and global-administrator roster resources (ADR-0041 slice 1)."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from gendertagger.api.authentication import require_authenticated_user
from gendertagger.api.authorization import require_admin
from gendertagger.api.dependencies import get_team_service
from gendertagger.api.errors import ApiRequestError, invalid_cursor_error
from gendertagger.models.api import CursorPage
from gendertagger.models.team import TeamCreate, TeamMember, TeamMemberAdd, TeamSummary, TeamUpdate
from gendertagger.models.user import CurrentUser
from gendertagger.services.pagination import InvalidCursorError
from gendertagger.services.ports.persistence_errors import (
    DuplicateTeamSlugError,
    ResourceNotFoundError,
)
from gendertagger.services.project_access import ManagerReplacementRequiredError
from gendertagger.services.teams import (
    InactiveUserError,
    TeamInUseError,
    TeamNotEmptyError,
    TeamService,
)

router = APIRouter(tags=["teams"])


@router.get("/teams", response_model=CursorPage[TeamSummary])
def list_visible_teams(
    current_user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    service: Annotated[TeamService, Depends(get_team_service)],
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[TeamSummary]:
    """List direct team summaries for the caller, or every summary for an administrator."""
    try:
        return service.list_visible_teams(
            current_user,
            query=query,
            limit=limit,
            cursor=cursor,
        )
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.get("/admin/teams", response_model=CursorPage[TeamSummary])
def list_admin_teams(
    service: Annotated[TeamService, Depends(get_team_service)],
    _: Annotated[CurrentUser, Depends(require_admin)],
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[TeamSummary]:
    """List every team for global administration."""
    try:
        return service.list_admin_teams(query=query, limit=limit, cursor=cursor)
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.post("/admin/teams", response_model=TeamSummary, status_code=status.HTTP_201_CREATED)
def create_admin_team(
    command: TeamCreate,
    request: Request,
    service: Annotated[TeamService, Depends(get_team_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> TeamSummary:
    """Create one direct-membership team without granting any project access."""
    try:
        return service.create_team(
            command,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except DuplicateTeamSlugError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="team_slug_conflict",
            message="A team with that slug already exists.",
        ) from error


@router.patch("/admin/teams/{team_id}", response_model=TeamSummary)
def update_admin_team(
    team_id: UUID,
    command: TeamUpdate,
    request: Request,
    service: Annotated[TeamService, Depends(get_team_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> TeamSummary:
    """Rename one team by updating only its mutable display name."""
    try:
        return service.update_team(
            team_id,
            command,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except ResourceNotFoundError as error:
        raise _resource_not_found_error("The team was not found.") from error


@router.delete("/admin/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_team(
    team_id: UUID,
    request: Request,
    service: Annotated[TeamService, Depends(get_team_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> None:
    """Delete one empty team after serializing concurrent direct-roster writes."""
    try:
        service.delete_team(
            team_id,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except ResourceNotFoundError as error:
        raise _resource_not_found_error("The team was not found.") from error
    except TeamNotEmptyError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="team_not_empty",
            message="A team with direct members cannot be deleted.",
        ) from error
    except TeamInUseError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="team_in_use",
            message="A team with assigned projects cannot be deleted.",
        ) from error


@router.get("/admin/teams/{team_id}/members", response_model=CursorPage[TeamMember])
def list_admin_team_members(
    team_id: UUID,
    service: Annotated[TeamService, Depends(get_team_service)],
    _: Annotated[CurrentUser, Depends(require_admin)],
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> CursorPage[TeamMember]:
    """List one direct team roster for global administration."""
    try:
        return service.list_members(team_id, query=query, limit=limit, cursor=cursor)
    except ResourceNotFoundError as error:
        raise _resource_not_found_error("The team was not found.") from error
    except InvalidCursorError as error:
        raise invalid_cursor_error() from error


@router.post(
    "/admin/teams/{team_id}/members",
    response_model=TeamMember,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": TeamMember,
            "description": "The direct membership already existed.",
        }
    },
)
def add_admin_team_member(
    team_id: UUID,
    command: TeamMemberAdd,
    request: Request,
    response: Response,
    service: Annotated[TeamService, Depends(get_team_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> TeamMember:
    """Add one active account to a direct team roster idempotently."""
    try:
        member, created = service.add_member(
            team_id,
            command,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except ResourceNotFoundError as error:
        raise _resource_not_found_error("The team or local account was not found.") from error
    except InactiveUserError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="inactive_user",
            message="An inactive account cannot be added to a team.",
        ) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return member


@router.delete("/admin/teams/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_admin_team_member(
    team_id: UUID,
    user_id: UUID,
    request: Request,
    service: Annotated[TeamService, Depends(get_team_service)],
    administrator: Annotated[CurrentUser, Depends(require_admin)],
) -> None:
    """Remove one direct team membership and its derived project grants."""
    try:
        service.remove_member(
            team_id,
            user_id,
            actor_user_id=administrator.id,
            request_id=cast(str, request.state.request_id),
        )
    except ResourceNotFoundError as error:
        raise _resource_not_found_error("The team membership was not found.") from error
    except ManagerReplacementRequiredError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="manager_replacement_required",
            message="Replace the user's project-manager assignments before removal.",
        ) from error


def _resource_not_found_error(message: str) -> ApiRequestError:
    """Build the stable resource-hiding error envelope shared by team resources."""
    return ApiRequestError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message=message,
    )
