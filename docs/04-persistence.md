# Persistence design

## Database

PostgreSQL is the durable source of truth for application state, scientific results, annotation history, and provenance metadata.
Redis is not durable scientific storage.

Use SQLAlchemy 2.x and Alembic from the first schema revision.

## Transaction and repository boundaries

Application services own a unit of work. One unit of work owns one SQLAlchemy session and therefore one
database transaction. Repositories share that session, flush when generated identifiers or constraint results
are needed, and never commit independently. Leaving a unit-of-work context rolls back any uncommitted work and
closes the session; successful commands call `commit()` explicitly.

Repository interfaces belong to the application boundary. Their inputs and outputs are canonical Pydantic
contracts or explicit scalar identifiers, never SQLAlchemy rows. The implementations under `gendertagger.db`
perform the row/contract mapping and may use SQLAlchemy internally. Services receive a unit-of-work factory so
tests and non-HTTP entry points use the same transaction semantics.

## Suggested tables

- `projects`
- `dataset_snapshots`
- `person_records`
- `person_external_ids`
- `runs`
- `method_executions`
- `predictions`
- `aggregation_executions`
- `aggregated_results`
- `annotations`
- `review_states`
- `users`
- `evaluations`
- `artifacts`
- `task_batches`
- `batch_dispatches` (generic transactional outbox with typed task-batch and aggregation owners)
- optional `method_cache_entries`

## Key constraints

### Projects and snapshots

- `projects.slug` unique.
- `dataset_snapshots` immutable when status becomes `ready`.
- unique `(dataset_snapshot_id, tei_id)` for person records.
- retain `(project_id, tei_id)` as the cross-snapshot canonical identity lookup.

### Predictions

Recommended uniqueness:

```text
(method_execution_id, person_record_id)
```

if exactly one result per person/execution is expected.

Prediction records should include:

- normalized label
- status
- method_confidence
- raw_label
- raw_output JSONB
- metadata JSONB
- input fingerprint
- created_at

### Aggregation

Aggregation executions reference the exact MethodExecutions included. Do not infer "all methods in run" later
if a subset was selected.

`aggregated_results` is unique on `(aggregation_execution_id, person_record_id)`. At the current dataset scale,
the executor inserts the full person-result set and marks the AggregationExecution completed in one
transaction. Completion requires result cardinality equal to the immutable snapshot's person cardinality.
Failed or retried attempts expose no partial rows.

### Transactional dispatch outbox

One outbox row belongs to exactly one durable work target. Storage has nullable `task_batch_id` and
`aggregation_execution_id` foreign keys with:

- an exactly-one-owner check;
- a unique constraint for each non-null owner;
- a dispatch kind consistent with the selected owner and validated payload;
- explicit `pending`/`published` state, availability time, attempt count, relay lease, publication time, and
  sanitized last-error diagnostic.

The outbox row is created in the same transaction as its target. Relay and reconciliation update delivery
metadata without owning scientific results. Reconciliation locks both dispatch and target rows with
`FOR UPDATE SKIP LOCKED`; it does not infer that an old timestamp alone proves a worker has stopped. See
[ADR-0015](decisions/ADR-0015-transactional-batch-dispatch-outbox.md) and
[ADR-0016](decisions/ADR-0016-asynchronous-aggregation-outbox.md).

### Annotations

Annotations are append-only. Store:

- person canonical/project reference and snapshot context
- label/decision
- reviewer
- comment/reason where supplied
- referenced aggregation/result
- supersedes_annotation_id where applicable
- resulting review revision
- timestamps

### Review state and optimistic concurrency

Use a small mutable `review_states` projection keyed by the snapshot/person record, for example:

```text
(dataset_snapshot_id, person_record_id) UNIQUE
revision NOT NULL
current_annotation_id NULLABLE
workflow_state NOT NULL
updated_at NOT NULL
```

Creating an annotation is one database transaction:

1. lock/load the ReviewState row;
2. compare the command's `expected_revision`;
3. fail with an application-level conflict if it is stale;
4. insert the immutable Annotation;
5. increment ReviewState.revision and update its current head/workflow state;
6. commit.

ReviewState is a query/concurrency projection and must be rebuildable from annotation history. It does not make historical Annotation rows mutable.

### Query indexes for browser review

Add indexes based on actual query plans, but expect the review API to need indexed/filterable fields for:

- snapshot/person identity;
- canonical/final label;
- certainty/agreement tiers;
- review workflow state;
- current reviewer/head where useful;
- method execution/result/status;
- name/identifier search.

Do not move these frequently queried fields into JSONB merely to avoid schema design.

## JSONB policy

Use JSONB for method-specific raw outputs, flexible provenance fragments, and configuration snapshots. Do not hide core queryable fields such as labels, states, IDs, timestamps, and agreement values inside JSONB.

## Artifact storage

Store bytes outside PostgreSQL initially. Each `Artifact` record contains:

- logical type
- storage URI/path
- SHA-256 checksum
- byte size
- media type
- source/producer IDs
- metadata

A filesystem backend is the v1 implementation. Define an interface that can later support S3-compatible storage without changing domain contracts.

## Caching

Caches are optimizations, not truth.
A scientific method cache key must include at least:

```text
method identifier
method implementation/version
model/data revision
resolved method configuration
normalized scientific input fingerprint
```

Cache hits must still create Run-local Prediction provenance pointing to the cached computation.
