# Persistence design

## Database

PostgreSQL is the durable source of truth for application state, scientific results, annotation history, and provenance metadata.
Redis is not durable scientific storage.

Persistence is implemented with SQLAlchemy 2.x declarative mappings under `gendertagger.db` and
Alembic migrations. The schema ships as a single baseline revision,
`migrations/versions/20260815_0001_baseline.py`, and `gendertagger.db.session` refuses any engine or
session whose dialect is not PostgreSQL.

## Transaction and repository boundaries

Application services own a unit of work. One unit of work owns one SQLAlchemy session and therefore one
database transaction. Repositories share that session, flush when generated identifiers or constraint results
are needed, and never commit independently. Leaving a unit-of-work context rolls back any uncommitted work and
closes the session; successful commands call `commit()` explicitly.

Repository interfaces belong to the application boundary. Their inputs and outputs are canonical Pydantic
contracts or explicit scalar identifiers, never SQLAlchemy rows. The implementations under `gendertagger.db`
perform the row/contract mapping and may use SQLAlchemy internally. Services receive a unit-of-work factory so
tests and non-HTTP entry points use the same transaction semantics.

## Tables

The baseline revision creates 21 tables, and revision `20260903_0002` adds the two local-account
authentication tables, for 23 tables mapped under `gendertagger.db`:

- projects and ingestion (`db/projects.py`): `projects`, `dataset_snapshots`,
  `snapshot_source_members`, `person_records`, `person_external_ids`;
- execution (`db/executions.py`): `runs`, `method_executions`, `task_batches`, `predictions`;
- aggregation (`db/aggregations.py`): `aggregation_executions`, `aggregation_method_executions`,
  `aggregated_results`;
- evaluation (`db/evaluations.py`): `evaluation_executions`, `evaluation_method_executions`;
- export (`db/exports.py`): `export_executions`;
- review (`db/reviews.py`): `users`, `user_roles`, `project_memberships`, `annotations`,
  `review_states`; `user_roles` holds only the global `operator` and `admin` roles, and
  `project_memberships` holds one project role per `(project_id, user_id)`, per
  [ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md);
- authentication (`db/auth.py`): `user_credentials`, `user_sessions`, per
  [ADR-0031](decisions/ADR-0031-local-database-authentication.md);
- artifacts (`db/artifacts.py`): `artifacts`;
- dispatch (`db/dispatches.py`): `batch_dispatches`, the generic transactional outbox whose typed
  owners are task batches, aggregation executions, dataset snapshots, evaluation executions, and
  exports.

## Key constraints

### Projects and snapshots

- `projects.slug` unique.
- `projects.working_aggregation_execution_id` is a nullable `ON DELETE RESTRICT` foreign key to
  `aggregation_executions.id`. `projects` is created before `aggregation_executions` in the baseline
  migration, so the column is declared with `use_alter=True`, matching every other forward-referencing
  foreign key in `db/artifacts.py`. The repository, not a database constraint, enforces that the referenced
  aggregation belongs to a run of this project's own snapshot and is `completed`
  ([ADR-0035](decisions/ADR-0035-project-working-aggregation.md)).
- `dataset_snapshots` immutable when status becomes `ready`.
- unique `(dataset_snapshot_id, tei_id)` for person records, plus a unique `(id, dataset_snapshot_id)`
  key that the review tables reference compositely.
- the cross-snapshot logical identity `(project_id, tei_id)` resolves through
  `dataset_snapshots.project_id`; `person_records` carries no denormalized project column.

`person_records` retains ordinary columns for the stable `surname`, `forenames`, and `alt_names` projections
used by methods and browser search. It also has JSONB `events` and a nullable JSONB `name_forms` column for the
ordered, Pydantic-validated source structures defined by
[ADR-0017](decisions/ADR-0017-structured-tei-person-name-forms.md). The `name_forms_array` check
requires a JSON array whenever the column is non-null, and `events_array` requires one
unconditionally. Null means the legacy import profile did not capture the structure. A v2 value is
a populated array with exactly one regular form, and v3 retains that contract. The repository rejects non-null
forms for a v1 TEI snapshot and missing forms for a v2, v3, or tabular snapshot. It also requires empty events
for TEI v1 and v2 while permitting the event-aware v3 and tabular profiles, so alternate application callers
cannot persist profile/projection provenance that disagrees.

For a complete import config, the repository resolves the canonical parser, collection, and packaging
version through the same closed importer registry used at acceptance and requires an exact `parser_version`
match before source-member or completion persistence. This prevents alternate repository callers from
combining a profile with misleading implementation provenance.

Every imported PersonRecord stores non-null `source_member_name` and `source_record_locator` together. The
repository verifies that a loose or single named member belongs to the snapshot; for archive packaging it
verifies the snapshot's one exact source container and accepts the package reader's validated internal member
name. The record locator then identifies the person within that member. Non-blank constraints and non-null
columns ensure complete source provenance. Ready-snapshot mutation protection covers these
source structures and locators together with the stable flat fields.

The migration adding `name_forms` does not backfill ready snapshots. Flat alternative-name strings cannot
recover component boundaries, order metadata, or subtype, and reparsing into an existing ready snapshot would
violate immutability. Re-importing the preserved source with an explicit structured profile creates a new
snapshot; new imports default to v3. Because the structured value is stored on `person_records`, the existing
ready-snapshot row-mutation protection applies to it without a separate child-table trigger.

Snapshot acceptance first stores every bounded upload outside PostgreSQL. One database transaction then
registers all source Artifacts, creates the pending DatasetSnapshot, inserts its ordered source-member rows,
and creates the snapshot's dispatch intent. A loose TEI collection additionally registers its canonical
manifest as the snapshot's primary Artifact. A database rollback therefore accepts neither the artifact
records nor source provenance nor the snapshot nor its work intent, although the content-addressed storage
backend may retain unreferenced blobs for later garbage collection.

`snapshot_source_members` is unique by `(dataset_snapshot_id, ordinal)` and by
`(dataset_snapshot_id, logical_name)`. Each row references one exact Artifact and repeats its checksum, size,
media type, and safe logical name as immutable snapshot provenance. Ordinals are zero-based and contiguous at
the application boundary. Source-member rows cannot be inserted, updated, or deleted after their snapshot is
ready. See [ADR-0021](decisions/ADR-0021-versioned-multi-format-snapshot-ingestion.md).

At the current bounded-source scale, the worker's conditional pending claim, `importing` transition, package
validation, streamed parser, PersonRecord inserts, and ready transition share one transaction. Repository
flushes may keep insert groups bounded but do not commit them independently. A transient exception or worker
loss rolls back both the claim and all rows. A permanent parse or contract error also rolls back before a
separate transaction marks the snapshot failed, so failed and retried imports expose no committed prefix. See
[ADR-0020](decisions/ADR-0020-asynchronous-snapshot-import-outbox.md).

Consequently, `importing` is a transaction-local persistence state for new asynchronous imports, not an
externally observable progress update. Normal readers see the previously committed `pending` row while the
worker holds its claim, then see one atomic transition to `ready` or, after rollback, to `failed`.

### Predictions

`predictions` is unique on:

```text
(method_execution_id, person_record_id)
```

so one method execution holds at most one result per person.

Each row stores:

- normalized `label`, which `status_label_consistent` requires to be present for `success` and absent
  for `abstain` and `error`
- `status`
- `method_confidence`, rejected when it is `NaN` or infinite
- `raw_label`
- `raw_output` JSONB
- `metadata` JSONB
- `input_fingerprint`, constrained to 64 lowercase hex characters
- `created_at`

Every Prediction belongs to one persisted TaskBatch; `task_batch_id` is required rather than optional
provenance. Prediction insertion locks the target TaskBatch and validates its owning Run and MethodExecution.
All three must be `running`, the batch must belong to the execution, and the people supplied must exactly match
the batch's deterministic `(record_offset, record_count)` slice of the Run's snapshot. A single write cannot
mix TaskBatches.

The complete prediction set and the completed TaskBatch state are committed in one transaction. Deferred
database checks reject a commit when prediction rows remain beneath a running batch, when a completed batch
does not have exactly its assigned people, or when its tallies disagree with those immutable outputs. Insert
guards enforce the same lifecycle, ownership, and snapshot-slice rules for direct SQLAlchemy or SQL callers.
Existing Prediction rows remain update/delete-immutable.

### Aggregation

Aggregation executions reference the exact MethodExecutions included. Do not infer "all methods in run" later
if a subset was selected.

`aggregated_results` is unique on `(aggregation_execution_id, person_record_id)`. At the current dataset scale,
the executor inserts the full person-result set and marks the AggregationExecution completed in one
transaction. Completion requires result cardinality equal to the immutable snapshot's person cardinality.
The repository requires the supplied unique person IDs to equal the snapshot's complete person set before
insertion. Insert and deferred database guards apply the same rule to direct callers: results may be inserted
only while the aggregation is `running`, every person must belong to its Run's snapshot, committed results
must have a completed parent, and a completed aggregation must have exact coverage. Failed or retried attempts
expose no partial rows. Existing AggregatedResult rows remain update/delete-immutable.

### Execution lifecycle and provenance sealing

PostgreSQL enforces legal lifecycle transitions for Runs, MethodExecutions, TaskBatches, and
AggregationExecutions in addition to repository validation. Terminal execution resources cannot be reopened
to admit late output. A MethodExecution cannot become terminal until all of its TaskBatches are terminal, and
a Run cannot become terminal until all of its MethodExecutions are terminal. Lifecycle rows cannot be deleted,
and status-specific start/finish timestamps and failure details are enforced at the database boundary.

New MethodExecutions may be appended only while their Run is non-terminal, and new TaskBatches only while
their MethodExecution is non-terminal. AggregationExecutions remain independently rerunnable and may be
created for an existing terminal Run; their selected MethodExecutions must still be completed outputs from
that Run. Creation locks the Run row with `FOR NO KEY UPDATE` before it looks for a matching live or
completed aggregation, so concurrent identical requests serialize and return one aggregation between them
([ADR-0034](decisions/ADR-0034-reuse-matching-aggregation-on-creation.md)). The lock admits the
`FOR KEY SHARE` locks of foreign-key checks, so it does not block workers writing rows that reference the
Run.

Creation-time scientific provenance is immutable. Updates to those rows are limited to operational fields:

- Runs: lifecycle status, start/finish timestamps, and failure diagnostic;
- MethodExecutions: lifecycle status, progress counts, timestamps, and failure details;
- TaskBatches: lifecycle status, worker/attempt metadata, tallies, timestamps, and failure details;
- AggregationExecutions: lifecycle status, timestamps, and failure details.

Consequently, snapshot/configuration hashes, code/runtime versions, method/model/data identifiers, queue and
batch-slice definitions, aggregation strategy/configuration, and owning-resource IDs cannot be rewritten.
The ordered `aggregation_method_executions` membership may be inserted only while its aggregation is pending;
before transition to queued or running it must be nonempty with contiguous positions starting at zero. After
scheduling it is sealed, and existing membership rows cannot be updated or deleted. Once any execution
resource reaches a terminal state, the entire row is sealed, including fields that were operationally mutable
while work was active.

### Transactional dispatch outbox

One outbox row belongs to exactly one durable work target. `batch_dispatches` has five nullable
`ON DELETE RESTRICT` foreign keys - `task_batch_id`, `aggregation_execution_id`,
`dataset_snapshot_id`, `evaluation_execution_id`, and `export_id`, the last pointing at
`export_executions.id` - with:

- the `exactly_one_target` check, `num_nonnulls(...) = 1` over all five owner columns;
- a unique constraint per owner column, so a target never has two outbox rows;
- a `DispatchTarget` kind consistent with the selected owner and payload, enforced by the
  discriminated-union create contracts in `gendertagger.models.dispatch`;
- explicit `pending`/`published` state, availability time, attempt count, relay lease, publication time, and
  sanitized last-error diagnostic.

The outbox row is created in the same transaction as its target. Relay and reconciliation update delivery
metadata without owning scientific results. Reconciliation locks both dispatch and target rows with
`FOR UPDATE SKIP LOCKED`; it does not infer that an old timestamp alone proves a worker has stopped. See
[ADR-0015](decisions/ADR-0015-transactional-batch-dispatch-outbox.md) and
[ADR-0016](decisions/ADR-0016-asynchronous-aggregation-outbox.md), and
[ADR-0020](decisions/ADR-0020-asynchronous-snapshot-import-outbox.md).

### Annotations

`annotations` is append-only: the `trg_annotations_append_only` trigger rejects every UPDATE and
DELETE. Each row stores:

- `dataset_snapshot_id` and `person_record_id`, bound together by a composite foreign key to the
  `(id, dataset_snapshot_id)` key on `person_records`, so an annotation cannot name a person from a
  different snapshot;
- `action` (`verify`, `correct`, `defer`) and `label`, kept consistent by `action_label_consistent`:
  verify and correct carry a canonical label, defer carries none;
- `reviewer_user_id`;
- `comment` where supplied;
- `aggregated_result_id` where the decision references one;
- `supersedes_annotation_id`, which `does_not_supersede_self` forbids from pointing at the row itself;
- `resulting_revision`, positive and unique per `(dataset_snapshot_id, person_record_id)` through the
  `review_stream_revision` constraint;
- `created_at`.

### Review state and optimistic concurrency

`review_states` is a small mutable projection whose composite primary key is the snapshot/person
record:

```text
PRIMARY KEY (dataset_snapshot_id, person_record_id)
revision NOT NULL
current_annotation_id NULLABLE
workflow_state NOT NULL
updated_at NOT NULL
```

It carries the same composite foreign key to `person_records (id, dataset_snapshot_id)` as
`annotations`, and `revision_head_consistent` ties its mutable fields together: revision `0` means no
head and `unreviewed`, while any higher revision means a non-null head and either `reviewed` or
`deferred`.

Creating an annotation is one database transaction:

1. lock the person record and its ReviewState row with `SELECT ... FOR UPDATE`, inserting a
   revision-0 state when none exists yet;
2. compare the command's `expected_revision`;
3. fail with an application-level conflict if it is stale;
4. insert the immutable Annotation;
5. increment ReviewState.revision and update its current head/workflow state;
6. commit.

ReviewState is a query/concurrency projection and must be rebuildable from annotation history. It does not make historical Annotation rows mutable.

### Query indexes for browser review

The review query in `gendertagger.db.review_repository` filters and orders on ordinary indexed
columns:

- snapshot/person identity, via the `(dataset_snapshot_id, tei_id)` unique key and
  `ix_person_records_dataset_snapshot_id_surname`;
- canonical/final label and aggregation outcome, via `ix_aggregated_results_person_record_id_outcome`;
- certainty and agreement tiers, via `ix_aggregated_results_aggregation_execution_id_certainty_tier`
  and `ix_aggregated_results_aggregation_execution_id_agreement_tier`;
- review workflow state, via `ix_review_states_workflow_state_updated_at`;
- reviewer and annotation head, via `ix_annotations_reviewer_user_id_created_at` and
  `ix_annotations_person_record_id_created_at`;
- selected method execution, prediction label, and prediction status, via
  `ix_predictions_method_execution_id_status` and `ix_predictions_person_record_id_status`;
- name and identifier search over `tei_id`, `surname`, `forenames`, `alt_names`, and
  `person_external_ids.value`, via `ix_person_external_ids_scheme_value`.

Further indexes follow actual query plans. These frequently queried fields stay out of JSONB.

## JSONB policy

Use JSONB for method-specific raw outputs, flexible provenance fragments, bounded source structures such as
`name_forms` and `events`, and configuration snapshots. Do not hide core queryable fields such as labels,
states, IDs, timestamps, agreement values, or the flat name-search projection inside JSONB.

## Artifact storage

Artifact bytes live outside PostgreSQL. Each `artifacts` row contains:

- logical type
- storage URI/path
- SHA-256 checksum
- byte size
- media type
- nullable producer references: `project_id`, `dataset_snapshot_id`, `run_id`, `method_execution_id`,
  `aggregation_execution_id`, `evaluation_execution_id`, `export_id`
- `metadata` JSONB

`gendertagger.services.artifact_storage.ArtifactStorage` is the boundary protocol - `store`, `open`,
and `materialize` - and `gendertagger.storage.local.LocalArtifactStorage` is the v1 filesystem
backend, so domain contracts never see a filesystem path. Rows are immutable: `trg_artifacts_immutable`
rejects UPDATE and DELETE.

Large method lookup datasets remain artifacts rather than application tables. Wiki-Gendersort, HIVOTO, and
GND use separate immutable SQLite files compiled from retained source artifacts; PostgreSQL stores their
checksums, metadata, and MethodExecution references only. Workers validate and materialize a selected digest
to a local read-only path. This keeps retained authority revisions out of application backups and replication
while preserving exact method-data provenance. See
[ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md).

## Caching

Caches are optimizations, not truth. No cache table exists, and run execution computes and persists
every Prediction with its own Run-local provenance.

The only cache is in-process. `gendertagger.services.classification.DirectClassificationService`
keeps a bounded LRU, `DEFAULT_CACHE_MAX_SIZE = 50_000`, keyed by

```text
(method name, resolved method configuration serialized as JSON, input name)
```

and serves the synchronous `POST /classify` endpoint only. It is per-process, never persisted, and
never a substitute for Prediction rows. A durable cross-run method cache is described in
[`22-future-development.md`](22-future-development.md).
