"""Persistence-only mappings for game rounds and their scoring evidence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as POSTGRESQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from gendertagger.db.base import Base


class GameRoundRow(Base):
    """Immutable server-scored summary of one completed game round."""

    __tablename__ = "game_rounds"
    __table_args__ = (
        CheckConstraint("round_size IN (10, 20, 50)", name="round_size_allowed"),
        CheckConstraint(
            "answered_count BETWEEN 0 AND round_size",
            name="answered_count_within_round",
        ),
        CheckConstraint("score = answered_count * 10", name="score_matches_answers"),
        Index(
            "ix_game_rounds_project_id_round_size_score",
            "project_id",
            "round_size",
            "score",
        ),
        Index("ix_game_rounds_reviewer_user_id_created_at", "reviewer_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(POSTGRESQL_UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    aggregation_execution_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("aggregation_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_user_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    round_size: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    answered_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class GameRoundEventRow(Base):
    """Ordered annotation evidence for one server-verified round score."""

    __tablename__ = "game_round_events"
    __table_args__ = (
        PrimaryKeyConstraint("game_round_id", "position", name="pk_game_round_events"),
        UniqueConstraint(
            "annotation_id",
            name="uq_game_round_events_annotation_scored_once",
        ),
        CheckConstraint("position >= 0", name="position_nonnegative"),
    )

    game_round_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("game_rounds.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    annotation_id: Mapped[UUID] = mapped_column(
        POSTGRESQL_UUID(as_uuid=True),
        ForeignKey("annotations.id", ondelete="RESTRICT"),
        nullable=False,
    )
