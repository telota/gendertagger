# Future development

Nothing in this document is implemented. It is the canonical home for capabilities that the design
documents deliberately deferred, extracted so that every other document can describe only the system
that actually exists.

This is not a roadmap and not a commitment. Each entry records what the capability is, why it was
deferred, and the constraints any future implementation has to respect — several were deferred
precisely because those constraints are non-trivial. Promoting an entry out of this document requires
its own bounded design and tests, and, for anything touching normalization, aggregation, authority
overrides, certainty tiers, TEI output semantics, or evaluation definitions, a new ADR as required by
[`AGENTS.md`](../AGENTS.md).

## Scientific pipeline and aggregation

### Alternative and weighted aggregation strategies

`AggregationStrategy` defines exactly one member, `reference_v1`, which reproduces the published
unweighted reference behavior. Candidate alternatives include confidence-weighted voting, soft voting
over method probability outputs, custom per-method ensemble weights, and including experimental methods
such as `hivoto_xgboost` in the decision rather than only in agreement analysis.

The governing constraint is that these must arrive as new versioned enum members with their own
configuration and their own persisted AggregationExecutions. They must never silently replace or
redefine the reference strategy, because published reference results have to stay reproducible from
stored provenance. See [`07-methods-and-aggregation.md`](07-methods-and-aggregation.md).

### Alternative evaluation definitions and benchmarks

`EvaluationDefinitionId` defines exactly one member, `gnd_benchmark_v1`. Further benchmarks — a
human-annotated gold standard, a multi-source consensus reference set, or a different metric
configuration over the same benchmark — would let the ensemble be assessed against something other
than GND agreement.

The same versioning rule applies as for aggregation strategies: a new definition is a new enum member
with its own configuration and its own persisted executions, never an edit to an existing one. A
benchmark also needs an explicit account of how its reference labels were produced, since the system
must never present a benchmark as unqualified "ground truth". See
[`10-evaluation.md`](10-evaluation.md).

### Wider golden fixture coverage

The `legacy_characterization` and `reference_v1` fixtures gate normalization and aggregation against
silent scientific drift. Broader coverage — more name morphologies, more authority-conflict shapes,
more certainty-tier boundaries — would tighten that gate.

Any addition must keep the fixtures small, licensed for redistribution, and offline, and must preserve
the property that a scientific change either keeps them passing or records an approved, ADR-referenced
expected difference. See [`14-testing.md`](14-testing.md).

### Additional TEI export profiles

`TeiExportProfile` defines one encoding, `tei_p5_gender_v1`. Editions using different TEI structures or
different gender vocabularies would need their own profiles.

These must be added as explicit versioned profile members rather than as corpus-specific conditionals
threaded through core export code, so that earlier projections stay byte-reproducible. See
[`08-ingestion-and-export.md`](08-ingestion-and-export.md).

## Ingestion and data management

### Label-bearing and ground-truth importers

Direct source `<sex>` values are deliberately not `PersonInput` fields, because existing values in a
register may themselves be the output of an earlier classification pass. Treating them as input would
risk circularity, where the system evaluates itself against its own prior labels.

A future label-bearing importer would need to capture such values as a separate, explicitly provenanced
benchmark or comparison channel — never merged into the classification input projection — and record
how the labels originated so that evaluation can state what it is measuring against. This is the
ingestion half of a non-GND benchmark. See [`03-pydantic-contracts.md`](03-pydantic-contracts.md).

### Reference-aware artifact garbage collection

Content-addressed storage intentionally publishes source bytes before the database transaction accepts
their Artifact references, so a failed transaction can leave an unreferenced blob behind.

A future mark-and-sweep collector must use a grace period, account for uploads that are concurrently
being accepted, define retention for failed snapshots, expose dry-run and capacity metrics, and never
infer liveness from filenames or storage age alone.

### Idempotent snapshot acceptance

HTTP retries currently create distinct DatasetSnapshot resources even when their exact bytes deduplicate
in artifact storage. Celery delivery is already idempotent independently of this.

An optional idempotency-key contract would need to scope keys to the authenticated actor, project, and
operation; bind each key to the declared format and packaging, derived profile, and canonical source
fingerprint;
return the original accepted snapshot on an exact replay; reject reuse with different input; and define
expiration and concurrent-reservation behavior.

### Observable progress, cancellation, and resumable publication

The import worker keeps its claim, PersonRecord writes, and `ready` transition in a single database
transaction. That gives simple all-or-nothing recovery, but `importing` stays transaction-local and long
imports externally appear `pending`.

Larger workloads may justify a separate import-attempt resource with ownership leases, staged records,
monotonic member and record progress, cancellation rules, idempotent chunk writes, stale-attempt
recovery, and one atomic publication step. This is an architectural alternative to the current
transaction model, not a progress field that can safely be added in isolation.

### Shared object storage and direct staging

The filesystem ArtifactStorage is the local-first default and requires the API and worker processes to
share the same absolute artifact root.

An S3- or MinIO-compatible adapter must preserve streaming checksums, immutable content addressing,
conditional publication, verified reads, and common API/worker visibility. Very large deployments might
additionally stage sources directly into object storage, accepting artifact identifiers only after
server-side integrity and project-ownership validation.

### Additional tabular packaging

CSV, XLSX, and JSON support `single` packaging only, while TEI additionally supports `loose`, `zip`, and
`tar_gz`.

Supporting packaged tabular collections requires an explicit homogeneous-versus-mixed member policy,
deterministic cross-file record ordering, collection-wide ID checks, profile and header agreement,
member-level provenance, aggregate limits, and safe treatment of XLSX as an already-compressed
container. It must not be enabled merely by routing tabular members through the TEI archive reader.

### Cross-snapshot comparison and annotation inheritance

`person_records` carries a unique `(dataset_snapshot_id, tei_id)` constraint, so `xml:id` is a stable
comparison key across a project's snapshots, but no comparison or diffing tooling exists.

Two capabilities build on that key. The first is snapshot diffing: reporting which person records were
added, removed, or changed between two snapshots. The second is annotation inheritance — carrying a
verified human decision forward to a newer snapshot when the underlying record is unchanged. Inheritance
must never happen silently; a carried-forward decision has to remain distinguishable from one made
against the snapshot in front of the reviewer. See
[`08-ingestion-and-export.md`](08-ingestion-and-export.md).

### Durable cross-run method cache

The current method cache is per-process, serves the synchronous `POST /classify` endpoint only, and is
never persisted. There is deliberately no `method_cache_entries` table.

A durable cross-run cache would have to key entries on the exact person-input fingerprint plus the fully
resolved method configuration, model revision, and normalization version, so that a configuration change
can never serve a stale label. It also needs an operational retention and eviction policy, which cannot
be specified sensibly until real workload sizes are known. Cache provenance must remain visible on any
Prediction that reuses a cached value, and the cache must never substitute for Prediction rows. See
[`04-persistence.md`](04-persistence.md).

### Addressable multi-output exports

`GET /exports/{export_execution_id}/download` returns output bytes directly when an export produced exactly one
output, and returns the manifest when it produced several, as a loose TEI collection does. Individual
member outputs are not separately addressable.

Options include per-member download routes and archive packaging of multi-member exports. Either must
preserve the manifest as the authoritative record of what was produced, along with each output's
checksum. See [`08-ingestion-and-export.md`](08-ingestion-and-export.md).

## Security, authentication and multi-tenancy

### Institutional OIDC/SSO integration

Authentication is deliberately provider-neutral: `AuthenticationBackend` is a protocol. The shipped
provider is the local account backend from
[ADR-0031](decisions/ADR-0031-local-database-authentication.md); no institutional provider is integrated.

Because every backend terminates into the same `CurrentUser` abstraction, adding one should not require
a divergent authorization path. The work is in session establishment, logout and token refresh
semantics, and mapping provider claims onto local roles without letting an external directory silently
grant `admin`. SSO users need no `user_credentials` row, so local and SSO accounts can coexist. See
[`13-auth-and-security.md`](13-auth-and-security.md).

### Per-account login throttling

The gateway throttles login attempts per client address (see
[`13-auth-and-security.md`](13-auth-and-security.md)), but the application itself counts nothing: failures
against one account from many addresses are neither slowed nor counted, and a stack reached without the
gateway is not throttled at all. Add a per-username backoff before the service is reachable from outside the
institution's network.

It must key on the normalized username whether or not an account exists, and it must keep the generic
`401 invalid_credentials` response, so it does not reveal whether a username exists. Prefer a growing delay
to a hard lockout: a lockout would let an outsider lock a reviewer out on purpose. See
[ADR-0031](decisions/ADR-0031-local-database-authentication.md).

### Self-service password recovery

Global administrators can reset local passwords through `POST /api/v1/admin/users/{user_id}/reset-password`
or the break-glass `gendertagger users reset-password` command. There is no self-service "forgot password"
flow.

Adding one needs outbound email, which the repository does not have. The reset token must be single-use
and short-lived, and using it must revoke the account's existing sessions, as the administrative reset
already does.

### User directory for membership administration

Project roles are held through memberships
([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)). The admin-only
`PUT /api/v1/projects/{project_id}/members/{user_id}` addresses the member by user ID.
`GET /api/v1/admin/users` now supplies the missing admin-only, searchable, cursor-paginated local-account
directory ([ADR-0039](decisions/ADR-0039-administer-local-accounts-over-http.md)). The administrator screen
that consumes it remains deferred, as does any less-privileged user-directory projection.

### Append-only history of role and membership changes

Membership grants, role changes, and revocations are logged with the acting administrator, and a
membership row keeps only its creation and last-update times. Global role assignment through
`gendertagger users create` is not recorded at all. A durable, queryable audit trail would append one
immutable record per change instead, mirroring how annotations supersede rather than overwrite.

### Separate machine and API token flow

Browser sessions use secure HTTP-only cookies with CSRF validation, which suits interactive clients but
not unattended ones. External machine clients would need a separate bearer or OIDC client-credentials
flow.

It must terminate into the same `CurrentUser` and authorization checks, and must not weaken or bypass
browser-session semantics — in particular, a token flow must not become a way to skip CSRF validation
for a browser-originated request.

## Task execution and operations

### Multi-host worker topology

The deployment target is a single Docker Compose project with segmented `public`, `edge`, `core`,
`model`, and `egress` networks. GPU and LLM workers could run on separate hosts against the same broker
and database.

This is constrained by the artifact-storage model: API and worker processes currently need a shared
absolute artifact root, so multi-host topology is coupled to the shared object storage entry above. It
is also subject to network and security review, since it moves database and broker traffic off a single
host. Kubernetes remains an explicit non-goal. See [`01-architecture.md`](01-architecture.md).

### Resource-class-specific batch tuning

Every adapter in the reference registry registers the same `_CPU_BATCH_SIZE` of 200 records per batch.
Batch size is per-registration data, so differentiating it per resource class is already possible in
principle.

Useful tuning would be measurement-driven and would likely differ sharply between cheap lookup adapters
and GPU or LLM adapters. Any dynamic or runtime-adjusted sizing must keep the executed partition
reproducible: each TaskBatch persists the deterministic slice it covers, and that record is what makes a
run reconstructible. See [`06-task-queue.md`](06-task-queue.md).

### Task batch cancellation

The lifecycle enums admit a `cancelled` state, and runs can be marked cancelled, but there is no
mechanism to interrupt work already claimed by a worker.

Real cancellation needs a cooperative check inside batch execution, a defined outcome for partially
completed batches, and a rule for what happens to Predictions already committed by a cancelled
execution. It must not leave an execution in a state that later reads as complete.

### Operational metrics and dashboards

Health and readiness endpoints plus structured JSON logging are in place. There is no metrics export.

Prometheus instrumentation and Grafana dashboards would most usefully cover outbox depth and relay lag,
queue depth per resource class, batch throughput and failure rates, and import and export durations.
Outbox depth is the highest-value signal, because a stalled dispatch coordinator is otherwise visible
only as work that silently never starts.

## Frontend and API integration

### SSE `Last-Event-ID` resume

`GET /runs/{run_id}/events` projects current state rather than replaying history, and no event log is
retained. Clients reconnect and refresh through ordinary GET endpoints instead.

Supporting `Last-Event-ID` resume requires persisted, ordered events with stable identifiers — a
storage and retention question, not just a header. Authoritative state must remain in PostgreSQL, and
losing a connection must continue to lose no scientific or workflow state.

### ETag and `If-Match` review concurrency

Optimistic concurrency over the review stream is implemented through the domain revision:
`expected_revision` on the command, `409 Conflict` with `annotation_conflict` on a stale write.

HTTP ETag and `If-Match` headers could mirror the same revision for clients that prefer standard HTTP
caching semantics. The domain revision must stay authoritative; the headers would be a projection of it,
never a second source of truth.

### Signed-URL artifact delivery

Uploads and downloads pass through API resources, and the browser never receives server filesystem
paths. For very large artifacts, a storage adapter could issue signed URLs.

This must retain the same artifact-resource semantics and authorization checks, so that a signed URL is
a delivery optimization rather than a way around project ownership and role checks. It is coupled to the
shared object storage entry above.

### Game mechanics in the review client

Playful scoring, streaks, or similar UI effects may be worth retaining in the review interface to sustain
reviewer engagement.

The hard constraint is that they stay entirely outside scientific annotation semantics. A click that
produces an annotation must still map to exactly the same explicit reviewed decision, with the same
reviewer identity and the same audit trail, as one made through a plain interface. Scoring must never
influence which records are shown for review, since that would bias the corrected sample. See
[`09-annotation-and-review.md`](09-annotation-and-review.md).

### Administrative redaction and audit-logged deletion

Ordinary review history is never hard-deleted, because human annotation is part of scholarly provenance.
Legal or ethical obligations may nonetheless require removing specific content.

Any redaction capability must be explicit, restricted to `admin`, and itself audit-logged, so that the
fact of a redaction remains visible even when its content does not. It must not become a general-purpose
delete path for inconvenient review history. See [`09-annotation-and-review.md`](09-annotation-and-review.md).

## CI/CD and governance

### Property-based test suite

Hypothesis is a locked development dependency and its execution profiles are registered in
`tests/conftest.py`, but no `@given` tests exist; the invariants below are currently covered by
example-based tests.

The invariants that would most repay property coverage are: rerunning an idempotent batch creates no
duplicate Predictions; duplicate snapshot-import delivery creates no duplicate or partial PersonRecords;
aggregation never mutates Predictions; duplicate aggregation delivery creates no duplicate or partial
AggregatedResults; removing one required Prediction fails reference aggregation rather than changing its
vote; a ready snapshot cannot change; `abstain` never contributes a vote; and human annotation precedence
never alters historical machine output. See [`14-testing.md`](14-testing.md).

### Container image digest enforcement

`RunCreate.container_image_digest` is optional, so a containerized run can be recorded without pinning
the exact image that produced it.

Requiring it when the API detects it is running in a container would strengthen reproducibility, but it
needs a reliable in-container detection path and a defined behavior for legitimate non-containerized
runs such as local CLI execution. See
[`11-provenance-and-reproducibility.md`](11-provenance-and-reproducibility.md).

### Repository governance automation

CI enforces documentation, contract-naming, package-initializer, lint, type, test, coverage, packaging,
secret-detection, and SBOM gates. Ownership and approval policy is not automated.

GitLab `CODEOWNERS` plus security approval rules would let the scientific-behavior review requirement in
[`AGENTS.md`](../AGENTS.md) — that changes to normalization, aggregation, authority overrides, certainty
tiers, TEI output semantics, or evaluation definitions carry a design-document update and an ADR — be
enforced mechanically rather than by reviewer memory.

### Automated production promotion

Production promotion is a documented manual SOP: pull tagged images, run the one-shot migration service,
restart services, verify health, with a scripted rollback path.

A CD or GitOps pipeline could automate it, but the properties the manual procedure guarantees must
survive: immutable tagged artifacts, a fresh backup taken immediately before deployment, a rehearsed
migration, and an unambiguous rollback. Automation must not make it easier to deploy an unrehearsed
migration. See [`21-production-promotion.md`](21-production-promotion.md).
