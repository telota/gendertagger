# Task queue and worker design

## Stack

Celery with Redis as broker/result coordination. Durable scientific results are written to PostgreSQL/artifact storage, not Celery result backend.

## Queues

Initial routing classes:

- `default`: lightweight orchestration
- `cpu`: dictionaries, rules, statistical CPU work, parsing, aggregation/evaluation
- `gpu`: Transformer/ML inference that benefits from GPU
- `llm`: locally hosted LLM requests if isolation/concurrency control is useful
- `external`: future rate-limited external services
- `export`: larger export/report jobs if needed

Do not create a queue per method unless operational evidence justifies it.

## Batch model

A MethodExecution is divided into persisted TaskBatches.
Batch sizes are method/resource-specific configuration rather than global constants.

Initial tuning ranges, not normative values:

- CPU lookup/rule work: ~100–500 records per batch
- GPU inference: ~32–256 records per batch depending on model/memory

## Transactional dispatch handoff

Scheduling must not commit a task batch and then publish its Celery message from the API. PostgreSQL and
Redis cannot make those two operations atomic, so a broker failure between them would strand durable work.

The scheduler instead creates each `TaskBatch` and a corresponding `BatchDispatch` outbox record in the same
PostgreSQL transaction. The `batch_dispatches` table owns the small validated `TaskBatchMessage`, queue name,
`pending`/`published` status, retry metadata, and relay lease. `task_batch_id` is unique. A committed scheduling
transaction therefore means both the work and its dispatch intent are durable; a rolled-back transaction
contains neither.

FastAPI never publishes batch messages to Redis. Its asynchronous response represents the persisted run,
not confirmation that a broker accepted every message.

## Dispatch coordinator

One separately started dispatch-coordinator process runs both dispatch services:

- `OutboxRelay` frequently claims available `pending` dispatches under short leases, commits those claims,
  publishes outside the database transaction, and records `published` or schedules a retry with backoff;
- `DispatchReconciler` runs less frequently and repairs durable intent for active pending batches when an
  intent is missing, a relay lease expired, or a published message is stale without a worker claim.

The reconciler creates or rearms `BatchDispatch` records; it does not publish to Redis itself. This leaves one
component responsible for broker interaction and makes reconciliation idempotent under the unique
`task_batch_id` constraint.

The coordinator is an ordinary process in this application, started with
`python -m gendertagger.tasks.relay`. It must not run as a Celery task because it is responsible for making
progress while the Celery broker is unavailable. Relay calls do not hold PostgreSQL row locks or transactions
open while waiting for Redis.

## Idempotency

Every task must be safe to retry.

Use persisted batch IDs and uniqueness constraints. A retry should upsert/confirm the same scientific result rather than append duplicates.

Outbox publication is intentionally at least once. The relay can publish successfully and crash before it
records `published`, so an expired lease may cause the same message to be published again. A worker claims a
batch through one conditional, ownership-aware database operation that verifies both the batch and method
execution IDs and transitions only a dispatchable non-terminal state to `running`. One competing delivery
wins; duplicates and terminal batches do not invoke the method adapter. A failed batch is not silently
reopened by redelivery.

Method predictions should be committed in bounded batches so a worker failure does not discard thousands of completed classifications.

## Retry policy

Differentiate:

- transient infrastructure failures: retry with exponential backoff and jitter
- validation/scientific input errors: persist as `error`/diagnostic, usually no retry
- LLM schema validation failure: bounded retries according to method config
- permanent model/config errors: fail MethodExecution promptly

## Run completion

A Run may complete with method-level errors. Do not make one failed optional classifier destroy all successfully persisted evidence.

Aggregation can require a configurable minimum set of completed MethodExecutions.
The reference configuration should fail clearly if required published-reference methods are unavailable.

## Cancellation

Cancellation should mark future batches cancelled and revoke queued work where practical. Already persisted Predictions remain as provenance and are not deleted silently.

## Worker observability

Record:

- worker/task IDs
- batch IDs
- queue
- attempts
- start/end times
- counts success/abstain/error
- exception class and sanitized diagnostic

Structured logs should carry `run_id`, `method_execution_id`, and `batch_id` when applicable.

Coordinator observability should include pending-dispatch count and age, publish attempts and failures,
expired leases, relay lag, and reconciliation repairs. Redis queue depth alone is insufficient because
PostgreSQL is the authoritative dispatch source.
