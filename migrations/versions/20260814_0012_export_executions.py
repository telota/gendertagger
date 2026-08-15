"""export executions

Revision ID: 20260814_0012
Revises: 20260814_0011
Created: 2026-08-15 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0012"
down_revision: str | None = "20260814_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add export executions and their manifest artifact linkage."""
    op.create_table(
        "export_executions",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("aggregation_execution_id", sa.UUID(), nullable=False),
        sa.Column(
            "format",
            sa.Enum("tei", "json", "csv", name="export_format", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "label_source_policy",
            sa.Enum(
                "machine_aggregation",
                "human_overrides",
                name="export_label_source_policy",
                native_enum=False,
            ),
            server_default="machine_aggregation",
            nullable=False,
        ),
        sa.Column(
            "tei_profile",
            sa.Enum("tei_p5_gender_v1", name="tei_export_profile", native_enum=False),
            nullable=True,
        ),
        sa.Column("human_resp_id", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "queued",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="export_execution_status",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("manifest_artifact_id", sa.UUID(), nullable=True),
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
            "status IN ('pending', 'queued', 'running', 'completed', 'failed', 'cancelled')",
            name=op.f("ck_export_executions_status_allowed"),
        ),
        sa.CheckConstraint(
            "format IN ('tei', 'json', 'csv')",
            name=op.f("ck_export_executions_format_allowed"),
        ),
        sa.CheckConstraint(
            "label_source_policy IN ('machine_aggregation', 'human_overrides')",
            name=op.f("ck_export_executions_label_source_policy_allowed"),
        ),
        sa.CheckConstraint(
            "tei_profile IS NULL OR format = 'tei'",
            name=op.f("ck_export_executions_tei_profile_requires_tei_format"),
        ),
        sa.CheckConstraint(
            "format <> 'tei' OR tei_profile IS NOT NULL",
            name=op.f("ck_export_executions_tei_format_requires_tei_profile"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NOT NULL",
            name=op.f("ck_export_executions_export_timing_order_present"),
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR manifest_artifact_id IS NOT NULL",
            name=op.f("ck_export_executions_completed_export_has_manifest"),
        ),
        sa.CheckConstraint(
            "status = 'completed' OR manifest_artifact_id IS NULL",
            name=op.f("ck_export_executions_only_completed_export_has_manifest"),
        ),
        sa.ForeignKeyConstraint(
            ["aggregation_execution_id"],
            ["aggregation_executions.id"],
            name=op.f("fk_export_executions_aggregation_execution_id_aggregation_executions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_export_executions_manifest_artifact_id_artifacts"),
            ondelete="RESTRICT",
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_export_executions_run_id_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export_executions")),
    )
    op.create_index(
        "ix_export_executions_run_id_status",
        "export_executions",
        ["run_id", "status"],
        unique=False,
    )
    op.add_column(
        "artifacts",
        sa.Column("export_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_artifacts_export_id_export_executions"),
        "artifacts",
        "export_executions",
        ["export_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_export_executions_manifest_artifact_id_artifacts"),
        "export_executions",
        "artifacts",
        ["manifest_artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Remove export executions and their manifest artifact linkage."""
    op.drop_constraint(
        op.f("fk_export_executions_manifest_artifact_id_artifacts"),
        "export_executions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_artifacts_export_id_export_executions"),
        "artifacts",
        type_="foreignkey",
    )
    op.drop_column("artifacts", "export_id")
    op.drop_index("ix_export_executions_run_id_status", table_name="export_executions")
    op.drop_table("export_executions")
