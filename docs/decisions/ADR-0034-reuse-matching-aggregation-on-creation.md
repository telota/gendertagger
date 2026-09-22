# ADR-0034: Reuse a matching aggregation on repeated creation

**Status:** Accepted

## Context

Decision D4 in [`24-frontend-delivery-plan.md`](../24-frontend-delivery-plan.md) has the browser client create
the default `reference_v1` aggregation as soon as a run completes, and requires that step to be idempotent.
Until now `POST /api/v1/runs/{run_id}/aggregations` persisted a new `AggregationExecution` on every call
([ADR-0016](ADR-0016-asynchronous-aggregation-outbox.md)). A page reload, a second open tab, or a retry after a
lost response therefore queued a full recomputation and left the run with several indistinguishable
aggregations. Each carries its own review queue and export scope, so a reviewer could no longer tell which of
them their decisions and exports belonged to.

The client cannot prevent this on its own. Listing a run's aggregations before creating one is a
check-then-act race between tabs, and a lost `202` response leaves the client with no identifier to recover.

The duplicate is also scientifically empty. An aggregation's output is a function of its run's immutable
DatasetSnapshot ([ADR-0002](ADR-0002-immutable-dataset-snapshots.md)), the immutable Predictions of the
selected MethodExecutions, the versioned strategy, and its resolved configuration
([ADR-0003](ADR-0003-reference-aggregation.md)). A second execution over the same inputs can only reproduce
the first.

## Decision

An aggregation's creation identity is the tuple of its `run_id`, its `strategy`, its `config_sha256` (the
canonical hash of the strategy together with its resolved configuration), and its exact ordered
`method_execution_ids`. Selection order is part of the identity: it is persisted provenance and fixes the
order in which `GET /aggregations/{aggregation_id}/results/{result_id}/predictions` lists the methods. A
client that wants its requests to match submits the selection in a stable order, such as the order
`GET /runs/{run_id}/executions` returns.

`POST /api/v1/runs/{run_id}/aggregations` first looks for an existing aggregation with the same identity
whose status is `pending`, `queued`, `running`, or `completed`. When one exists, the command returns it
unchanged with `200 OK`, and it creates no new aggregation and no new dispatch intent. Otherwise the command
validates the selection and creates a new queued aggregation with `202 Accepted`, exactly as before.

A `failed` or `cancelled` aggregation never matches, so re-issuing the same request after a failure creates
a fresh attempt. The failed record stays in place as history. Where several matching aggregations exist,
which is only possible for rows created before this decision, the command returns the oldest by
`(created_at, id)`.

Concurrent identical requests are serialized on the run. The creating transaction locks the run row with
`FOR NO KEY UPDATE` before it looks for a match, and PostgreSQL's default `READ COMMITTED` isolation gives
each later statement a fresh snapshot. A second request that waited for the lock therefore sees the first
request's committed aggregation and returns it. `FOR NO KEY UPDATE` still admits the `FOR KEY SHARE` locks
that foreign-key checks take, so workers inserting rows that reference the run are not blocked.

Evaluations and exports keep their create-new semantics; this decision covers aggregation only.

## Consequences

- The client can issue the default aggregation request whenever it observes a completed run, without
  tracking whether it or another tab already did. The status code tells it whether the aggregation already
  existed.
- An identical selection can no longer be recomputed while a matching aggregation is live or completed.
  This removes nothing a user could observe, but it makes explicit a rule that already governed aggregation:
  any change to aggregation behavior requires a new strategy version. `AggregationExecution` records no code
  provenance of its own, so an unversioned behavior change would now be hidden behind a reused result rather
  than exposed by a new one.
- A matching aggregation that never finishes blocks identical new requests. The existing reconciler and
  retry exhaustion in ADR-0016 already move such an aggregation to `failed`, which releases the identity; a
  different selection is unaffected in the meantime.
- Creating an aggregation now briefly holds a stronger lock on the run row. Aggregation creation is rare
  and its transaction is short, and the lock does not conflict with foreign-key checks.
- No schema change is needed. A partial unique index over a selection fingerprint was rejected because it
  requires a new column and a migration that would fail on any deployment that already holds duplicates.
- An `Idempotency-Key` header was rejected for this case. It needs a key table, actor scoping, and expiry
  rules, and it still admits deliberate duplicates. It remains the candidate for commands without a natural
  identity, such as snapshot import in [`22-future-development.md`](../22-future-development.md).
- Creating the default aggregation on the server when a run completes was rejected. It would reverse D4 and
  tie run completion to aggregation, and a selection that cannot be aggregated would then need a failure
  surface of its own.
