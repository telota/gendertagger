"""Persist server-scored game rounds and their annotation evidence.

Revision ID: 20260926_0010
Revises: 20260926_0009
Created: 2026-09-26 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0010"
down_revision: str | None = "20260926_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable project rounds and their ordered scoring evidence."""
    op.create_table(
        "game_rounds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("aggregation_execution_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_user_id", sa.UUID(), nullable=False),
        sa.Column("round_size", sa.Integer(), nullable=False),
        sa.Column("timer_enabled", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("duration_milliseconds", sa.BigInteger(), nullable=False),
        sa.Column("answered_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("longest_streak", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "round_size IN (10, 20, 50)",
            name=op.f("ck_game_rounds_round_size_allowed"),
        ),
        sa.CheckConstraint("score >= 0", name=op.f("ck_game_rounds_score_nonnegative")),
        sa.CheckConstraint(
            "duration_milliseconds >= 0",
            name=op.f("ck_game_rounds_duration_nonnegative"),
        ),
        sa.CheckConstraint(
            "answered_count >= 0",
            name=op.f("ck_game_rounds_answered_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "skipped_count >= 0",
            name=op.f("ck_game_rounds_skipped_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "answered_count + skipped_count BETWEEN 1 AND round_size",
            name=op.f("ck_game_rounds_question_count_within_round"),
        ),
        sa.CheckConstraint(
            "longest_streak BETWEEN 0 AND answered_count",
            name=op.f("ck_game_rounds_longest_streak_within_answers"),
        ),
        sa.ForeignKeyConstraint(
            ["aggregation_execution_id"],
            ["aggregation_executions.id"],
            name=op.f("fk_game_rounds_aggregation_execution_id_aggregation_executions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_game_rounds_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            name=op.f("fk_game_rounds_reviewer_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_rounds")),
    )
    op.create_index(
        "ix_game_rounds_project_id_round_size_score",
        "game_rounds",
        ["project_id", "round_size", "score"],
        unique=False,
    )
    op.create_index(
        "ix_game_rounds_reviewer_user_id_created_at",
        "game_rounds",
        ["reviewer_user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "game_round_events",
        sa.Column("game_round_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=6), nullable=False),
        sa.Column("annotation_id", sa.UUID(), nullable=True),
        sa.Column("elapsed_milliseconds", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0", name=op.f("ck_game_round_events_position_nonnegative")),
        sa.CheckConstraint(
            "kind IN ('answer', 'skip')",
            name=op.f("ck_game_round_events_kind_allowed"),
        ),
        sa.CheckConstraint(
            "(kind = 'answer' AND annotation_id IS NOT NULL) OR "
            "(kind = 'skip' AND annotation_id IS NULL)",
            name=op.f("ck_game_round_events_kind_annotation_consistent"),
        ),
        sa.CheckConstraint(
            "elapsed_milliseconds BETWEEN 0 AND 86400000",
            name=op.f("ck_game_round_events_elapsed_milliseconds_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["annotation_id"],
            ["annotations.id"],
            name=op.f("fk_game_round_events_annotation_id_annotations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["game_round_id"],
            ["game_rounds.id"],
            name=op.f("fk_game_round_events_game_round_id_game_rounds"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "game_round_id",
            "position",
            name=op.f("pk_game_round_events"),
        ),
        sa.UniqueConstraint(
            "annotation_id",
            name=op.f("uq_game_round_events_annotation_scored_once"),
        ),
    )


def downgrade() -> None:
    """Remove game scores without changing their source annotations."""
    op.drop_table("game_round_events")
    op.drop_index(
        "ix_game_rounds_reviewer_user_id_created_at",
        table_name="game_rounds",
    )
    op.drop_index(
        "ix_game_rounds_project_id_round_size_score",
        table_name="game_rounds",
    )
    op.drop_table("game_rounds")
