"""Canonical contracts for game rounds and project-scoped leaderboards."""

from typing import Literal, Self, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gendertagger.models.common import UtcDatetime

GameRoundSize: TypeAlias = Literal[10, 20, 50]


class GameRoundCreate(BaseModel):
    """Idempotent command recording verified answer evidence for one completed round.

    Official points depend only on immutable annotations validated by the server.
    Timer readings, skips, and streaks remain local presentation state because a
    completed-round request cannot prove those client observations.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    aggregation_execution_id: UUID
    round_size: GameRoundSize
    annotation_ids: tuple[UUID, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def _validate_annotation_ids(self) -> Self:
        if len(self.annotation_ids) > self.round_size:
            msg = "annotation_ids must not exceed round_size"
            raise ValueError(msg)
        if len(set(self.annotation_ids)) != len(self.annotation_ids):
            msg = "annotation_ids must not repeat"
            raise ValueError(msg)
        return self


class GameRound(BaseModel):
    """Persisted summary scored only from server-verified annotations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    project_id: UUID
    aggregation_execution_id: UUID
    reviewer_user_id: UUID
    round_size: GameRoundSize
    score: int = Field(ge=0)
    answered_count: int = Field(ge=0)
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_summary(self) -> Self:
        if self.answered_count > self.round_size:
            msg = "answered_count must not exceed round_size"
            raise ValueError(msg)
        if self.score != self.answered_count * 10:
            msg = "score must equal ten points per verified answer"
            raise ValueError(msg)
        return self


class GameLeaderboardEntry(BaseModel):
    """One project member's best verified-answer round at a selected size."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int = Field(gt=0)
    round_id: UUID
    reviewer_user_id: UUID
    reviewer_display_name: str = Field(min_length=1, max_length=200)
    score: int = Field(ge=0)
    answered_count: int = Field(ge=0)
    created_at: UtcDatetime


class GameLeaderboard(BaseModel):
    """Project-scoped best rounds for one comparable round size."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    round_size: GameRoundSize
    total_players: int = Field(ge=0)
    entries: tuple[GameLeaderboardEntry, ...]

    @model_validator(mode="after")
    def _validate_entries(self) -> Self:
        if len(self.entries) > self.total_players:
            msg = "entries must not exceed total_players"
            raise ValueError(msg)
        if [entry.rank for entry in self.entries] != list(range(1, len(self.entries) + 1)):
            msg = "leaderboard entries must have consecutive ranks starting at one"
            raise ValueError(msg)
        reviewer_ids = [entry.reviewer_user_id for entry in self.entries]
        if len(set(reviewer_ids)) != len(reviewer_ids):
            msg = "leaderboard entries must contain at most one round per reviewer"
            raise ValueError(msg)
        return self
