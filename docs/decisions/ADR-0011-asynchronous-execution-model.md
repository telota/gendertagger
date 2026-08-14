# ADR-0011: Asynchronous batch execution model

**Status:** Accepted

## Context

Phase 4 introduces Celery execution over Redis. The queue coordinates work but is never the authoritative
store: runs, method executions, task batches, and predictions live in PostgreSQL. At-least-once delivery,
worker crashes, transient infrastructure faults, and per-method failures must not corrupt or discard persisted
scientific evidence. `docs/06-task-queue.md` sets the requirements; this ADR fixes the concrete contract.

## Decision

A `MethodExecution` is divided into persisted `TaskBatch` rows, each owning a deterministic person slice
(`record_offset`, `record_count`) over the immutable snapshot's `(tei_id, id)` ordering, so a batch's inputs
are reproducible from persisted state and a fixed batch size.

Batch execution is idempotent. Predictions are upserted under a `(method_execution_id, person_record_id)`
uniqueness constraint; a retry confirms identical output rather than appending duplicates, and re-running a
`completed` batch is a no-op. A batch is marked `running` only inside an uncommitted transaction, so a crashed
attempt rolls back to `pending` and redelivery re-runs cleanly.

Failures are classified. Scientific or configuration failures (contract violations, invalid adapter config,
an unregistered method) are permanent: the batch is failed immediately with a sanitized diagnostic and is not
retried. Other failures are treated as transient infrastructure faults: the task retries with exponential
backoff and full jitter, bounded to three attempts; on exhaustion the batch is failed so the run can still
complete. Record-level scientific failures remain `error` predictions, never exceptions.

Run and method-execution completion is derived under row locks so concurrent workers cannot double-finalize.
A method execution whose batches all complete is `completed`; any failed batch or record error makes it
`completed_with_errors`; all batches failing makes it `failed`. A run completes when all its executions are
terminal: `completed` when all succeeded, otherwise `completed_with_errors`, unless
`execution.fail_run_on_optional_method_error` is set and a method execution failed, which fails the run. One
failed optional classifier never discards another method's persisted predictions.

## Consequences

- Redis loss cannot destroy scientific results; recovery re-dispatches persisted `pending` batches.
- Runs surface partial success honestly instead of collapsing to a single pass/fail bit.
- The reference-completeness requirement (a run must fail clearly when required methods are unavailable) is a
  future aggregation-time gate; this ADR governs execution-time completion only.
- The queue can change without changing the public API, which returns persisted resources, never task IDs.
