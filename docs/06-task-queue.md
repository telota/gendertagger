# Task queue and worker design

## Public classification execution

[ADR-0044](decisions/ADR-0044-public-name-classification.md) adds an identifier-only
`PublicClassificationTaskMessage`. The worker calls `PublicClassificationService.execute_job` directly.
The persisted job and outbox intent are accepted together; broker availability is not required for `202`.
The outbox coordinator restores missing intents and rearms queued or expired-running jobs. The chosen queue
is frozen at acceptance: CPU-only selections use `cpu`; mixed selections requiring one dedicated queue
(currently `local_llm` uses `llm`) use that worker, which also executes their CPU adapters. Selections that
require more than one distinct dedicated worker fail acceptance rather than silently changing routing.

Workers verify the accepted method and execution-environment provenance, execute names in bounded chunks,
and renew their token-fenced lease while adapters run. Terminal writes require the current lease ID.
Duplicate messages and stale workers cannot change completed results. Transient database outages retry
through Celery; durable reconciliation also restores abandoned execution. The LLM deployment profile and
server-owned local endpoint must be enabled before making `local_llm` publicly selectable.

## Stack

`gendertagger.tasks.celery_app` builds the Celery application over a Redis broker. The result
backend stays disabled unless `GENDERTAGGER_CELERY_RESULT_BACKEND` is set, because durable
scientific results live in PostgreSQL and artifact storage rather than in Celery. The application
accepts JSON only, acknowledges tasks late, rejects on worker loss, and prefetches one message per
worker process, so a crash redelivers at most one in-flight batch to an idempotent task.

## Queues

`gendertagger.models.queues` defines six routing classes in `CLASSIFICATION_QUEUES`, and the Celery
application declares exactly those as its `task_queues` with `default` as `task_default_queue`:

| Queue | Constant | Purpose | Consumer service |
| --- | --- | --- | --- |
| `default` | `DEFAULT_QUEUE` | lightweight orchestration | `worker-cpu` |
| `cpu` | `CPU_QUEUE` | dictionaries, rules, statistical CPU work, parsing, aggregation, evaluation, export | `worker-cpu` |
| `gpu` | `GPU_QUEUE` | Transformer/ML inference that benefits from a GPU | `worker-gpu` (profile `gpu`) |
| `llm` | `LLM_QUEUE` | locally hosted LLM requests needing isolation or concurrency control | `worker-llm` (profile `llm`) |
| `external` | `EXTERNAL_QUEUE` | rate-limited external services | `worker-external` (profile `external`) |
| `export` | `EXPORT_QUEUE` | larger export and report jobs | `worker-cpu` |

`worker-cpu` runs `celery -A gendertagger.tasks.celery_app worker -Q default,cpu,export`, so the
`export` class is consumed by the same process that serves `default` and `cpu`. The reference
method registry (`services/method_registry.py`) routes nine adapters to `cpu` and `local_llm` to
`llm`; snapshot-import, aggregation, evaluation, and export dispatches are pinned to `cpu` and the
dispatch repository rejects any other queue for them.

Methods are routed to one of these classes, never to a per-method queue. Do not create a queue per
method unless operational evidence justifies it.

## Registered tasks and dispatch targets

Five Celery tasks are registered, one per `DispatchTarget` value in `gendertagger.models.dispatch`:

| `DispatchTarget` | Celery task name | Module | Envelope fields |
| --- | --- | --- | --- |
| `task_batch` | `gendertagger.tasks.execute_batch` | `tasks/execution.py` | `method_execution_id`, `task_batch_id` |
| `aggregation_execution` | `gendertagger.tasks.execute_aggregation` | `tasks/aggregation.py` | `aggregation_execution_id` |
| `dataset_snapshot` | `gendertagger.tasks.execute_snapshot_import` | `tasks/snapshot_import.py` | `dataset_snapshot_id` |
| `evaluation_execution` | `gendertagger.tasks.execute_evaluation` | `tasks/evaluation.py` | `evaluation_execution_id` |
| `export` | `gendertagger.tasks.execute_export` | `tasks/export.py` | `export_execution_id` |

`CeleryMessagePublisher` (`tasks/dispatch.py`) is the closed mapping from a validated envelope to
its task name, queue, and broker task ID. The broker task ID is always the target's own identifier,
and a payload whose identifier disagrees with the dispatch is rejected before publication.
`DispatchStatus` has exactly two values, `pending` and `published`.

## Batch model

A MethodExecution is divided into persisted TaskBatches. `MethodRegistration.batch_size` is
per-adapter registration data rather than a global constant, and each `TaskBatch` persists the
deterministic slice it covers as `record_offset` and `record_count`. Every adapter in the reference
registry registers the same `_CPU_BATCH_SIZE` of 200 records per batch. Resource-class-specific
tuning is discussed in [`22-future-development.md`](22-future-development.md).

## Incremental progress

A terminal batch refreshes execution tallies in its existing worker transaction, independently of
whether other batches remain pending/running. Execution finalizers serialize on the existing parent
row with `FOR NO KEY UPDATE` and refresh cached ORM state after locking; Prediction foreign-key
`KEY SHARE` checks do not force competing workers into lock-upgrade deadlocks.

Completed work is batch `success_count + abstain_count`; failed work is `error_count`, including the
entire assigned slice of a technically failed batch even when no Predictions were written. A successful
substantive `unknown`, abstention, and technical failure remain distinct method outcomes. Run progress
sums the current execution counters in record-method work units. GET and SSE read that same persisted
state. Duplicate batch delivery cannot add counts or outputs, and outstanding batches prevent terminal
lifecycle transitions without suppressing intermediate progress.

## Transactional dispatch handoff

Scheduling must not commit durable work and then publish its Celery message from the API. PostgreSQL and Redis
cannot make those two operations atomic, so a broker failure between them would strand a task batch or
aggregation execution. A snapshot import has the same problem after its source has been staged.

The outbox is a generic application mechanism with the five typed targets listed above. Outbox storage has
corresponding nullable owner foreign keys plus an exactly-one-owner check. Each non-null owner is unique. A
closed publisher mapping derives the Celery task name from the typed target and payload. Target, queue, owner,
payload, and derived task name must agree; an ownerless, multiply owned, or mismatched dispatch is invalid.

Method scheduling creates each `TaskBatch` and its `TaskBatchMessage` intent in one PostgreSQL transaction.
Aggregation, evaluation, and export creation similarly each create one execution resource and its
identifier-only dispatch intent in one transaction. Snapshot acceptance first durably stages the bounded
source and then creates its Artifact record, pending DatasetSnapshot, and identifier-only import intent in
one database transaction. The outbox also stores `pending`/`published` state, retry metadata, and a relay
lease. A committed asynchronous command therefore means both the work and dispatch intent are durable; a
rolled-back transaction contains neither.

FastAPI never publishes task messages to Redis. Its asynchronous response represents the persisted run or
aggregation, or the pending DatasetSnapshot, not confirmation that a broker accepted every message.

## Dispatch coordinator

One separately started dispatch-coordinator process runs both dispatch services:

- `OutboxRelay` frequently claims available `pending` dispatches under short leases, commits those claims,
  publishes outside the database transaction, and records `published` or schedules a retry with backoff;
- `DispatchReconciler` runs less frequently and repairs durable intent across all five targets — queued task
  batches, aggregation executions, pending snapshot imports, evaluation executions, and export executions —
  when an intent is missing, a relay lease expired, or a published message is stale without a worker claim.

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

## Project worker compatibility

[ADR-0048](decisions/ADR-0048-project-worker-provenance-compatibility.md) extends the public-job provenance
check to project TaskBatches. Workers require configured source revision and dependency-lock digest, capture
their actual application/Python/installed-dependency/image identity, and record canonical hostname/process
provenance in the atomic claim. MethodExecution's immutable metadata and identifier-only task envelopes
remain unchanged.

Before any adapter call, implementation/normalization versions and every accepted Run environment field
must match; the resolved configuration and applicable pinned lookup/model bytes must also retain their
accepted identities. A mismatch or missing historical dependency evidence fails permanently with a
diagnosable `IncompatibleWorkerError` and zero Predictions. Redelivery of that failed batch is a no-op.
Finish unclaimed work with its matching environment or accept a new Run; never replace accepted provenance
or silently reopen terminal work. Transient infrastructure failures retain the existing rollback/retry
policy, including rollback of the worker receipt. Actual worker identity stays internal rather than entering
public method summaries.


## Worker resource ownership

`tasks/worker_resources.py` owns one lazy, lock-protected infrastructure context per process. All six
task families share its database pool while every operation and heartbeat enters a fresh UoW/session.
Ordinary imports and artifact execution load runtime settings without classification build identity;
classification registries, resolvers, actual-worker provenance, and the bounded public prediction cache
are initialized only when needed.

Fork hooks detach inherited pools without closing the parent's connections. Process initialization,
shutdown, and explicit reset reject stale resource use and permit lazy reinitialization; callers stop
their operation/heartbeat threads before explicit reset. Task names, envelopes, executor composition,
and resource-specific failure types remain explicit outside FastAPI.

## Retry policy

Differentiate:

- transient infrastructure failures: retry with exponential backoff and jitter
- validation/scientific input errors: persist as `error`/diagnostic, usually no retry
- LLM schema validation failure: bounded retries according to method config
- permanent model/config errors: fail MethodExecution promptly

The six worker wrappers use `services/dispatch.py::jittered_exponential_retry_delay` with a two-second
base and sixty-second cap. Celery's zero-based retry count becomes a one-based delivery attempt; ordinary
three-attempt budgets and the public job's five-retry budget remain unchanged.

For snapshot imports, malformed or unsupported source content, an unsafe archive/workbook, an incompatible
persisted profile, or a duplicate collection-wide `xml:id` is a permanent input failure. The complete import
transaction rolls back before a fresh transaction records the failed lifecycle and sanitized diagnostic.
Transient storage, database, and unclassified failures roll back to pending and use bounded task retries;
retry exhaustion records a terminal failure from a clean claim.

## Persisted failure diagnostics

Batch, aggregation, evaluation, export, and dispatch failures share
`services/diagnostics.py::sanitized_diagnostic`. Detailed diagnostics redact URL user information
before truncating to at most 500 characters, including the trailing ellipsis when truncated.
This policy protects credential-bearing URLs; it does not promise general secret or editorial-content
sanitization. Detailed operational diagnostics remain available only through authorized resources.

Snapshot imports retain their fixed public-safe messages, and anonymous classification retains its
limited failure codes and private-evidence boundary. Neither surface exposes detailed exceptions through
this formatter. Failure classes, retry decisions, and immutable method evidence are unchanged.

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
