"""Keep official game scores limited to server-verifiable annotations.

Revision ID: 20260926_0012
Revises: 20260926_0011
Created: 2026-09-26 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0012"
down_revision: str | None = "20260926_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove client-authored timing, skip, and streak values from official scores."""
    op.execute(sa.text("DELETE FROM game_round_events WHERE annotation_id IS NULL"))
    for constraint_name in (
        "ck_game_round_events_kind_annotation_consistent",
        "ck_game_round_events_kind_allowed",
        "ck_game_round_events_elapsed_milliseconds_allowed",
    ):
        op.drop_constraint(op.f(constraint_name), "game_round_events", type_="check")
    op.alter_column(
        "game_round_events",
        "annotation_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.drop_column("game_round_events", "kind")
    op.drop_column("game_round_events", "elapsed_milliseconds")

    for constraint_name in (
        "ck_game_rounds_score_nonnegative",
        "ck_game_rounds_duration_nonnegative",
        "ck_game_rounds_answered_count_nonnegative",
        "ck_game_rounds_skipped_count_nonnegative",
        "ck_game_rounds_question_count_within_round",
        "ck_game_rounds_longest_streak_within_answers",
    ):
        op.drop_constraint(op.f(constraint_name), "game_rounds", type_="check")
    op.execute(sa.text("UPDATE game_rounds SET score = answered_count * 10"))
    op.drop_column("game_rounds", "timer_enabled")
    op.drop_column("game_rounds", "duration_milliseconds")
    op.drop_column("game_rounds", "skipped_count")
    op.drop_column("game_rounds", "longest_streak")
    op.create_check_constraint(
        op.f("ck_game_rounds_answered_count_within_round"),
        "game_rounds",
        "answered_count BETWEEN 0 AND round_size",
    )
    op.create_check_constraint(
        op.f("ck_game_rounds_score_matches_answers"),
        "game_rounds",
        "score = answered_count * 10",
    )


def downgrade() -> None:
    """Restore the former client-transcript columns without recreating unverifiable values."""
    op.drop_constraint(
        op.f("ck_game_rounds_score_matches_answers"),
        "game_rounds",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_game_rounds_answered_count_within_round"),
        "game_rounds",
        type_="check",
    )
    op.add_column(
        "game_rounds",
        sa.Column("timer_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "game_rounds",
        sa.Column(
            "duration_milliseconds",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "game_rounds",
        sa.Column("skipped_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "game_rounds",
        sa.Column("longest_streak", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.execute(sa.text("UPDATE game_rounds SET skipped_count = 1 WHERE answered_count = 0"))
    for column_name in (
        "timer_enabled",
        "duration_milliseconds",
        "skipped_count",
        "longest_streak",
    ):
        op.alter_column("game_rounds", column_name, server_default=None)
    op.create_check_constraint(
        op.f("ck_game_rounds_score_nonnegative"), "game_rounds", "score >= 0"
    )
    op.create_check_constraint(
        op.f("ck_game_rounds_duration_nonnegative"),
        "game_rounds",
        "duration_milliseconds >= 0",
    )
    op.create_check_constraint(
        op.f("ck_game_rounds_answered_count_nonnegative"),
        "game_rounds",
        "answered_count >= 0",
    )
    op.create_check_constraint(
        op.f("ck_game_rounds_skipped_count_nonnegative"),
        "game_rounds",
        "skipped_count >= 0",
    )
    op.create_check_constraint(
        op.f("ck_game_rounds_question_count_within_round"),
        "game_rounds",
        "answered_count + skipped_count BETWEEN 1 AND round_size",
    )
    op.create_check_constraint(
        op.f("ck_game_rounds_longest_streak_within_answers"),
        "game_rounds",
        "longest_streak BETWEEN 0 AND answered_count",
    )

    op.add_column(
        "game_round_events",
        sa.Column("kind", sa.String(length=6), server_default="answer", nullable=False),
    )
    op.add_column(
        "game_round_events",
        sa.Column(
            "elapsed_milliseconds",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.alter_column("game_round_events", "kind", server_default=None)
    op.alter_column("game_round_events", "elapsed_milliseconds", server_default=None)
    op.alter_column(
        "game_round_events",
        "annotation_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.create_check_constraint(
        op.f("ck_game_round_events_kind_allowed"),
        "game_round_events",
        "kind IN ('answer', 'skip')",
    )
    op.create_check_constraint(
        op.f("ck_game_round_events_kind_annotation_consistent"),
        "game_round_events",
        "(kind = 'answer' AND annotation_id IS NOT NULL) OR "
        "(kind = 'skip' AND annotation_id IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_game_round_events_elapsed_milliseconds_allowed"),
        "game_round_events",
        "elapsed_milliseconds BETWEEN 0 AND 86400000",
    )
