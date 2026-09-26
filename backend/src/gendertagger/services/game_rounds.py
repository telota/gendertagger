"""Application use cases for scored game rounds and project leaderboards."""

from uuid import UUID

from gendertagger.domain.game_scoring import score_game_round
from gendertagger.models.game import (
    GameLeaderboard,
    GameRound,
    GameRoundCreate,
    GameRoundSize,
)
from gendertagger.models.lifecycle import AggregationExecutionStatus
from gendertagger.models.review import ReviewAction
from gendertagger.services.ports.game_repository import GameRoundWrite
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.project_access_repository import ProjectScope
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory


class GameModeDisabledError(RuntimeError):
    """Raised when a project has not opted into the optional game interface."""


class GameRoundService:
    """Verify annotation evidence, derive scores, and expose comparable rankings."""

    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def create_round(
        self,
        project_id: UUID,
        command: GameRoundCreate,
        *,
        reviewer_user_id: UUID,
    ) -> GameRound:
        """Persist one idempotent server-scored round for the authenticated reviewer."""
        with self._unit_of_work_factory() as unit_of_work:
            self._require_game_mode_enabled(unit_of_work, project_id)
            owning_project_id = unit_of_work.access.get_owning_project_id(
                ProjectScope.aggregation,
                command.aggregation_execution_id,
            )
            if owning_project_id is None:
                msg = f"aggregation {command.aggregation_execution_id} does not exist"
                raise ResourceNotFoundError(msg)
            if owning_project_id != project_id:
                msg = "aggregation belongs to a different project"
                raise InvalidResourceStateError(msg)
            aggregation = unit_of_work.aggregations.get_aggregation(
                command.aggregation_execution_id
            )
            if aggregation is None:
                msg = f"aggregation {command.aggregation_execution_id} does not exist"
                raise ResourceNotFoundError(msg)
            if aggregation.status is not AggregationExecutionStatus.completed:
                msg = f"aggregation {command.aggregation_execution_id} is not completed"
                raise InvalidResourceStateError(msg)

            unit_of_work.games.lock_round(command.id)
            existing = unit_of_work.games.get_round(command.id)
            if existing is not None:
                if (
                    existing.project_id != project_id
                    or existing.reviewer_user_id != reviewer_user_id
                    or existing.aggregation_execution_id != command.aggregation_execution_id
                    or existing.round_size != command.round_size
                    or tuple(unit_of_work.games.get_round_annotation_ids(command.id))
                    != command.annotation_ids
                ):
                    msg = "game round id is already bound to a different command"
                    raise InvalidResourceStateError(msg)
                return existing

            annotation_ids = command.annotation_ids
            evidence = unit_of_work.games.get_annotation_evidence(annotation_ids)
            by_id = {item.annotation_id: item for item in evidence}
            if len(by_id) != len(annotation_ids):
                msg = "every answer must reference an existing machine-backed annotation"
                raise ResourceNotFoundError(msg)
            if any(
                item.reviewer_user_id != reviewer_user_id
                or item.aggregation_execution_id != command.aggregation_execution_id
                or item.action not in {ReviewAction.verify, ReviewAction.correct}
                for item in evidence
            ):
                msg = (
                    "answer annotations must be saved review decisions "
                    "from this reviewer and aggregation"
                )
                raise InvalidResourceStateError(msg)
            if len({item.person_record_id for item in evidence}) != len(evidence):
                msg = "a person may contribute at most one answer to a game round"
                raise InvalidResourceStateError(msg)

            answered_count = len(evidence)
            result = unit_of_work.games.add_round(
                GameRoundWrite(
                    id=command.id,
                    project_id=project_id,
                    aggregation_execution_id=command.aggregation_execution_id,
                    reviewer_user_id=reviewer_user_id,
                    round_size=command.round_size,
                    score=score_game_round(answered_count),
                    answered_count=answered_count,
                    annotation_ids=command.annotation_ids,
                )
            )
            unit_of_work.commit()
        return result

    def get_leaderboard(
        self,
        project_id: UUID,
        round_size: GameRoundSize,
        *,
        limit: int,
    ) -> GameLeaderboard:
        """Return one best round per project member for the selected round size."""
        with self._unit_of_work_factory() as unit_of_work:
            self._require_game_mode_enabled(unit_of_work, project_id)
            data = unit_of_work.games.list_leaderboard(project_id, round_size, limit=limit)
        return GameLeaderboard(
            project_id=project_id,
            round_size=round_size,
            total_players=data.total_players,
            entries=tuple(data.entries),
        )

    @staticmethod
    def _require_game_mode_enabled(unit_of_work: UnitOfWork, project_id: UUID) -> None:
        project = unit_of_work.projects.get_project(project_id)
        if project is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        if not project.game_mode_enabled:
            msg = f"game mode is disabled for project {project_id}"
            raise GameModeDisabledError(msg)
