"""Bind immutable scientific outputs to sealed execution lifecycles.

Revision ID: 20260814_0008
Revises: 20260814_0007
Created: 2026-08-14 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0008"
down_revision: str | None = "20260814_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Seal execution provenance and lifecycle-bound output writes."""
    op.alter_column(
        "predictions",
        "task_batch_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    op.execute(
        """
        CREATE FUNCTION gendertagger_protect_lifecycle_row()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            legal_transition boolean;
            terminal_status boolean;
            started_at_required boolean;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION USING
                    ERRCODE = '55000',
                    MESSAGE = format('%s lifecycle rows cannot be deleted', TG_TABLE_NAME);
            ELSIF TG_OP = 'INSERT' THEN
                legal_transition := CASE TG_TABLE_NAME
                    WHEN 'runs' THEN NEW.status = 'created'
                    WHEN 'method_executions' THEN NEW.status = 'pending'
                    WHEN 'task_batches' THEN NEW.status = 'pending'
                    WHEN 'aggregation_executions' THEN NEW.status = 'pending'
                    ELSE false
                END;
            ELSIF OLD.status IS NOT DISTINCT FROM NEW.status THEN
                terminal_status := CASE TG_TABLE_NAME
                    WHEN 'runs' THEN OLD.status IN (
                        'completed',
                        'completed_with_errors',
                        'failed',
                        'cancelled'
                    )
                    WHEN 'method_executions' THEN OLD.status IN (
                        'completed',
                        'completed_with_errors',
                        'failed',
                        'cancelled'
                    )
                    WHEN 'task_batches' THEN OLD.status IN (
                        'completed',
                        'failed',
                        'cancelled'
                    )
                    WHEN 'aggregation_executions' THEN OLD.status IN (
                        'completed',
                        'failed',
                        'cancelled'
                    )
                    ELSE false
                END;
                IF terminal_status AND to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '55000',
                        MESSAGE = format('terminal %s rows are immutable', TG_TABLE_NAME);
                END IF;
                legal_transition := true;
            ELSE
                legal_transition := CASE TG_TABLE_NAME
                    WHEN 'runs' THEN
                        (OLD.status = 'created' AND NEW.status = 'queued')
                        OR (OLD.status = 'queued' AND NEW.status = 'running')
                        OR (
                            OLD.status = 'running'
                            AND NEW.status IN (
                                'completed',
                                'completed_with_errors',
                                'failed',
                                'cancelled'
                            )
                        )
                        OR (
                            OLD.status IN ('created', 'queued')
                            AND NEW.status = 'cancelled'
                        )
                    WHEN 'method_executions' THEN
                        (OLD.status = 'pending' AND NEW.status = 'queued')
                        OR (OLD.status = 'queued' AND NEW.status = 'running')
                        OR (
                            OLD.status = 'running'
                            AND NEW.status IN (
                                'completed',
                                'completed_with_errors',
                                'failed',
                                'cancelled'
                            )
                        )
                        OR (
                            OLD.status IN ('pending', 'queued')
                            AND NEW.status = 'cancelled'
                        )
                    WHEN 'task_batches' THEN
                        (OLD.status = 'pending' AND NEW.status IN ('queued', 'running'))
                        OR (OLD.status = 'queued' AND NEW.status = 'running')
                        OR (
                            OLD.status = 'running'
                            AND NEW.status IN ('completed', 'failed', 'cancelled')
                        )
                        OR (
                            OLD.status IN ('pending', 'queued')
                            AND NEW.status = 'cancelled'
                        )
                    WHEN 'aggregation_executions' THEN
                        (OLD.status = 'pending' AND NEW.status IN ('queued', 'running'))
                        OR (OLD.status = 'queued' AND NEW.status = 'running')
                        OR (
                            OLD.status = 'running'
                            AND NEW.status IN ('completed', 'failed', 'cancelled')
                        )
                        OR (
                            OLD.status IN ('pending', 'queued')
                            AND NEW.status = 'cancelled'
                        )
                    ELSE false
                END;
            END IF;

            IF NOT legal_transition THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = format('ck_%s_lifecycle_transition', TG_TABLE_NAME),
                    MESSAGE = format(
                        'illegal %s lifecycle transition to %s',
                        TG_TABLE_NAME,
                        NEW.status
                    );
            END IF;

            IF TG_OP = 'INSERT' AND TG_TABLE_NAME = 'method_executions' THEN
                -- Deliberately create a new parent tuple version instead of only
                -- taking a row lock.  A terminal transition that began under a
                -- fixed REPEATABLE READ snapshot must then serialize-fail rather
                -- than miss this newly committed child after its lock wait.
                UPDATE runs AS parent
                SET status = parent.status
                WHERE parent.id = NEW.run_id
                  AND parent.status IN ('created', 'queued', 'running');
                IF NOT FOUND THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        CONSTRAINT = 'method_executions_parent_run_open',
                        MESSAGE = 'a method execution requires a non-terminal parent run';
                END IF;
            END IF;

            IF TG_OP = 'INSERT' AND TG_TABLE_NAME = 'task_batches' THEN
                UPDATE method_executions AS parent
                SET status = parent.status
                WHERE parent.id = NEW.method_execution_id
                  AND parent.status IN ('pending', 'queued', 'running');
                IF NOT FOUND THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        CONSTRAINT = 'task_batches_parent_execution_open',
                        MESSAGE = 'a task batch requires a non-terminal parent execution';
                END IF;
            END IF;

            IF TG_OP = 'INSERT' AND TG_TABLE_NAME = 'aggregation_executions' THEN
                PERFORM 1
                FROM runs
                WHERE id = NEW.run_id
                FOR SHARE;
                IF NOT FOUND THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        CONSTRAINT = 'aggregation_executions_parent_run_exists',
                        MESSAGE = 'an aggregation requires an existing parent run';
                END IF;
            END IF;

            IF TG_OP = 'UPDATE'
                AND TG_TABLE_NAME = 'aggregation_executions'
                AND OLD.status = 'pending'
                AND NEW.status IN ('queued', 'running')
                AND NOT EXISTS (
                    SELECT 1
                    FROM aggregation_method_executions
                    WHERE aggregation_execution_id = NEW.id
                    GROUP BY aggregation_execution_id
                    HAVING min(position) = 0
                       AND max(position) = count(*) - 1
                       AND count(*) > 0
                )
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'aggregation_executions_contiguous_membership',
                    MESSAGE = 'a queued aggregation requires nonempty contiguous membership';
            END IF;

            IF TG_OP = 'UPDATE'
                AND OLD.status IS DISTINCT FROM NEW.status
                AND TG_TABLE_NAME = 'method_executions'
                AND NEW.status IN (
                    'completed',
                    'completed_with_errors',
                    'failed',
                    'cancelled'
                )
                AND EXISTS (
                    SELECT 1
                    FROM task_batches
                    WHERE method_execution_id = NEW.id
                      AND status NOT IN ('completed', 'failed', 'cancelled')
                )
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'method_executions_terminal_batches',
                    MESSAGE = 'a method execution cannot finish before all task batches are terminal';
            END IF;

            IF TG_OP = 'UPDATE'
                AND OLD.status IS DISTINCT FROM NEW.status
                AND TG_TABLE_NAME = 'runs'
                AND NEW.status IN (
                    'completed',
                    'completed_with_errors',
                    'failed',
                    'cancelled'
                )
                AND EXISTS (
                    SELECT 1
                    FROM method_executions
                    WHERE run_id = NEW.id
                      AND status NOT IN (
                          'completed',
                          'completed_with_errors',
                          'failed',
                          'cancelled'
                      )
                )
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'runs_terminal_method_executions',
                    MESSAGE = 'a run cannot finish before all method executions are terminal';
            END IF;

            terminal_status := CASE TG_TABLE_NAME
                WHEN 'runs' THEN NEW.status IN (
                    'completed',
                    'completed_with_errors',
                    'failed',
                    'cancelled'
                )
                WHEN 'method_executions' THEN NEW.status IN (
                    'completed',
                    'completed_with_errors',
                    'failed',
                    'cancelled'
                )
                WHEN 'task_batches' THEN NEW.status IN (
                    'completed',
                    'failed',
                    'cancelled'
                )
                WHEN 'aggregation_executions' THEN NEW.status IN (
                    'completed',
                    'failed',
                    'cancelled'
                )
                ELSE false
            END;
            started_at_required := CASE TG_TABLE_NAME
                WHEN 'runs' THEN NEW.status IN (
                    'running',
                    'completed',
                    'completed_with_errors',
                    'failed'
                )
                WHEN 'method_executions' THEN NEW.status IN (
                    'running',
                    'completed',
                    'completed_with_errors',
                    'failed'
                )
                WHEN 'task_batches' THEN NEW.status IN ('running', 'completed', 'failed')
                WHEN 'aggregation_executions' THEN NEW.status IN (
                    'running',
                    'completed',
                    'failed'
                )
                ELSE false
            END;

            IF (terminal_status AND NEW.finished_at IS NULL)
                OR (NOT terminal_status AND NEW.finished_at IS NOT NULL)
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = format('ck_%s_lifecycle_timestamps', TG_TABLE_NAME),
                    MESSAGE = format('%s status and finished_at are inconsistent', TG_TABLE_NAME);
            END IF;
            IF started_at_required AND NEW.started_at IS NULL THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = format('ck_%s_lifecycle_timestamps', TG_TABLE_NAME),
                    MESSAGE = format('%s status requires started_at', TG_TABLE_NAME);
            END IF;
            IF NOT started_at_required
                AND NEW.status <> 'cancelled'
                AND NEW.started_at IS NOT NULL
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = format('ck_%s_lifecycle_timestamps', TG_TABLE_NAME),
                    MESSAGE = format('%s status forbids started_at', TG_TABLE_NAME);
            END IF;

            IF TG_TABLE_NAME = 'runs' THEN
                IF NEW.status = 'failed'
                    AND (
                        NEW.failure_diagnostic IS NULL
                        OR btrim(NEW.failure_diagnostic) = ''
                    )
                THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        CONSTRAINT = 'ck_runs_lifecycle_failure',
                        MESSAGE = 'a failed run requires a failure diagnostic';
                ELSIF NEW.status <> 'failed' AND NEW.failure_diagnostic IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        CONSTRAINT = 'ck_runs_lifecycle_failure',
                        MESSAGE = 'only a failed run may have a failure diagnostic';
                END IF;
            ELSE
                IF NEW.status = 'failed'
                    AND (
                        NEW.failure_diagnostic IS NULL
                        OR btrim(NEW.failure_diagnostic) = ''
                    )
                THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        CONSTRAINT = format('ck_%s_lifecycle_failure', TG_TABLE_NAME),
                        MESSAGE = format(
                            'a failed %s row requires a failure diagnostic',
                            TG_TABLE_NAME
                        );
                ELSIF NEW.status <> 'failed'
                    AND (
                        NEW.failure_class IS NOT NULL
                        OR NEW.failure_diagnostic IS NOT NULL
                    )
                THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        CONSTRAINT = format('ck_%s_lifecycle_failure', TG_TABLE_NAME),
                        MESSAGE = format(
                            'only a failed %s row may have failure details',
                            TG_TABLE_NAME
                        );
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION gendertagger_protect_provenance_columns()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF (to_jsonb(OLD) - TG_ARGV) IS DISTINCT FROM (to_jsonb(NEW) - TG_ARGV) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '55000',
                    MESSAGE = format('%s provenance is immutable', TG_TABLE_NAME);
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """CREATE TRIGGER trg_runs_lifecycle
        BEFORE INSERT OR UPDATE OR DELETE ON runs
        FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_lifecycle_row()"""
    )
    op.execute(
        """CREATE TRIGGER trg_runs_provenance
        BEFORE UPDATE ON runs
        FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_provenance_columns(
            'status',
            'started_at',
            'finished_at',
            'failure_diagnostic'
        )"""
    )
    op.execute(
        """CREATE TRIGGER trg_method_executions_lifecycle
        BEFORE INSERT OR UPDATE OR DELETE ON method_executions
        FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_lifecycle_row()"""
    )
    op.execute(
        """CREATE TRIGGER trg_method_executions_provenance
        BEFORE UPDATE ON method_executions
        FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_provenance_columns(
            'status',
            'completed_count',
            'failed_count',
            'started_at',
            'finished_at',
            'failure_class',
            'failure_diagnostic'
        )"""
    )
    op.execute(
        """CREATE TRIGGER trg_task_batches_lifecycle
        BEFORE INSERT OR UPDATE OR DELETE ON task_batches
        FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_lifecycle_row()"""
    )
    op.execute(
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
            'failure_diagnostic'
        )"""
    )
    op.execute(
        """CREATE TRIGGER trg_aggregation_executions_lifecycle
        BEFORE INSERT OR UPDATE OR DELETE ON aggregation_executions
        FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_lifecycle_row()"""
    )
    op.execute(
        """CREATE TRIGGER trg_aggregation_executions_provenance
        BEFORE UPDATE ON aggregation_executions
        FOR EACH ROW EXECUTE FUNCTION gendertagger_protect_provenance_columns(
            'status',
            'started_at',
            'finished_at',
            'failure_class',
            'failure_diagnostic'
        )"""
    )

    op.execute(
        """
        CREATE FUNCTION gendertagger_validate_prediction_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            protected_snapshot_id uuid;
            protected_record_offset integer;
            protected_record_count integer;
        BEGIN
            SELECT
                run.dataset_snapshot_id,
                batch.record_offset,
                batch.record_count
            INTO
                protected_snapshot_id,
                protected_record_offset,
                protected_record_count
            FROM task_batches AS batch
            JOIN method_executions AS execution
              ON execution.id = batch.method_execution_id
            JOIN runs AS run
              ON run.id = execution.run_id
            WHERE batch.id = NEW.task_batch_id
              AND batch.method_execution_id = NEW.method_execution_id
              AND batch.status = 'running'
              AND execution.status = 'running'
              AND run.status = 'running';

            IF NOT FOUND THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'predictions_running_execution_ownership',
                    MESSAGE = 'prediction writes require one running owning run, execution, and batch';
            END IF;

            PERFORM 1
            FROM person_records AS person
            WHERE person.id = NEW.person_record_id
              AND person.dataset_snapshot_id = protected_snapshot_id
              AND person.id IN (
                  SELECT expected.id
                  FROM person_records AS expected
                  WHERE expected.dataset_snapshot_id = protected_snapshot_id
                  ORDER BY expected.tei_id, expected.id
                  OFFSET protected_record_offset
                  LIMIT protected_record_count
              );

            IF NOT FOUND THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'predictions_batch_person_ownership',
                    MESSAGE = 'prediction person must belong to the owning batch slice';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_predictions_validate_insert
        BEFORE INSERT ON predictions
        FOR EACH ROW EXECUTE FUNCTION gendertagger_validate_prediction_insert()"""
    )

    op.execute(
        """
        CREATE FUNCTION gendertagger_validate_aggregated_result_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            protected_snapshot_id uuid;
        BEGIN
            SELECT run.dataset_snapshot_id
            INTO protected_snapshot_id
            FROM aggregation_executions AS aggregation
            JOIN runs AS run
              ON run.id = aggregation.run_id
            WHERE aggregation.id = NEW.aggregation_execution_id
              AND aggregation.status = 'running';

            IF NOT FOUND THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'aggregated_results_running_aggregation',
                    MESSAGE = 'aggregation result writes require a running aggregation';
            END IF;

            PERFORM 1
            FROM person_records AS person
            WHERE person.id = NEW.person_record_id
              AND person.dataset_snapshot_id = protected_snapshot_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'aggregated_results_snapshot_person_ownership',
                    MESSAGE = 'aggregation result person must belong to the run snapshot';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_aggregated_results_validate_insert
        BEFORE INSERT ON aggregated_results
        FOR EACH ROW EXECUTE FUNCTION gendertagger_validate_aggregated_result_insert()"""
    )

    op.execute(
        """
        CREATE FUNCTION gendertagger_validate_aggregation_membership()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            protected_run_id uuid;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION USING
                    ERRCODE = '55000',
                    MESSAGE = 'aggregation method-execution membership is immutable';
            END IF;

            -- As with execution children, advance the parent tuple version so a
            -- fixed-snapshot status transition cannot miss committed membership.
            UPDATE aggregation_executions AS aggregation
            SET status = aggregation.status
            WHERE aggregation.id = NEW.aggregation_execution_id
              AND aggregation.status = 'pending'
            RETURNING aggregation.run_id INTO protected_run_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION USING
                    ERRCODE = '55000',
                    MESSAGE = 'aggregation membership may only be added while pending';
            END IF;

            PERFORM 1
            FROM method_executions AS execution
            WHERE execution.id = NEW.method_execution_id
              AND execution.run_id = protected_run_id
              AND execution.status IN ('completed', 'completed_with_errors')
            FOR SHARE OF execution;

            IF NOT FOUND THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'aggregation_membership_execution_ownership',
                    MESSAGE = 'aggregation members must be completed executions from its run';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_aggregation_methods_validate_mutation
        BEFORE INSERT OR UPDATE OR DELETE ON aggregation_method_executions
        FOR EACH ROW EXECUTE FUNCTION gendertagger_validate_aggregation_membership()"""
    )

    op.execute(
        """
        CREATE FUNCTION gendertagger_require_completed_prediction_parent()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM task_batches
                WHERE id = NEW.task_batch_id
                  AND status = 'completed'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'predictions_completed_batch',
                    MESSAGE = 'committed predictions require a completed task batch';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """CREATE CONSTRAINT TRIGGER trg_predictions_parent_completed
        AFTER INSERT ON predictions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION gendertagger_require_completed_prediction_parent()"""
    )

    op.execute(
        """
        CREATE FUNCTION gendertagger_validate_completed_batch_coverage()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            protected_snapshot_id uuid;
            protected_record_offset integer;
            protected_record_count integer;
            protected_success_count integer;
            protected_abstain_count integer;
            protected_error_count integer;
            expected_count bigint;
            actual_count bigint;
            actual_success_count bigint;
            actual_abstain_count bigint;
            actual_error_count bigint;
            coverage_mismatch boolean;
        BEGIN
            SELECT
                run.dataset_snapshot_id,
                batch.record_offset,
                batch.record_count,
                batch.success_count,
                batch.abstain_count,
                batch.error_count
            INTO
                protected_snapshot_id,
                protected_record_offset,
                protected_record_count,
                protected_success_count,
                protected_abstain_count,
                protected_error_count
            FROM task_batches AS batch
            JOIN method_executions AS execution
              ON execution.id = batch.method_execution_id
            JOIN runs AS run
              ON run.id = execution.run_id
            WHERE batch.id = NEW.id
              AND batch.status = 'completed';

            IF NOT FOUND THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'task_batches_completed_prediction_coverage',
                    MESSAGE = 'completed task batch no longer exists in completed state';
            END IF;

            WITH expected AS (
                SELECT person.id
                FROM person_records AS person
                WHERE person.dataset_snapshot_id = protected_snapshot_id
                ORDER BY person.tei_id, person.id
                OFFSET protected_record_offset
                LIMIT protected_record_count
            ),
            actual AS (
                SELECT prediction.person_record_id, prediction.status
                FROM predictions AS prediction
                WHERE prediction.task_batch_id = NEW.id
            )
            SELECT
                (SELECT count(*) FROM expected),
                (SELECT count(*) FROM actual),
                (SELECT count(*) FROM actual WHERE status = 'success'),
                (SELECT count(*) FROM actual WHERE status = 'abstain'),
                (SELECT count(*) FROM actual WHERE status = 'error'),
                EXISTS (
                    SELECT id FROM expected
                    EXCEPT
                    SELECT person_record_id FROM actual
                ) OR EXISTS (
                    SELECT person_record_id FROM actual
                    EXCEPT
                    SELECT id FROM expected
                )
            INTO
                expected_count,
                actual_count,
                actual_success_count,
                actual_abstain_count,
                actual_error_count,
                coverage_mismatch;

            IF expected_count <> protected_record_count
                OR actual_count <> protected_record_count
                OR coverage_mismatch
                OR actual_success_count <> protected_success_count
                OR actual_abstain_count <> protected_abstain_count
                OR actual_error_count <> protected_error_count
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'task_batches_completed_prediction_coverage',
                    MESSAGE = 'completed task batch requires exact prediction coverage and tallies';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """CREATE CONSTRAINT TRIGGER trg_task_batches_prediction_coverage
        AFTER UPDATE ON task_batches
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        WHEN (NEW.status = 'completed')
        EXECUTE FUNCTION gendertagger_validate_completed_batch_coverage()"""
    )

    op.execute(
        """
        CREATE FUNCTION gendertagger_require_completed_result_parent()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM aggregation_executions
                WHERE id = NEW.aggregation_execution_id
                  AND status = 'completed'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'aggregated_results_completed_aggregation',
                    MESSAGE = 'committed results require a completed aggregation';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """CREATE CONSTRAINT TRIGGER trg_aggregated_results_parent_completed
        AFTER INSERT ON aggregated_results
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION gendertagger_require_completed_result_parent()"""
    )

    op.execute(
        """
        CREATE FUNCTION gendertagger_validate_completed_aggregation_coverage()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            protected_snapshot_id uuid;
            declared_record_count integer;
            expected_count bigint;
            actual_count bigint;
            coverage_mismatch boolean;
        BEGIN
            SELECT run.dataset_snapshot_id, snapshot.record_count
            INTO protected_snapshot_id, declared_record_count
            FROM aggregation_executions AS aggregation
            JOIN runs AS run
              ON run.id = aggregation.run_id
            JOIN dataset_snapshots AS snapshot
              ON snapshot.id = run.dataset_snapshot_id
            WHERE aggregation.id = NEW.id
              AND aggregation.status = 'completed'
              AND snapshot.status = 'ready';

            IF NOT FOUND OR declared_record_count IS NULL THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'aggregation_executions_completed_result_coverage',
                    MESSAGE = 'completed aggregation requires a ready counted run snapshot';
            END IF;

            WITH expected AS (
                SELECT person.id
                FROM person_records AS person
                WHERE person.dataset_snapshot_id = protected_snapshot_id
            ),
            actual AS (
                SELECT result.person_record_id
                FROM aggregated_results AS result
                WHERE result.aggregation_execution_id = NEW.id
            )
            SELECT
                (SELECT count(*) FROM expected),
                (SELECT count(*) FROM actual),
                EXISTS (
                    SELECT id FROM expected
                    EXCEPT
                    SELECT person_record_id FROM actual
                ) OR EXISTS (
                    SELECT person_record_id FROM actual
                    EXCEPT
                    SELECT id FROM expected
                )
            INTO expected_count, actual_count, coverage_mismatch;

            IF expected_count <> declared_record_count
                OR actual_count <> declared_record_count
                OR coverage_mismatch
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    CONSTRAINT = 'aggregation_executions_completed_result_coverage',
                    MESSAGE = 'completed aggregation requires one result per snapshot person';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """CREATE CONSTRAINT TRIGGER trg_aggregation_executions_result_coverage
        AFTER UPDATE ON aggregation_executions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        WHEN (NEW.status = 'completed')
        EXECUTE FUNCTION gendertagger_validate_completed_aggregation_coverage()"""
    )


def downgrade() -> None:
    """Remove execution provenance and lifecycle output guards."""
    op.execute("DROP TRIGGER trg_aggregation_executions_result_coverage ON aggregation_executions")
    op.execute("DROP TRIGGER trg_aggregated_results_parent_completed ON aggregated_results")
    op.execute("DROP TRIGGER trg_task_batches_prediction_coverage ON task_batches")
    op.execute("DROP TRIGGER trg_predictions_parent_completed ON predictions")
    op.execute(
        "DROP TRIGGER trg_aggregation_methods_validate_mutation ON aggregation_method_executions"
    )
    op.execute("DROP TRIGGER trg_aggregated_results_validate_insert ON aggregated_results")
    op.execute("DROP TRIGGER trg_predictions_validate_insert ON predictions")

    op.execute("DROP TRIGGER trg_aggregation_executions_provenance ON aggregation_executions")
    op.execute("DROP TRIGGER trg_aggregation_executions_lifecycle ON aggregation_executions")
    op.execute("DROP TRIGGER trg_task_batches_provenance ON task_batches")
    op.execute("DROP TRIGGER trg_task_batches_lifecycle ON task_batches")
    op.execute("DROP TRIGGER trg_method_executions_provenance ON method_executions")
    op.execute("DROP TRIGGER trg_method_executions_lifecycle ON method_executions")
    op.execute("DROP TRIGGER trg_runs_provenance ON runs")
    op.execute("DROP TRIGGER trg_runs_lifecycle ON runs")

    op.execute("DROP FUNCTION gendertagger_validate_completed_aggregation_coverage()")
    op.execute("DROP FUNCTION gendertagger_require_completed_result_parent()")
    op.execute("DROP FUNCTION gendertagger_validate_completed_batch_coverage()")
    op.execute("DROP FUNCTION gendertagger_require_completed_prediction_parent()")
    op.execute("DROP FUNCTION gendertagger_validate_aggregation_membership()")
    op.execute("DROP FUNCTION gendertagger_validate_aggregated_result_insert()")
    op.execute("DROP FUNCTION gendertagger_validate_prediction_insert()")
    op.execute("DROP FUNCTION gendertagger_protect_provenance_columns()")
    op.execute("DROP FUNCTION gendertagger_protect_lifecycle_row()")

    op.alter_column(
        "predictions",
        "task_batch_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
