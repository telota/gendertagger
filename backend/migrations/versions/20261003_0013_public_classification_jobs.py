"""Persist anonymous classification inputs, provenance, leases, and outbox delivery.

Revision ID: 20261003_0013
Revises: 20260926_0012
Created: 2026-10-03 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261003_0013"
down_revision: str | None = "20260926_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add immutable anonymous-job inputs and one unique durable dispatch per job."""
    op.create_table(
        "public_classification_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("retrieval_token_sha256", sa.String(length=64), nullable=False),
        sa.Column("queue_name", sa.String(length=100), server_default="cpu", nullable=False),
        sa.Column("names", postgresql.JSONB(), nullable=False),
        sa.Column("methods", postgresql.JSONB(), nullable=False),
        sa.Column("resolved_method_configs", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=9), server_default="queued", nullable=False),
        sa.Column("response", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("raw_predictions", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_id", sa.UUID(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_public_classification_jobs")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name=op.f("ck_public_classification_jobs_status_allowed"),
        ),
        sa.CheckConstraint(
            "retrieval_token_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_public_classification_jobs_retrieval_token_sha256_format"),
        ),
        sa.CheckConstraint(
            "queue_name ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'",
            name=op.f("ck_public_classification_jobs_queue_name_format"),
        ),
        sa.CheckConstraint(
            "(status = 'running' AND lease_id IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status <> 'running' AND lease_id IS NULL AND lease_until IS NULL)",
            name=op.f("ck_public_classification_jobs_lease_consistent"),
        ),
        sa.CheckConstraint(
            "(status = 'queued' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name=op.f("ck_public_classification_jobs_timestamps_consistent"),
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND response IS NOT NULL AND raw_predictions IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'failed' AND response IS NULL AND raw_predictions IS NULL "
            "AND failure_code = 'classification_failed') OR "
            "(status IN ('queued', 'running') AND response IS NULL AND raw_predictions IS NULL "
            "AND failure_code IS NULL)",
            name=op.f("ck_public_classification_jobs_result_consistent"),
        ),
    )
    op.create_index(
        "ix_public_classification_jobs_status_created_at",
        "public_classification_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_public_classification_jobs_status_lease_until",
        "public_classification_jobs",
        ["status", "lease_until"],
    )
    op.execute(
        sa.text(
            """CREATE FUNCTION gendertagger_public_classification_jobs_immutable()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.status IN ('completed', 'failed') THEN
                    RAISE EXCEPTION 'terminal public classification jobs are immutable';
                END IF;
                IF NEW.id IS DISTINCT FROM OLD.id
                    OR NEW.retrieval_token_sha256 IS DISTINCT FROM OLD.retrieval_token_sha256
                    OR NEW.queue_name IS DISTINCT FROM OLD.queue_name
                    OR NEW.names IS DISTINCT FROM OLD.names
                    OR NEW.methods IS DISTINCT FROM OLD.methods
                    OR NEW.resolved_method_configs IS DISTINCT FROM OLD.resolved_method_configs
                    OR NEW.provenance IS DISTINCT FROM OLD.provenance
                    OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'public classification inputs and provenance are immutable';
                END IF;
                IF (OLD.status = 'queued' AND NEW.status <> 'running')
                    OR (OLD.status = 'running' AND NEW.status NOT IN ('running', 'completed', 'failed'))
                    OR (OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at)
                    THEN
                    RAISE EXCEPTION 'invalid public classification lifecycle transition';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER trg_public_classification_jobs_immutable
            BEFORE UPDATE ON public_classification_jobs
            FOR EACH ROW EXECUTE FUNCTION gendertagger_public_classification_jobs_immutable();"""
        )
    )
    op.add_column("dispatch_outbox", sa.Column("classification_job_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_dispatch_outbox_classification_job_id_public_classification_jobs"),
        "dispatch_outbox",
        "public_classification_jobs",
        ["classification_job_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "classification_job_single_dispatch", "dispatch_outbox", ["classification_job_id"]
    )
    op.drop_constraint(
        op.f("ck_dispatch_outbox_exactly_one_target"), "dispatch_outbox", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_dispatch_outbox_exactly_one_target"),
        "dispatch_outbox",
        "num_nonnulls(task_batch_id, aggregation_execution_id, dataset_snapshot_id, "
        "evaluation_execution_id, export_execution_id, classification_job_id) = 1",
    )


def downgrade() -> None:
    """Remove anonymous jobs and their outbox entries while preserving other work."""
    op.execute(sa.text("DELETE FROM dispatch_outbox WHERE classification_job_id IS NOT NULL"))
    op.drop_constraint(
        op.f("ck_dispatch_outbox_exactly_one_target"), "dispatch_outbox", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_dispatch_outbox_exactly_one_target"),
        "dispatch_outbox",
        "num_nonnulls(task_batch_id, aggregation_execution_id, dataset_snapshot_id, "
        "evaluation_execution_id, export_execution_id) = 1",
    )
    op.drop_constraint("classification_job_single_dispatch", "dispatch_outbox", type_="unique")
    op.drop_constraint(
        op.f("fk_dispatch_outbox_classification_job_id_public_classification_jobs"),
        "dispatch_outbox",
        type_="foreignkey",
    )
    op.drop_column("dispatch_outbox", "classification_job_id")
    op.drop_table("public_classification_jobs")
    op.execute(sa.text("DROP FUNCTION gendertagger_public_classification_jobs_immutable()"))
