# Remaining open questions

The main architecture is decided. These are deliberately non-blocking or implementation-time choices.

## Authentication identity provider

Browser mechanics are decided: same-origin secure HTTP-only session cookies plus CSRF protection. The concrete identity provider is still open. Options include local accounts for the first deployment or integration with institutional SSO/OIDC; both should resolve to the same `CurrentUser` abstraction.


## Exact batch sizes/concurrency

Tune per method from measurements. Preserve them in MethodExecution configuration/provenance.

## Alternative aggregations

The system should eventually permit weighted or experimental strategies, but the first implementation must reproduce the unweighted published reference strategy.

## TEI project profiles

The reference export profile is documented. If additional editions use different TEI structures or gender vocabularies, introduce explicit import/export profiles rather than corpus-specific conditionals throughout core code.

## Cross-snapshot annotation semantics

A human annotation is made in a snapshot context but the `xml:id` is canonically stable within a project. Decide later whether verified decisions should be suggested/carried forward to a newer snapshot when the relevant person record is unchanged. Never carry them silently.

## Cache retention

Define operational retention/eviction after real workload sizes are known.

## Snapshot-ingestion expansion candidates

The supported asynchronous import contract is complete for TEI in `single`, `loose`, `zip`, and `tar_gz`
packaging and for single-file CSV, XLSX, and JSON. The following capabilities are optional expansions rather
than unfinished acceptance criteria for that contract. Each should receive its own bounded design and tests
before implementation.

### Reference-aware artifact garbage collection

Content-addressed storage intentionally publishes source bytes before the database transaction accepts their
Artifact references. A failed transaction can therefore leave an unreferenced blob. A future collector may
reclaim such blobs through mark-and-sweep reference checks, but it must use a grace period, account for uploads
concurrently being accepted, define retention for failed snapshots, expose dry-run and capacity metrics, and
never infer liveness from filenames or storage age alone.

### Idempotent snapshot acceptance

HTTP retries currently create distinct DatasetSnapshot resources even when their exact bytes deduplicate in
artifact storage. A future optional idempotency-key contract should scope keys to the authenticated actor,
project, and operation; bind each key to the declared format, packaging, profile, and canonical source
fingerprint; return the original accepted snapshot on an exact replay; reject reuse with different input; and
define expiration and concurrent-reservation behavior. Celery delivery is already idempotent independently of
this possible HTTP feature.

### Observable progress, cancellation, and resumable publication

The current worker keeps its claim, PersonRecord writes, and `ready` transition in one database transaction.
That gives simple all-or-nothing recovery but leaves `importing` transaction-local and makes long imports
externally appear pending. Larger workloads may justify a separate import-attempt resource with ownership
leases, staged records, monotonic member/record progress, cancellation rules, idempotent chunk writes, stale
attempt recovery, and one atomic publication step. This is an architectural alternative to the current
transaction model, not a progress field that can safely be added in isolation.

### Shared object storage and direct staging

The filesystem ArtifactStorage remains the local/private default and requires API and worker processes to
share the same absolute artifact root. A future S3- or MinIO-compatible adapter should preserve streaming
checksums, immutable content addressing, conditional publication, verified reads, and common API/worker
visibility. Very large deployments may additionally stage sources directly into object storage and accept
artifact identifiers only after server-side integrity and project-ownership validation.

### Additional tabular packaging

CSV, XLSX, and JSON currently support `single` packaging only. Supporting loose or archive-packaged tabular
collections requires an explicit homogeneous-versus-mixed member policy, deterministic cross-file record
ordering, collection-wide ID checks, profile/header agreement, member-level provenance, aggregate limits, and
safe treatment of XLSX as an already-compressed container. It must not be enabled merely by routing tabular
members through the TEI archive reader.
