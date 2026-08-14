# ADR-0015: Transactional batch dispatch outbox

**Status:** Accepted

## Context

[ADR-0011](ADR-0011-asynchronous-execution-model.md) makes PostgreSQL authoritative for runs, method
executions, task batches, and scientific results. It requires recovery to re-dispatch persisted pending
batches after Redis loss. The initial Phase 4 implementation instead commits a run and all task batches
before the FastAPI request publishes their Celery messages directly.

PostgreSQL and Redis cannot participate in one atomic transaction. A broker failure after the database
commit can therefore leave a run marked active while some or all of its batches have no queued message.
Retrying the HTTP command cannot safely distinguish a lost publication from one accepted by Redis before
the connection failed. Direct publication from the API also couples API availability to an internal queue
mechanism that the public contract deliberately hides.

## Decision

Persist one Pydantic `BatchDispatch` for each `TaskBatch` in the PostgreSQL `batch_dispatches` transactional
outbox. Run scheduling uses `BatchDispatchCreate` to create the method executions, task batches, and their
small validated `TaskBatchMessage` dispatch intents in one database transaction. The transaction either
commits all durable work and intent or commits none of it. Dispatch status is `pending` until broker
publication succeeds and `published` afterward. FastAPI returns the persisted run after that commit and does
not publish Celery messages.

Scheduling claims the run with one conditional `created` to `queued` update before creating executions. Of
two concurrent scheduling commands, one owns the transaction and the other receives the existing
resource-state conflict rather than duplicating execution or leaking a database constraint error.

A separate long-running dispatch-coordinator process, started through `gendertagger.tasks.relay`, contains two
application services:

- `OutboxRelay` claims available outbox rows under short PostgreSQL leases, publishes them to their configured
  Celery queues, and records success or retry metadata;
- a slower `DispatchReconciler` detects expired relay leases, active pending batches missing an intent, and
  batches whose publication is stale without a worker claim, then creates or rearms outbox intent for the
  relay.

The coordinator uses the same application package, configuration, database, and deployable image as the API
and workers, but starts with a different command. It is not a Celery task: it must remain able to observe and
retry durable intent while the Celery broker is unavailable. The reconciler changes PostgreSQL state only;
the relay remains the sole component that publishes batch messages.

Publication is at least once. A relay can publish successfully and crash before recording success, so a later
lease holder may publish the same message again. Workers therefore claim a task batch with one ownership-aware
conditional database operation that verifies both `task_batch_id` and `method_execution_id` and transitions
only a dispatchable non-terminal state to `running`. Exactly one competing delivery obtains the claim;
duplicate, completed, failed, cancelled, or wrongly owned messages are no-ops or explicit integrity errors and
never execute an adapter. Celery task IDs are observability data, not the deduplication mechanism.

Relay calls do not hold database transactions or row locks while waiting for Redis. Failed publication uses
bounded exponential backoff and a sanitized diagnostic. Lease expiry makes coordinator crashes recoverable.
A unique constraint on task-batch ownership prevents concurrent schedulers or reconcilers from creating
multiple active dispatch intents for one batch.

## Consequences

- A successful scheduling response means both work and the intent to dispatch it are durable, even when Redis
  is unavailable.
- The API no longer needs a Celery publisher and does not return an error after durable scheduling merely
  because the broker is temporarily unavailable.
- Dispatch remains eventually consistent and at least once; correctness depends on atomic batch claiming and
  immutable prediction uniqueness, not exactly-once broker delivery.
- Operators run and monitor one additional process. Relay lag, pending intent count, retry count, expired
  leases, and reconciliation repairs become operational health signals.
- API, coordinator, and worker services can share one backend image while scaling and restarting independently.
- Automatic recovery of an already `running` batch requires a future worker lease or heartbeat; elapsed
  `started_at` time alone is insufficient evidence that adapter execution has stopped.
