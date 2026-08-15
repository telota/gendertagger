"""evaluation executions

Revision ID: 20260814_0010
Revises: 20260814_0009
Created: 2026-08-15 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0010"
down_revision: str | None = "20260814_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add evaluation executions, their method membership, and report linkage."""
    op.create_table(
        "evaluation_executions",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("aggregation_execution_id", sa.UUID(), nullable=True),
        sa.Column("definition", sa.String(length=100), nullable=False),
        sa.Column(
            "resolved_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "queued",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="evaluation_execution_status",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("report_artifact_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_class", sa.String(length=255), nullable=True),
        sa.Column("failure_diagnostic", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "config_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_evaluation_executions_config_sha256_format"),
        ),
        sa.CheckConstraint(
            "definition ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name=op.f("ck_evaluation_executions_definition_format"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'queued', 'running', 'completed', 'failed', 'cancelled')",
            name=op.f("ck_evaluation_executions_status_allowed"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NOT NULL",
            name=op.f("ck_evaluation_executions_evaluation_timing_order_present"),
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR report_artifact_id IS NOT NULL",
            name=op.f("ck_evaluation_executions_completed_evaluation_has_report"),
        ),
        sa.CheckConstraint(
            "status = 'completed' OR report_artifact_id IS NULL",
            name=op.f("ck_evaluation_executions_only_completed_evaluation_has_report"),
        ),
        sa.ForeignKeyConstraint(
            ["aggregation_execution_id"],
            ["aggregation_executions.id"],
            name=op.f("fk_evaluation_executions_aggregation_execution_id_aggregation_executions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["report_artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_evaluation_executions_report_artifact_id_artifacts"),
            ondelete="RESTRICT",
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_evaluation_executions_run_id_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_executions")),
    )
    op.create_index(
        "ix_evaluation_executions_run_id_status",
        "evaluation_executions",
        ["run_id", "status"],
        unique=False,
    )
    op.create_table(
        "evaluation_method_executions",
        sa.Column("evaluation_execution_id", sa.UUID(), nullable=False),
        sa.Column("method_execution_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_evaluation_method_executions_position_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_execution_id"],
            ["evaluation_executions.id"],
            name=op.f(
                "fk_evaluation_method_executions_evaluation_execution_id_evaluation_executions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["method_execution_id"],
            ["method_executions.id"],
            name=op.f("fk_evaluation_method_executions_method_execution_id_method_executions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "evaluation_execution_id",
            "method_execution_id",
            name="pk_evaluation_method_executions",
        ),
        sa.UniqueConstraint("evaluation_execution_id", "position", name="evaluation_position"),
    )
    op.add_column(
        "artifacts",
        sa.Column("evaluation_execution_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_artifacts_evaluation_execution_id_evaluation_executions"),
        "artifacts",
        "evaluation_executions",
        ["evaluation_execution_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_evaluation_executions_report_artifact_id_artifacts"),
        "evaluation_executions",
        "artifacts",
        ["report_artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Remove evaluation executions, their method membership, and report linkage."""
    op.drop_constraint(
        op.f("fk_evaluation_executions_report_artifact_id_artifacts"),
        "evaluation_executions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_artifacts_evaluation_execution_id_evaluation_executions"),
        "artifacts",
        type_="foreignkey",
    )
    op.drop_column("artifacts", "evaluation_execution_id")
    op.drop_table("evaluation_method_executions")
    op.drop_index("ix_evaluation_executions_run_id_status", table_name="evaluation_executions")
    op.drop_table("evaluation_executions")
