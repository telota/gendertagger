"""Seal accepted dependencies and capture immutable project-worker claim receipts.

Revision ID: 20261004_0014
Revises: 20261003_0013
Created: 2026-10-04 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261004_0014"
down_revision: str | None = "20261003_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_batch_provenance_guard(*, include_worker_provenance: bool) -> None:
    receipt_argument = ", 'worker_provenance'" if include_worker_provenance else ""
    op.execute(
        sa.text(
            """CREATE TRIGGER trg_task_batches_provenance
            BEFORE UPDATE ON task_batches
            FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_provenance_columns(
                'status',
                'worker_task_id',
                'attempt_count',
                'success_count',
                'abstain_count',
                'error_count',
                'started_at',
                'finished_at',
                'failure_class',
                'failure_diagnostic'"""
            + receipt_argument
            + "\n            )"
        )
    )


def upgrade() -> None:
    """Keep historical evidence unknown and require receipts only for new claims."""
    op.add_column(
        "runs",
        sa.Column("dependency_versions", postgresql.JSONB(none_as_null=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_runs_dependency_versions_object"),
        "runs",
        "dependency_versions IS NULL OR jsonb_typeof(dependency_versions) = 'object'",
    )
    op.add_column(
        "task_batches",
        sa.Column("worker_provenance", postgresql.JSONB(none_as_null=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_task_batches_worker_provenance_object"),
        "task_batches",
        "worker_provenance IS NULL OR jsonb_typeof(worker_provenance) = 'object'",
    )
    # The existing Run guard seals every column except its lifecycle allowlist,
    # so the new accepted dependency map is automatically immutable.
    op.execute(
        sa.text(
            """CREATE FUNCTION gendertagger_protect_task_batch_worker_provenance()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    IF NEW.worker_provenance IS NOT NULL THEN
                        RAISE EXCEPTION USING
                            ERRCODE = '55000',
                            MESSAGE = 'task batch worker provenance requires an initial claim';
                    END IF;
                ELSIF OLD.status IN ('pending', 'queued') AND NEW.status = 'running' THEN
                    IF OLD.worker_provenance IS NOT NULL OR NEW.worker_provenance IS NULL THEN
                        RAISE EXCEPTION USING
                            ERRCODE = '55000',
                            MESSAGE = 'task batch worker provenance is required at initial claim';
                    END IF;
                ELSIF NEW.worker_provenance IS DISTINCT FROM OLD.worker_provenance THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '55000',
                        MESSAGE = 'task batch worker provenance is immutable after initial claim';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER trg_task_batches_worker_provenance
            BEFORE INSERT OR UPDATE ON task_batches
            FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_task_batch_worker_provenance();"""
        )
    )
    op.execute(sa.text("DROP TRIGGER trg_task_batches_provenance ON task_batches"))
    _create_batch_provenance_guard(include_worker_provenance=True)


def downgrade() -> None:
    """Restore the pre-receipt guard and remove only newly introduced evidence."""
    op.execute(sa.text("DROP TRIGGER trg_task_batches_worker_provenance ON task_batches"))
    op.execute(sa.text("DROP FUNCTION gendertagger_protect_task_batch_worker_provenance()"))
    op.execute(sa.text("DROP TRIGGER trg_task_batches_provenance ON task_batches"))
    _create_batch_provenance_guard(include_worker_provenance=False)
    op.drop_constraint(
        op.f("ck_task_batches_worker_provenance_object"), "task_batches", type_="check"
    )
    op.drop_column("task_batches", "worker_provenance")
    op.drop_constraint(op.f("ck_runs_dependency_versions_object"), "runs", type_="check")
    op.drop_column("runs", "dependency_versions")
