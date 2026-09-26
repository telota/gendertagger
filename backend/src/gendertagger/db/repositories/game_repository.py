"""SQLAlchemy repository for immutable game rounds and project leaderboards."""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gendertagger.db.rows.aggregations import AggregatedResultRow
from gendertagger.db.rows.games import GameRoundEventRow, GameRoundRow
from gendertagger.db.rows.reviews import AnnotationRow
from gendertagger.db.rows.users import UserRow
from gendertagger.models.game import GameLeaderboardEntry, GameRound, GameRoundSize
from gendertagger.services.ports.game_repository import (
    GameAnnotationEvidence,
    GameLeaderboardData,
    GameRoundWrite,
)
from gendertagger.services.ports.persistence_errors import InvalidResourceStateError

_ROUND_PRIMARY_KEY_CONSTRAINT = "pk_game_rounds"
_ANNOTATION_SCORE_UNIQUE_CONSTRAINT = "uq_game_round_events_annotation_scored_once"


class SqlAlchemyGameRepository:
    """Persist scored rounds without owning the caller's transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_round(self, round_id: UUID) -> None:
        """Serialize commands sharing a round id for atomic idempotency."""
        advisory_key = round_id.int >> 64
        if advisory_key >= 2**63:
            advisory_key -= 2**64
        self._session.execute(select(func.pg_advisory_xact_lock(advisory_key)))

    def get_round(self, round_id: UUID) -> GameRound | None:
        """Return one previously persisted round."""
        row = self._session.get(GameRoundRow, round_id)
        return None if row is None else self._round_from_row(row)

    def get_round_annotation_ids(self, round_id: UUID) -> Sequence[UUID]:
        """Return one round's persisted annotation identifiers in command order."""
        return tuple(
            self._session.scalars(
                select(GameRoundEventRow.annotation_id)
                .where(GameRoundEventRow.game_round_id == round_id)
                .order_by(GameRoundEventRow.position)
            )
        )

    def get_annotation_evidence(
        self,
        annotation_ids: Sequence[UUID],
    ) -> Sequence[GameAnnotationEvidence]:
        """Resolve only annotations tied to an aggregated result."""
        if not annotation_ids:
            return []
        rows = self._session.execute(
            select(
                AnnotationRow.id,
                AnnotationRow.person_record_id,
                AnnotationRow.action,
                AnnotationRow.reviewer_user_id,
                AggregatedResultRow.aggregation_execution_id,
            )
            .join(
                AggregatedResultRow,
                AggregatedResultRow.id == AnnotationRow.aggregated_result_id,
            )
            .where(AnnotationRow.id.in_(annotation_ids))
            .order_by(AnnotationRow.id)
            .with_for_update(of=AnnotationRow)
        ).all()
        return [
            GameAnnotationEvidence(
                annotation_id=row.id,
                person_record_id=row.person_record_id,
                reviewer_user_id=row.reviewer_user_id,
                aggregation_execution_id=row.aggregation_execution_id,
                action=row.action,
            )
            for row in rows
        ]

    def add_round(self, command: GameRoundWrite) -> GameRound:
        """Persist one score and the immutable annotations that prove it."""
        if self._session.get(GameRoundRow, command.id) is not None:
            msg = f"game round {command.id} already exists"
            raise InvalidResourceStateError(msg)

        annotation_ids = list(command.annotation_ids)
        if annotation_ids:
            used = self._session.scalars(
                select(GameRoundEventRow.annotation_id).where(
                    GameRoundEventRow.annotation_id.in_(annotation_ids)
                )
            ).all()
            if used:
                msg = "one or more annotations have already contributed to a scored round"
                raise InvalidResourceStateError(msg)

        row = GameRoundRow(
            id=command.id,
            project_id=command.project_id,
            aggregation_execution_id=command.aggregation_execution_id,
            reviewer_user_id=command.reviewer_user_id,
            round_size=command.round_size,
            score=command.score,
            answered_count=command.answered_count,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as error:
            constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint_name == _ROUND_PRIMARY_KEY_CONSTRAINT:
                msg = f"game round {command.id} already exists"
                raise InvalidResourceStateError(msg) from error
            raise
        self._session.add_all(
            [
                GameRoundEventRow(
                    game_round_id=row.id,
                    position=position,
                    annotation_id=annotation_id,
                )
                for position, annotation_id in enumerate(command.annotation_ids)
            ]
        )
        try:
            self._session.flush()
        except IntegrityError as error:
            constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint_name == _ANNOTATION_SCORE_UNIQUE_CONSTRAINT:
                msg = "one or more annotations have already contributed to a scored round"
                raise InvalidResourceStateError(msg) from error
            raise
        return self._round_from_row(row)

    def list_leaderboard(
        self,
        project_id: UUID,
        round_size: GameRoundSize,
        *,
        limit: int,
    ) -> GameLeaderboardData:
        """Rank verified-answer rounds by score, then creation time."""
        order = (
            GameRoundRow.score.desc(),
            GameRoundRow.created_at.asc(),
            GameRoundRow.id.asc(),
        )
        ranked = (
            select(
                GameRoundRow.id.label("round_id"),
                GameRoundRow.reviewer_user_id,
                UserRow.display_name.label("reviewer_display_name"),
                GameRoundRow.score,
                GameRoundRow.answered_count,
                GameRoundRow.created_at,
                func.row_number()
                .over(partition_by=GameRoundRow.reviewer_user_id, order_by=order)
                .label("reviewer_rank"),
            )
            .join(UserRow, UserRow.id == GameRoundRow.reviewer_user_id)
            .where(
                GameRoundRow.project_id == project_id,
                GameRoundRow.round_size == round_size,
            )
            .subquery()
        )
        best_filter = ranked.c.reviewer_rank == 1
        total_players = int(
            self._session.scalar(select(func.count()).select_from(ranked).where(best_filter)) or 0
        )
        rows = self._session.execute(
            select(ranked)
            .where(best_filter)
            .order_by(
                ranked.c.score.desc(),
                ranked.c.created_at.asc(),
                ranked.c.round_id.asc(),
            )
            .limit(limit)
        ).mappings()
        entries = tuple(
            GameLeaderboardEntry(
                rank=rank,
                round_id=row["round_id"],
                reviewer_user_id=row["reviewer_user_id"],
                reviewer_display_name=row["reviewer_display_name"],
                score=row["score"],
                answered_count=row["answered_count"],
                created_at=row["created_at"],
            )
            for rank, row in enumerate(rows, start=1)
        )
        return GameLeaderboardData(total_players=total_players, entries=entries)

    @staticmethod
    def _round_from_row(row: GameRoundRow) -> GameRound:
        return GameRound(
            id=row.id,
            project_id=row.project_id,
            aggregation_execution_id=row.aggregation_execution_id,
            reviewer_user_id=row.reviewer_user_id,
            round_size=cast(GameRoundSize, row.round_size),
            score=row.score,
            answered_count=row.answered_count,
            created_at=row.created_at,
        )
