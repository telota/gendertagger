"""Project-scoped game-round score and leaderboard resources."""

from enum import IntEnum
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from gendertagger.api.authorization import ProjectAccessGuard, get_project_access_guard
from gendertagger.api.dependencies import get_game_round_service
from gendertagger.api.errors import ApiRequestError
from gendertagger.models.game import GameLeaderboard, GameRound, GameRoundCreate
from gendertagger.models.user import ProjectRole
from gendertagger.services.game_rounds import GameModeDisabledError, GameRoundService
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.project_access_repository import ProjectScope

router = APIRouter(tags=["game"])


class _GameRoundSizeQuery(IntEnum):
    """Numeric query representation that accepts HTTP string values."""

    short = 10
    standard = 20
    long = 50


@router.post(
    "/projects/{project_id}/game-rounds",
    response_model=GameRound,
    status_code=status.HTTP_201_CREATED,
)
def create_game_round(
    project_id: UUID,
    command: GameRoundCreate,
    service: Annotated[GameRoundService, Depends(get_game_round_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
) -> GameRound:
    """Record a completed round after verifying its ordinary annotation writes."""
    access.require(ProjectScope.project, project_id, ProjectRole.reviewer)
    access.require(
        ProjectScope.aggregation,
        command.aggregation_execution_id,
        ProjectRole.reviewer,
    )
    try:
        return service.create_round(project_id, command, reviewer_user_id=access.user.id)
    except GameModeDisabledError as error:
        raise _game_mode_disabled_error() from error
    except ResourceNotFoundError as error:
        raise ApiRequestError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message="The requested game-round evidence does not exist.",
        ) from error
    except InvalidResourceStateError as error:
        raise ApiRequestError(
            status_code=status.HTTP_409_CONFLICT,
            code="resource_conflict",
            message="The game round references incompatible or already scored evidence.",
        ) from error


@router.get(
    "/projects/{project_id}/game-leaderboard",
    response_model=GameLeaderboard,
)
def get_game_leaderboard(
    project_id: UUID,
    round_size: Annotated[_GameRoundSizeQuery, Query()],
    service: Annotated[GameRoundService, Depends(get_game_round_service)],
    access: Annotated[ProjectAccessGuard, Depends(get_project_access_guard)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> GameLeaderboard:
    """List each project member's best round at one comparable round size."""
    access.require(ProjectScope.project, project_id, ProjectRole.viewer)
    try:
        return service.get_leaderboard(project_id, round_size.value, limit=limit)
    except GameModeDisabledError as error:
        raise _game_mode_disabled_error() from error
    except ResourceNotFoundError as error:
        raise ApiRequestError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found",
            message="The requested project does not exist.",
        ) from error


def _game_mode_disabled_error() -> ApiRequestError:
    return ApiRequestError(
        status_code=status.HTTP_409_CONFLICT,
        code="game_mode_disabled",
        message="Game mode is disabled for this project.",
    )
