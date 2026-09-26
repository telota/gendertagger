"""Application persistence contract for game rounds and leaderboards."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from gendertagger.models.game import GameLeaderboardEntry, GameRound, GameRoundSize
from gendertagger.models.review import ReviewAction


@dataclass(frozen=True, slots=True)
class GameAnnotationEvidence:
    """Facts proving that an answer is a distinct saved review decision."""

    annotation_id: UUID
    person_record_id: UUID
    reviewer_user_id: UUID
    aggregation_execution_id: UUID
    action: ReviewAction


@dataclass(frozen=True, slots=True)
class GameRoundWrite:
    """Server-derived round values ready for persistence."""

    id: UUID
    project_id: UUID
    aggregation_execution_id: UUID
    reviewer_user_id: UUID
    round_size: GameRoundSize
    score: int
    answered_count: int
    annotation_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class GameLeaderboardData:
    """Bounded leaderboard entries plus the full distinct-player count."""

    total_players: int
    entries: Sequence[GameLeaderboardEntry]


class GameRepository(Protocol):
    """Persist immutable rounds and query one best round per project member."""

    def lock_round(self, round_id: UUID) -> None:
        """Serialize commands sharing one client-generated round identifier."""
        ...

    def get_round(self, round_id: UUID) -> GameRound | None:
        """Return one round by its client-generated idempotency identifier."""
        ...

    def get_round_annotation_ids(self, round_id: UUID) -> Sequence[UUID]:
        """Return one round's persisted answer evidence in command order."""
        ...

    def get_annotation_evidence(
        self,
        annotation_ids: Sequence[UUID],
    ) -> Sequence[GameAnnotationEvidence]:
        """Return identity, action, reviewer, and aggregation facts for machine-backed annotations."""
        ...

    def add_round(self, command: GameRoundWrite) -> GameRound:
        """Persist one immutable scored round and its ordered evidence events."""
        ...

    def list_leaderboard(
        self,
        project_id: UUID,
        round_size: GameRoundSize,
        *,
        limit: int,
    ) -> GameLeaderboardData:
        """Return each member's best comparable round in deterministic rank order."""
        ...
