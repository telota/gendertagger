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

The original pre-release schema was consolidated into baseline revision `20260815_0001`; historical
pre-deployment amendments to that baseline are recorded in their ADRs. Existing forward migrations and the
baseline are preserved. Account preferences under
[ADR-0043](decisions/ADR-0043-account-level-user-preferences.md) use an ordinary forward migration after the
current head, without a default-row backfill or a rewrite of migration history. Verify a clean upgrade,
an upgrade from the preceding head, and model-versus-migration agreement on PostgreSQL. Once any deployment
exists, all schema changes must use forward migrations.

## Transactions and repositories

Application services own units of work. One unit of work owns one SQLAlchemy session and transaction.
Repositories share that session, may flush for generated identifiers or constraint feedback, and never commit
independently. Exiting without an explicit commit rolls back and closes the session.

Repository interfaces accept and return Pydantic contracts or explicit scalar identifiers, never ORM rows.
Implementations perform mapping internally. Services receive unit-of-work factories so HTTP, CLI, workers,
and tests share the same transaction semantics.

## Ownership and identity

Every persisted scientific resource has one unambiguous owner chain back to a project. Dataset snapshots belong to
projects; people belong to snapshots; runs belong to snapshots; executions and Predictions belong to runs;
aggregations, evaluations, and exports identify their exact run inputs.

A person is unique by TEI `xml:id` within one snapshot. Cross-snapshot logical identity remains
`(project_id, tei_id)` through the snapshot relationship; no global person table or identity layer exists.
Composite foreign keys prevent annotations or review state from pairing a person with the wrong snapshot.

The project working-aggregation pointer may reference only a completed aggregation produced by one of that
project's snapshots. The repository enforces the cross-resource ownership and lifecycle rule described in
[ADR-0035](decisions/ADR-0035-project-working-aggregation.md).

## Teams and delegated membership — slice 1 delivered

[ADR-0041](decisions/ADR-0041-admin-managed-teams-and-delegated-project-membership.md) slice 1 adds
`teams` and direct `team_memberships`, keyed by `(team_id, user_id)`. A team has a UUID identity, unique
canonical lowercase slug, display name, and timestamps; membership records its creation timestamp. The
pre-deployment baseline contains this schema, while
`20260924_0006_administrative_settings.py` remains the forward migration from that baseline and is not
squashed or altered.

Team creation, rename, deletion, and roster mutations use application-owned transactions. Every roster
mutation and empty-team deletion acquires a transaction-scoped PostgreSQL advisory lock derived from the
team ID, then freshly locks and validates the team and, for additions, the target user. Repositories never
commit. A nonempty team cannot be deleted; adding an inactive account is rejected inside the mutation
transaction.

Project-linked deletion guards, derived project-grant cleanup, manager replacement, project ownership
columns, and account-deactivation integration remain slice 2 work. This slice deliberately leaves existing
projects and project memberships unchanged.

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

## Account presentation preferences

[ADR-0043](decisions/ADR-0043-account-level-user-preferences.md) adds an optional one-to-one preferences
row owned by the existing local account, keyed by `user_id` referencing `users.id`. Locale, theme,
`desktop_sidebar_collapsed`, and revision are explicit typed columns. Database constraints enforce the
allowed locale/theme values, non-null theme and collapse flag, and nonnegative revision. The row has no
project relationship and stores no scientific or administrative settings.

Absence means the canonical defaults at revision zero: locale null, theme `system`, and desktop sidebar
expanded. Reads validate the active local owner but never insert defaults. They distinguish an absent
preferences row from an unavailable store or an unresolved/non-local account.

Mutation transactions first lock the existing user row, freshly validate the local credential and current
password requirement, then read the preferences or virtual defaults and compare `expected_revision`.
Locking the parent serializes both initial inserts and subsequent updates. Only changed values cause an
insert/update and revision increment; matching no-ops preserve the revision and do not initialize an absent
row. Revision comparison occurs before the no-op check. Restoring defaults on a persisted row advances its
revision rather than deleting it. Repositories never commit independently.

Concurrent changed first writes at revision zero produce one successful save and one revision conflict,
not duplicate rows or a silent overwrite. Saved values remain independent of sessions and survive logout,
expiry, password changes, and session revocation. Browser-default locale remains null in storage, and
responsive layout cannot alter the explicit desktop preference. No process-local preferences cache is added.

## Deployment branding overrides

This section records the delivered persistence and mutation slices of
[ADR-0040](decisions/ADR-0040-administrative-branding-overrides.md). Its singleton table, migration, read
repository, and revision-checked mutation transactions are implemented.

One deployment-wide settings row stores a fixed `id = 1`, a nonnegative `revision`, a non-null
`branding_overrides` JSONB object, and UTC `updated_at`. Database constraints enforce the singleton identity,
revision bounds, and JSON object shape. The object is a closed Pydantic-validated document containing only
the six allowed branding override fields, validated on reads and writes, not an arbitrary-key configuration
store. No administrative history table is added.

The migration initializes row `1` with revision `0` and `{}`. It never copies environment configuration into
the database. Reads perform no initialization; a missing row after migration is an operational error.
Missing keys inherit deployment fallbacks, whereas explicit JSON nulls and an empty `editors` list remain
overrides that clear a value. Reset deletes selected keys rather than writing their fallback values.

Update and reset share one application-owned transaction protocol: lock the singleton, compare
`expected_revision` with the current revision, apply and validate the complete override document, then
persist and commit atomically. A changed document increments the revision and updates `updated_at`. A
matching-revision no-op leaves both unchanged; a stale request conflicts even if its intended values already
match. Setting an override equal to its fallback is a real change because it pins the value. Revisions track
stored overrides only, not changes in deployment environment configuration.

Settings and public-branding resolution read once per request from the primary database without a
process-local or Redis override cache. Requests reading after commit observe the committed overrides; a read
already in progress may return the previous complete state. API replicas must use equivalent startup fallback
configuration. Storage failures do not silently restore environment branding: administrative settings and
branding JSON return `503 settings_unavailable`. The filesystem-backed logo remains independent.

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
