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

Scheduling must not commit durable work and then publish its Celery message from the API. PostgreSQL and Redis
cannot make those two operations atomic, so a broker failure between them would strand a task batch or
aggregation execution. A snapshot import has the same problem after its source has been staged.

The outbox is a generic application mechanism with three typed targets: `task_batch`,
`aggregation_execution`, and `dataset_snapshot`. Outbox storage has corresponding nullable owner foreign keys
plus an exactly-one-owner check. Each non-null owner is unique. A closed publisher mapping derives the Celery
task name from the typed target and payload. Target, queue, owner, payload, and derived task name must agree; an
ownerless, multiply owned, or mismatched dispatch is invalid.

Method scheduling creates each `TaskBatch` and its `TaskBatchMessage` intent in one PostgreSQL transaction.
Aggregation creation similarly creates one `AggregationExecution` and its identifier-only aggregation intent
in one transaction. Snapshot acceptance first durably stages the bounded source and then creates its Artifact
record, pending DatasetSnapshot, and identifier-only import intent in one database transaction. The outbox also
stores `pending`/`published` state, retry metadata, and a relay lease. A committed asynchronous command
therefore means both the work and dispatch intent are durable; a rolled-back transaction contains neither.

FastAPI never publishes task messages to Redis. Its asynchronous response represents the persisted run or
aggregation, or the pending DatasetSnapshot, not confirmation that a broker accepted every message.

## Dispatch coordinator

One separately started dispatch-coordinator process runs both dispatch services:

- `OutboxRelay` frequently claims available `pending` dispatches under short leases, commits those claims,
  publishes outside the database transaction, and records `published` or schedules a retry with backoff;
- `DispatchReconciler` runs less frequently and repairs durable intent for queued task batches and aggregation
  executions and pending snapshot imports when an intent is missing, a relay lease expired, or a published
  message is stale without a worker claim.

The reconciler creates or rearms typed dispatch records; it does not publish to Redis itself. This leaves one
component responsible for broker interaction and makes reconciliation idempotent under the unique owner
constraints. Reconciliation locks both the dispatch and its target with `FOR UPDATE SKIP LOCKED`, so it does
not rearm a target currently held by a worker transaction.

The coordinator is an ordinary process in this application, started with
`python -m gendertagger.tasks.relay`. It must not run as a Celery task because it is responsible for making
progress while the Celery broker is unavailable. Relay calls do not hold PostgreSQL row locks or transactions
open while waiting for Redis.

## Idempotency

Every task must be safe to retry.

Use persisted batch IDs and uniqueness constraints. A retry should upsert/confirm the same scientific result rather than append duplicates.

Outbox publication is intentionally at least once. The relay can publish successfully and crash before it
records `published`, so an expired lease may cause the same message to be published again. A method worker
claims a batch through one conditional, ownership-aware database operation that verifies both the batch and
method execution IDs and transitions only a dispatchable non-terminal state to `running`. An aggregation
worker applies the same pattern to the exact aggregation execution ID. A snapshot worker conditionally claims
the exact pending DatasetSnapshot and owns its import transaction. One competing delivery wins; duplicates and
terminal resources do not invoke parsing or scientific computation. A failed resource is not silently
reopened by redelivery.

Each claimed TaskBatch writes its exact deterministic person slice and marks the batch completed in one
transaction. Batch sizing bounds the amount of work lost on rollback. No prediction is accepted without its
TaskBatch provenance, while its Run, MethodExecution, or TaskBatch is outside `running`, or for a person outside
that batch's slice. Deferred database checks prevent a caller from committing the outputs without the matching
completed batch state. Conflicting output is never overwritten, and delivery after terminal completion is a
no-op at claim time.

## Retry policy

Differentiate:

- transient infrastructure failures: retry with exponential backoff and jitter
- validation/scientific input errors: persist as `error`/diagnostic, usually no retry
- LLM schema validation failure: bounded retries according to method config
- permanent model/config errors: fail MethodExecution promptly

For snapshot imports, malformed or unsupported source content, an unsafe archive/workbook, an incompatible
persisted profile, or a duplicate collection-wide `xml:id` is a permanent input failure. The complete import
transaction rolls back before a fresh transaction records the failed lifecycle and sanitized diagnostic.
Transient storage, database, and unclassified failures roll back to pending and use bounded task retries;
retry exhaustion records a terminal failure from a clean claim.

## Run completion

A Run may complete with method-level errors. Do not make one failed optional classifier destroy all successfully persisted evidence.

Aggregation can require a configurable minimum set of completed MethodExecutions.
The reference configuration should fail clearly if required published-reference methods are unavailable.

## Snapshot import execution

Snapshot parsing runs on the existing `cpu` queue through the generic outbox. Its task envelope contains only
`dataset_snapshot_id`. The worker loads the primary Artifact, ordered source members, stored import
configuration, importer version, and accepted resource limits through the snapshot resource and opens the
exact sources from shared artifact storage. A task never carries upload bytes, a request-temporary path, an
internal storage locator, a manifest, or parser options.

The closed importer registry requires a known combination of source format, packaging, profile, and importer
version. TEI collection reading produces the same deterministic stream of logical XML members for loose, ZIP,
and TAR.GZ input; CSV, XLSX, and JSON route to their single-file tabular parser. Per-record locators and member
names travel with the validated PersonInput projection.

At the current bounded-source scale, one transaction conditionally claims the pending snapshot, validates the
package, streams secure parsing, inserts PersonRecords in bounded flush groups without intermediate commits,
and marks the snapshot ready with its complete count. Rollback removes the claim and every write, so a crash or
transient failure can retry from the immutable source. Duplicate delivery after completion is a no-op.
Reconciliation uses target-row locking with `SKIP LOCKED`, so it does not rearm a snapshot held by an active
importer. See [ADR-0020](decisions/ADR-0020-asynchronous-snapshot-import-outbox.md) and
[ADR-0021](decisions/ADR-0021-versioned-multi-format-snapshot-ingestion.md).

Chunked committed imports are not introduced by this asynchronous slice. Supporting sources that exceed a
reasonable single-transaction budget requires a separate staging and atomic-publication design.

## Aggregation execution

Aggregation runs on the existing `cpu` queue through the generic outbox. Its small task envelope contains only
`aggregation_execution_id`. The worker loads the exact selected MethodExecutions, snapshot people,
Predictions, strategy, and resolved configuration from PostgreSQL.

For `reference_v1`, every person must have one persisted Prediction from each required reference execution.
An explicit `success`, `abstain`, or `error` prediction satisfies presence; abstentions and errors cast no vote.
A missing row is a permanent completeness failure, not an implicit abstention. The worker never creates a
synthetic Prediction because only a MethodExecution may produce that immutable evidence.

At the current dataset scale, one worker transaction conditionally claims the aggregation, validates complete
evidence, computes every result, inserts the complete person-result set, and marks the aggregation completed.
A rollback exposes no partial results and returns a transient attempt to its queueable state. Permanent
completeness or contract failures produce a terminal failed aggregation with no result rows. Duplicate
deliveries become no-ops after the first transaction completes. Repository and database guards both require
the inserted people to equal the Run snapshot's exact person set and reject output outside the aggregation's
`running` transaction. See
[ADR-0016](decisions/ADR-0016-asynchronous-aggregation-outbox.md).

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
Aggregation work carries `aggregation_execution_id` and its owning `run_id`.
Snapshot-import work carries `dataset_snapshot_id`, its owning `project_id`, source format, packaging, importer
version, and safe counts, but not source content, member names, record values, or internal storage locators.

Coordinator observability should include pending-dispatch count and age, publish attempts and failures,
expired leases, relay lag, and reconciliation repairs. Redis queue depth alone is insufficient because
PostgreSQL is the authoritative dispatch source.
