# ADR-0016: Execute aggregation asynchronously through the transactional outbox

**Status:** Accepted

## Context

An `AggregationExecution` is already a persisted, independently rerunnable resource, but the first API slice
only creates it in `pending` state. Nothing executes the aggregation or changes it to a terminal state. Running
the pure aggregation inside the HTTP request would contradict the asynchronous resource contract in
`docs/05-api.md`, couple request latency to corpus size, and make client retries ambiguous.

[ADR-0015](ADR-0015-transactional-batch-dispatch-outbox.md) closes the PostgreSQL-to-Redis failure window for
method batches. Publishing aggregation jobs directly from FastAPI, or adding an unrelated dispatcher, would
recreate that window and a second recovery mechanism. Aggregation also has a stricter scientific completeness
condition than ordinary voting: [ADR-0008](ADR-0008-reference-aggregation-edge-contract.md) requires a
persisted result envelope from every required reference method for every person. A persisted `abstain` or
`error` is evidence that the method ran; an absent `Prediction` is not.

## Decision

Aggregation uses the same generic transactional dispatch outbox, relay, reconciler, Redis broker, and CPU
workers as method execution. The existing outbox storage is generalized to support exactly one typed owner per
row: either `task_batch_id` or `aggregation_execution_id`. Both are nullable foreign keys, an exactly-one-owner
check prevents ownerless or ambiguous rows, and each non-null owner is unique. A typed target discriminator and
closed publisher mapping require the owner, small validated payload, queue, and Celery task name to agree. The
aggregation envelope contains only `aggregation_execution_id`; workers load all authoritative configuration
and evidence from PostgreSQL.

`POST /api/v1/runs/{run_id}/aggregations` validates the selected completed MethodExecutions, creates the
`AggregationExecution`, transitions it to `queued`, and creates its outbox intent in one database transaction.
The endpoint returns that persisted resource with `202 Accepted`; it neither computes results nor publishes to
Redis. A database rollback leaves neither the aggregation nor dispatch intent. Broker unavailability after
commit leaves durable queued work for the existing coordinator to publish later.

The relay publishes aggregation intent at least once. An aggregation worker claims the exact
`aggregation_execution_id` with one conditional state transition from `queued` to `running`. Competing or
duplicate deliveries cannot both claim it; a delivery for a completed, failed, cancelled, or wrongly owned
resource is a no-op or an explicit integrity failure. Celery task IDs remain observability metadata, not the
deduplication mechanism.

For the current dataset scale, one worker transaction owns the claim, completeness read, pure computation,
complete result insert, and transition to `completed`. The worker computes and validates the full result set
before persistence. A uniqueness constraint permits at most one `AggregatedResult` per
`(aggregation_execution_id, person_record_id)`, and completion requires exactly one result for every person in
the run's immutable DatasetSnapshot. Other transactions therefore observe either no results for an
uncompleted attempt or the complete result set with terminal status, never a partial completed aggregation.
The target row remains locked during this transaction; reconciliation locks both dispatch and target rows with
`SKIP LOCKED` so it does not rearm work held by an active worker.

Before computing `reference_v1`, the executor verifies all of the following:

- the exact selected MethodExecutions still belong to the aggregation's run and snapshot;
- every required reference method is represented once by the selected executions;
- every person in the snapshot has one persisted `Prediction` from every required execution;
- every loaded prediction belongs to the expected person and execution.

Explicit `success`, `abstain`, and `error` predictions all satisfy presence. `abstain` and `error` cast no vote
but remain valid scientific inputs and can lead to a completed `no_data` result. A missing required prediction
is a permanent completeness failure. The executor never fabricates an `abstain` or `error` `Prediction` to
fill the gap: `Prediction` rows remain immutable outputs of their MethodExecutions, while the failed
`AggregationExecution` records the missing-evidence diagnostic.

A permanent completeness, contract, or strategy failure transitions the aggregation to `failed`, records a
sanitized failure class and diagnostic, sets `finished_at`, and exposes no result rows. A transient
infrastructure failure rolls back the claim and all result writes so Celery can retry with bounded backoff.
Retry exhaustion records the same terminal failed resource in a clean transaction. A valid corpus containing
record-level abstentions or errors is not an aggregation failure. `AggregationExecution` has no
`completed_with_errors` state: it either produces a complete valid result set or fails.

The first implementation intentionally favors atomicity over chunked writes. If corpus size later makes one
transaction unacceptable, chunked aggregation requires a new decision defining attempt ownership, staging,
completeness validation, and atomic publication of the finished result set; it must not make partial results
look complete.

## Consequences

- Aggregation remains independently rerunnable and becomes a genuine asynchronous application resource.
- API, dispatch coordinator, Redis, and existing CPU-worker topology are unchanged; no aggregation-specific
  service or public queue detail is introduced.
- Broker and coordinator outages cannot lose an accepted aggregation command, and duplicate publication is
  safe through atomic target claiming.
- Reference completeness is enforced against persisted evidence without rewriting scientific history.
- Successful aggregation publication is eventually consistent, while scientific result visibility is atomic
  at the current corpus scale.
- A worker transaction may be longer than an ordinary repository command. Operations must monitor aggregation
  duration and database pressure; future chunking requires an explicit safe staging design.
