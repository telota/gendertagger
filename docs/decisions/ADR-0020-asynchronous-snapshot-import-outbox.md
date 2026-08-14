# ADR-0020: Execute dataset-snapshot imports asynchronously through the transactional outbox

**Status:** Accepted

## Context

`POST /api/v1/projects/{project_id}/snapshots` returns `202 Accepted`, but the first vertical slice stores the
upload, parses the complete TEI document, commits PersonRecords in batches, and moves the DatasetSnapshot to
`ready` or `failed` before sending the response. The status code therefore describes an asynchronous command
that the implementation does not yet provide. Request latency and API-process resource use also grow with the
register, and a client cannot observe the persisted import lifecycle while work is running.

An uploaded request body is different from an ordinary identifier-only command. The request-bound
`UploadFile` and its temporary file cannot be passed to a worker after the response. The API must first copy
the complete bounded source into shared immutable artifact storage. Only then can a later worker reliably open
the same bytes. PostgreSQL and Redis still cannot commit atomically, so publishing directly from FastAPI after
creating the snapshot would recreate the lost-message window closed for method batches by
[ADR-0015](ADR-0015-transactional-batch-dispatch-outbox.md) and for aggregations by
[ADR-0016](ADR-0016-asynchronous-aggregation-outbox.md).

The synchronous importer commits bounded PersonRecord batches independently. That is not safe under Celery's
at-least-once delivery: a worker crash can leave an `importing` snapshot with a committed prefix of its people,
while reprocessing the source can collide with the snapshot-scoped TEI-ID uniqueness constraint. A ready
snapshot must instead expose either the complete imported projection or none of it.

The initial public import scope is one TEI XML file under a selected versioned TEI profile. Related loose TEI
files, ZIP or TAR.GZ packaging, and CSV, XLSX, or JSON person-register imports require source-manifest,
validation, and tabular-shape contracts. Those additive contracts are decided separately in
[ADR-0021](ADR-0021-versioned-multi-format-snapshot-ingestion.md); this decision remains the asynchronous and
transactional foundation for every supported format.

## Decision

The initial asynchronous boundary accepts one bounded TEI XML upload and one supported TEI import profile.
FastAPI streams the complete upload into content-addressed artifact storage, enforcing the configured byte
limit and computing its SHA-256 digest. It then registers the Artifact, creates a `pending` DatasetSnapshot,
and creates that snapshot's typed outbox intent in one PostgreSQL transaction. The endpoint returns the
persisted pending snapshot with `202 Accepted` after both the source bytes and database transaction are
durable. It does not parse XML or persist PersonRecords in the request. ADR-0021 extends this same acceptance
and execution boundary with additional source members, manifests, packaging, and record formats; it does not
move their parsing back into the request.

Artifact storage and PostgreSQL are separate durability systems. If artifact storage succeeds but the database
transaction fails, no snapshot is accepted and an unreferenced content-addressed blob may remain for later
garbage collection. The API never returns `202` before source staging succeeds, and a worker never receives an
`UploadFile`, temporary path, storage URI, or source payload.

The generic transactional outbox gains a `dataset_snapshot` target alongside `task_batch` and
`aggregation_execution`. Exactly one nullable owner ID is present, and each DatasetSnapshot owns at most one
dispatch. Its frozen `SnapshotImportTaskMessage` contains only `dataset_snapshot_id`. The dispatch coordinator
publishes that message at least once to the existing `cpu` queue, and the worker loads the authoritative
snapshot, Artifact, import configuration, and parser version from PostgreSQL and shared artifact storage.
Broker unavailability therefore does not invalidate an accepted import.

For the current bounded-source scale, one worker transaction conditionally claims a `pending` snapshot, moves
it through `importing`, streams its securely configured importer over the stored artifact set, flushes bounded
PersonRecord groups without intermediate commits, and marks the snapshot `ready` with its complete record
count. The target row remains locked for that transaction. Competing or duplicate deliveries cannot both claim
it, and delivery after a successful commit returns the existing terminal resource without reparsing. The
uncommitted `importing` value is therefore an internal persistence guard rather than public progress: ordinary
readers continue to observe `pending` until the transaction atomically exposes `ready`.

A permanent source or contract failure rolls back the complete import transaction before a fresh transaction
marks the snapshot `failed` with a sanitized diagnostic. A transient storage, database, or unclassified failure
rolls back the claim and every PersonRecord so the snapshot remains `pending` for bounded Celery retry.
Retry exhaustion records a terminal sanitized failure from a clean claim. A worker crash before commit likewise
leaves no committed partial projection; redelivery can start again from the immutable source. Reconciliation
repairs missing or stale publication only while the snapshot remains dispatchable and skips a target locked by
an active worker.

The singular `source_artifact_id`, source checksum, versioned parser provenance, and JSON import configuration
remain the stable DatasetSnapshot boundary. An import adapter must distinguish semantic source format
(for example TEI, CSV, XLSX, or JSON) from packaging (single file, loose collection, or archive). A collection
may be represented by an immutable manifest that references each exact staged file, while an uploaded archive
may remain the exact source artifact. Such adapters define deterministic member order, cross-file identity
validation, archive expansion limits, and an unambiguous tabular representation. ADR-0021 supplies those
rules without changing the identifier-only task or atomic worker transaction defined here.

## Consequences

- `202 Accepted` truthfully means that the exact source, pending DatasetSnapshot, and dispatch intent are
  durable; it does not mean parsing has started or that Redis is available.
- Upload transfer, bounded staging, hashing, and the short acceptance transaction still occur before the HTTP
  response. Parsing and PersonRecord persistence move entirely to a CPU worker.
- Clients receive a pending resource and use `GET /api/v1/snapshots/{snapshot_id}` to observe `ready` or
  `failed`; invalid source content is not reported as terminal in the initial response.
- At-least-once publication and worker loss do not expose or strand a committed prefix of PersonRecords.
- The atomic streamed import holds one PostgreSQL transaction and snapshot-row lock while parsing and writing.
  If larger future sources make that unacceptable, chunking requires a new decision defining attempt
  ownership, staging tables, completeness validation, and atomic publication.
- API and CPU-worker processes require access to the same immutable artifact-storage namespace. Redis remains
  non-authoritative and does not require scientific backup.
- External artifact storage can accumulate unreferenced bytes after failed acceptance transactions; safe
  reference-aware garbage collection is an operational follow-up.
- The snapshot and artifact contracts support additive source manifests and adapters without format-specific
  snapshot columns. ADR-0021 supplies the reviewed multi-format contracts and security limits while retaining
  this decision's asynchronous and atomic boundary.
