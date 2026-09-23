# Persistence design

## Database

PostgreSQL is the durable source of truth for application state, scientific results, annotation history, and
provenance metadata. Redis is a broker and operational coordination service, never durable scientific
storage.

SQLAlchemy 2.x mappings live under [`src/gendertagger/db/`](../backend/src/gendertagger/db/), and Alembic migrations
under [`migrations/`](../backend/migrations/) define the exact tables, columns, constraints, indexes, and triggers.
The application refuses a non-PostgreSQL database because its integrity model depends on PostgreSQL behavior.

This document records persistence boundaries and invariants rather than duplicating the current schema.

## Migration policy

No database outside development runs these migrations yet, so the schema is a single baseline revision,
`20260815_0001`, and pre-release schema changes edit that baseline instead of stacking revisions. Every such
edit is verified by comparing `pg_dump --schema-only` output, and a local development database is re-created
or moved onto the baseline with `alembic stamp --purge 20260815_0001` when its schema is unchanged. Once any
deployment exists, the baseline is frozen and every change becomes an ordinary forward migration.

## Transactions and repositories

Application services own units of work. One unit of work owns one SQLAlchemy session and transaction.
Repositories share that session, may flush for generated identifiers or constraint feedback, and never commit
independently. Exiting without an explicit commit rolls back and closes the session.

Repository interfaces accept and return Pydantic contracts or explicit scalar identifiers, never ORM rows.
Implementations perform mapping internally. Services receive unit-of-work factories so HTTP, CLI, workers,
and tests share the same transaction semantics.

## Ownership and identity

Every persisted resource has one unambiguous owner chain back to a project. Dataset snapshots belong to
projects; people belong to snapshots; runs belong to snapshots; executions and Predictions belong to runs;
aggregations, evaluations, and exports identify their exact run inputs.

A person is unique by TEI `xml:id` within one snapshot. Cross-snapshot logical identity remains
`(project_id, tei_id)` through the snapshot relationship; no global person table or identity layer exists.
Composite foreign keys prevent annotations or review state from pairing a person with the wrong snapshot.

The project working-aggregation pointer may reference only a completed aggregation produced by one of that
project's snapshots. The repository enforces the cross-resource ownership and lifecycle rule described in
[ADR-0035](decisions/ADR-0035-project-working-aggregation.md).

## Immutable snapshots and import atomicity

A ready DatasetSnapshot and its source/member/person projection are immutable. A failed DatasetSnapshot is
sealed as well, so its status and failure details cannot be rewritten; a new import creates a new snapshot.
Structured name forms, events,
flat search fields, authority identifiers, source-member names, and record locators are sealed together.
Repositories validate that the parser version and projected fields agree with the persisted import profile.
Every imported record must carry the structured name projection required by its supported profile.

Snapshot acceptance stages bounded bytes first, then atomically registers artifacts, ordered source members,
the pending snapshot, and its dispatch intent. A database rollback accepts none of those records, although
content-addressed storage may retain an unreferenced blob for later garbage collection.

Import claim, validation, streamed PersonRecord insertion, and the ready transition share one transaction at
the supported dataset scale. A transient failure or worker loss rolls back the claim and every projection
row. A permanent parsing failure rolls back before a separate transaction records the sanitized terminal
failure. Readers therefore observe `pending` followed by one atomic transition to `ready` or `failed`, never a
committed prefix. See
[ADR-0020](decisions/ADR-0020-asynchronous-snapshot-import-outbox.md) and
[ADR-0021](decisions/ADR-0021-versioned-multi-format-snapshot-ingestion.md).

## Predictions and task batches

One MethodExecution can persist at most one Prediction per person. Prediction label and status must agree;
confidence is finite; raw output, metadata, input fingerprint, and owning TaskBatch remain attached as
immutable provenance.

Prediction insertion validates the running execution and batch, the owning run, and the exact deterministic
person slice assigned to that batch. Completing a batch and committing its complete Prediction set happen in
one transaction. Database guards reject late, partial, cross-run, cross-batch, or update/delete mutations even
when a caller bypasses the repository.

## Aggregation results

An AggregationExecution stores the exact ordered MethodExecutions it selected; persistence never infers the
selection later from the run. Membership is nonempty and ordered before scheduling, then sealed.

One aggregation has at most one result per snapshot person. The executor commits the complete result set and
completed lifecycle together, with cardinality and ownership equal to the immutable snapshot population.
Failed or retried attempts expose no partial results. Existing AggregatedResults are immutable.

Matching aggregation creation serializes on the run so concurrent identical requests reuse one active or
completed resource. See [ADR-0034](decisions/ADR-0034-reuse-matching-aggregation-on-creation.md).

## Lifecycle and provenance sealing

PostgreSQL enforces legal lifecycle transitions in addition to repository validation. Terminal resources
cannot reopen or accept late output. Parent resources cannot complete before their owned executions or batches
reach compatible terminal states. Status-specific timestamps and failure diagnostics remain consistent.

Creation-time scientific provenance is immutable. While work is active, only operational lifecycle fields,
progress, attempt/worker metadata, tallies, timestamps, and sanitized failure details may change. Once a
resource is terminal, the entire row is sealed. Lifecycle resources are not deleted to rewrite history.

These database guards cover runs, method executions, task batches, and aggregation, evaluation, and export
executions alike. For evaluations and exports, the only fields that may change after creation are the
lifecycle columns plus the report or manifest artifact that marks completion. Aggregation and evaluation
method-execution membership is insert-only, may be added only while the execution is pending, and may
reference only completed executions of the same run.

Failed runs, dataset snapshots, method executions, task batches, and aggregation, evaluation, and export
executions record `failure_class` next to the sanitized `failure_diagnostic`, and only failed rows may carry
either. `failure_class` is the class name of the exception that ended the work, for example `TeiImportError`.
A run that fails because a method execution failed, under `fail_run_on_optional_method_error`, involves no
exception of its own and records `MethodExecutionFailure`; the underlying exception classes remain on the
failed method executions and task batches.

## Transactional dispatch outbox

Each outbox row belongs to exactly one durable work target: task batch, aggregation execution, dataset
snapshot, evaluation execution, or export. Database and Pydantic constraints require one owner, one outbox row
per target, and agreement among owner type, identifier-only payload, task name, and queue.

The target and dispatch intent are created in the same transaction. Relay and reconciliation update delivery
metadata without owning scientific state. Claims use row locking that permits concurrent workers while
preventing duplicate ownership; age alone never proves a worker stopped. See
[ADR-0015](decisions/ADR-0015-transactional-batch-dispatch-outbox.md),
[ADR-0016](decisions/ADR-0016-asynchronous-aggregation-outbox.md), and
[ADR-0020](decisions/ADR-0020-asynchronous-snapshot-import-outbox.md).

## Annotation history and review state

Annotation rows are append-only. Verify and correct actions carry a canonical label; defer carries none. Each
new decision identifies its reviewer, optional aggregation context, predecessor, resulting revision, and
timestamp. Database triggers reject updates and deletes.

ReviewState is the small mutable head projection for one snapshot/person stream. Revision zero means no head
and an unreviewed workflow state. Higher revisions identify the current annotation and a reviewed or deferred
state. The projection is rebuildable from Annotation history and does not replace it.

Creating an annotation locks the person and review-state row, compares `expected_revision`, inserts the next
immutable annotation, advances the projection, and commits once. A stale revision becomes an application-level
conflict rather than an overwrite.

## Query indexes

Indexes support ownership traversal, lifecycle polling, stable cursor orders, review filters, uncertainty
ordering, labels and prediction status, annotation heads, and name/authority search. Core query fields remain
ordinary typed columns rather than JSONB. New indexes follow measured query plans rather than speculative UI
requirements.

Exact index definitions belong to the SQLAlchemy metadata and Alembic migrations.

## JSONB policy

Use JSONB for method-specific raw output, flexible provenance fragments, validated bounded source structures,
and configuration snapshots. Do not hide core queryable fields such as labels, states, IDs, timestamps,
agreement values, or flat name-search projections inside JSONB.

## Artifact storage

Artifact bytes live outside PostgreSQL behind the ArtifactStorage boundary. Immutable database records bind a
logical type and producer provenance to storage location, SHA-256 checksum, byte size, media type, and bounded
metadata. Domain and API contracts never receive filesystem paths.

Large lookup datasets and directory-shaped models remain content-addressed artifacts rather than application
tables. Workers resolve an approved digest, verify it, and materialize it read-only. Original sources and
compiled derivatives remain independently attributable. See
[ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md),
[ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md), and
[ADR-0025](decisions/ADR-0025-hivoto-xgboost-adapter.md).

## Caching

Caches are optimizations, not truth. Run execution persists every Prediction with Run-local provenance.

The synchronous classification service may use a bounded in-process cache keyed by method, resolved
configuration, and input name. It is process-local, non-durable, and never substitutes for Prediction rows. A
durable cross-run cache remains deferred in [`22-future-development.md`](22-future-development.md).
