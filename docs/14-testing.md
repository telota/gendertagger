# Testing strategy

## Principles

Tests are deterministic, offline by default, and isolated from shared mutable state. Ordinary CI uses
only synthetic or explicitly cleared fixtures. Live authority services, model downloads, GPUs, and large
corpora are never implicit test dependencies.

Use the narrowest layer that proves a behavior. SQL behavior that matters runs on PostgreSQL rather than
an SQLite substitute.

## Test pyramid

### Pure domain tests
Fast, deterministic tests for:

- label normalization
- abstain vs unknown semantics
- aggregation priority chain
- vote/tie behavior
- certainty tiers
- agreement tiers
- TEI certainty projection
- final-decision resolution

These are the most important tests because they protect the published scientific behavior.

### Pydantic contract tests
Validate invariants and serialized schema stability.

### Repository/persistence tests
Run against PostgreSQL, not SQLite, for SQL behavior that matters.

### API integration tests
FastAPI TestClient/httpx tests for authentication, lifecycle, validation, pagination, and error envelopes.

### Account preferences tests

Verify [ADR-0043](decisions/ADR-0043-account-level-user-preferences.md) at the narrowest relevant layer:

- closed contracts and strict locale/theme/boolean/revision validation, rejected unknown fields, and nonempty
  partial updates;
- default revision zero without a read-side insert, omitted-field preservation, explicit locale clearing,
  matching no-ops, and monotonic revisions when resetting saved values to defaults;
- persistence across separate sessions and isolation between accounts, including accounts with no roles;
- unauthenticated, unresolved/non-local, forced-password, and CSRF failures through the existing envelopes;
- stale updates and stale no-ops returning `409 preferences_revision_conflict`; and
- real PostgreSQL transactions proving concurrent first writes cannot both succeed at revision zero,
  forward migration from the preceding head, fresh-schema upgrade, and Alembic metadata agreement.

The OpenAPI snapshot and generated frontend transport remain part of the public-contract checks. This
backend increment does not require a new settings screen or browser interaction tests.

### Celery integration tests
Test idempotent retries, batch completion, partial failure, and run completion logic. Avoid eager-mode-only confidence; include at least one real broker integration test in CI or a dedicated profile.

### Asynchronous snapshot-import tests

Exercise snapshot import at the contract, artifact-storage, PostgreSQL, service, API, relay, and real-worker
boundaries:

- the multipart endpoint accepts the complete supported matrix—TEI single/loose/ZIP/TAR.GZ and single
  CSV/XLSX/JSON—durably preserves every exact byte sequence and checksum, and returns a persisted pending
  DatasetSnapshot without invoking a content parser;
- incompatible format/packaging combinations, invalid persisted profile provenance, unsafe or colliding loose
  names, wrong source-part
  counts, per-part overflow, aggregate overflow, and source-member-count overflow fail at acceptance;
- loose member order and canonical manifest bytes are deterministic regardless of multipart order, and every
  snapshot member row resolves to its exact Artifact metadata;
- Artifact registration, pending snapshot creation, and the typed outbox intent commit atomically after source
  staging, while a failed acceptance transaction returns no successful `202` resource;
- the generic outbox enforces exactly one `task_batch`, `aggregation_execution`, or `dataset_snapshot` owner and
  rejects a mismatched owner, payload, queue, or target kind;
- relay publication contains only `dataset_snapshot_id`, and broker unavailability leaves the accepted import
  pending and recoverable;
- reconciliation repairs missing snapshot intent, rearms stale publication only while the target remains
  pending, and skips a snapshot locked by an active importer;
- duplicate deliveries have one conditional claim winner, while ready and failed snapshots are no-ops;
- valid TEI v3 and tabular sources stream PersonRecords and the ready transition in one transaction with
  matching importer/profile, name-form/event, authority-ID, and member/record-locator provenance;
- direct repository callers cannot mismatch the composite parser version, omit required imported name forms,
  or attach incomplete source artifacts and members;
- loose and archived TEI enforce collection-wide `xml:id` uniqueness and produce the same canonical person
  projections for equivalent logical XML members;
- JSON native arrays and CSV/XLSX JSON-valued `persName`, `event`, and `idno` cells preserve multiple
  forenames, alternate forms, notes, life dates, events, and GND/VIAF identifiers;
- TEI v3 and tabular typed bare/URI identifiers have parity, exact canonical authority hosts and paths reject
  type conflicts and spoofed hosts, and duplicate normalized schemes fail;
- the exact tabular header/order and object shapes reject unknown, missing, duplicate, coerced, or silently
  discarded fields, oversized JSON integers, and JSON/CSV U+0000 strings, while `<sex>` remains excluded from
  classifier PersonInput;
- hostile ZIP/TAR.GZ fixtures cover traversal and absolute names, normalized full-name and basename collisions,
  links, devices, sparse files, encryption, nesting, classic/ZIP64 directory-count and metadata preflight,
  member/expanded-byte limits, and compression ratios;
- hostile XLSX fixtures cover its ZIP limits and names plus injected macro/dialog/VBA parts or content types,
  entity-encoded external relationship modes, formulas, hyperlinks, merged cells, oversized dimensions,
  populated secondary sheets, and non-string cell values; assertions prove preflight happens before read-only
  workbook materialization and dimension-free bounded sheets remain valid;
- TEI inline-markup fixtures prove word-boundary insertion excludes comment and Oxygen instruction payloads
  and rejects unsupported descendants;
- a permanent parse or contract failure rolls back every PersonRecord before persisting a sanitized failed
  lifecycle;
- injected transient failure or worker loss rolls back the claim and all writes so retry begins again from the
  immutable source, and retry exhaustion records a sanitized terminal failure;
- listing people remains unavailable until the snapshot is ready, and completion exposes the exact full record
  count rather than a committed prefix.

At least one non-eager Redis/Celery test must publish the identifier-only snapshot message through the
coordinator and execute it on a CPU worker with shared artifact storage. PostgreSQL concurrency tests use
separate transactions to prove claim and reconciliation locking. See
[ADR-0020](decisions/ADR-0020-asynchronous-snapshot-import-outbox.md) and
[ADR-0021](decisions/ADR-0021-versioned-multi-format-snapshot-ingestion.md); the latter defines the
supported-matrix, manifest, tabular-shape, and hostile-container cases.

### Asynchronous aggregation tests

Exercise aggregation at the contract, PostgreSQL, service, API, relay, and real-worker boundaries:

- creating an aggregation and its typed dispatch intent commits atomically and returns a persisted queued
  resource without a Celery ID;
- the generic outbox enforces exactly one `task_batch`, `aggregation_execution`, or `dataset_snapshot` owner
  and rejects a mismatched kind, owner, task name, or payload;
- relay publication is at least once, duplicate aggregation messages have one atomic claim winner, and terminal
  resources are no-ops;
- reconciliation repairs missing aggregation intent but skips a target locked by an active worker;
- one `success`, `abstain`, or `error` Prediction from every required execution satisfies completeness, while
  one absent required Prediction fails the aggregation;
- completeness failure never inserts a synthetic Prediction and leaves zero AggregatedResults;
- injected transient failure rolls back the claim and every result so retry can start cleanly;
- successful completion atomically exposes exactly one result per snapshot person and a completed lifecycle;
- retry exhaustion and permanent contract failures expose sanitized terminal diagnostics without partial
  results.

At least one non-eager Redis/Celery test must publish the identifier-only aggregation message through the
coordinator and execute it on a CPU worker. PostgreSQL concurrency tests must use separate transactions to
prove claim and reconciliation locking rather than relying on sequential mocks.

### End-to-end fixture

A tiny representative source should travel through:

```text
staged upload -> asynchronous snapshot import -> run -> predictions -> aggregation -> annotation -> export
```

and produce stable expected outputs.

Keep equivalent single, loose, ZIP, and TAR.GZ TEI fixtures plus JSON, CSV, and XLSX projections. At least one
complete workflow uses TEI, while focused end-to-end import tests prove the other accepted boundaries without
duplicating every downstream scientific-method assertion.

## Golden scientific fixtures

Before replacing the existing Python script, freeze a representative subset of current inputs and outputs. The new implementation must reproduce normalized labels and reference aggregation behavior for that fixture.

Maintain two explicit oracles:

- `legacy_characterization`: immutable evidence of what the old pipeline actually did;
- `reference_v1`: the approved normative semantics of this design.

Differences between them require an explicit expectation and, when scientific semantics change, a design
update and ADR. Tests never regenerate expected output as part of their normal execution.

Phase 1 freezes these oracles under `backend/tests/fixtures/scientific/`:

- `legacy_characterization.json` contains ten approved observed cases, source artifact hashes, raw method
  labels, LLM self-certainty, and legacy aggregate outputs;
- `reference_v1.json` contains the expected normalized status/label for all ten profiles, the complete
  reference aggregation result, and every approved difference from legacy behavior.

The excerpt is deliberately limited to TEI IDs and scientific method outputs. It excludes names, dates,
biographical text, alternative names, and LLM reasoning. The scientific regression test reads raw labels from
the immutable legacy oracle and executes normalization, reference voting, agreement, and certainty before
comparing against the independent `reference_v1` expectations.

## Migration tests

The PostgreSQL CI job runs `alembic upgrade head` against a clean database and then `alembic check`, so a
clean migration to head and the absence of unexpected model-versus-migration drift are both enforced gates.

## Property tests

Hypothesis is a locked development dependency and `backend/tests/conftest.py` registers its execution profiles, but
no `@given` property tests exist yet. The invariants that would most repay property coverage — batch and
delivery idempotency, aggregation immutability, and abstention semantics — are recorded in
[`22-future-development.md`](22-future-development.md). They are currently covered by
example-based tests instead.

## Browser/API contract tests

Backend contract tests cover:

- OpenAPI schema stability/snapshot or intentional-diff review;
- list cursor pagination and stable sorting;
- server-side review filters;
- shared error envelope and stable error codes;
- asynchronous `202 Accepted` resource creation without Celery IDs in public responses;
- snapshot creation returns pending after durable source/outbox acceptance and before parsing;
- snapshot-import creation persists its outbox intent atomically and broker failure leaves it pending;
- aggregation creation persists its outbox intent atomically and broker failure leaves it queued;
- completed aggregation result cardinality equals snapshot person cardinality;
- Run/MethodExecution progress serialization;
- SSE reconnect safety via persisted GET state;
- annotation stale-write `409 Conflict`;
- `/api/v1/me` authorization behavior;
- production CORS defaults and explicit development origin behavior.

The OpenAPI contract test runs `backend/scripts/update_openapi_snapshot.py --check`, so the snapshot has a single
rendering and a failure names the command that fixes it. The frontend's TypeScript transport types are
generated from the committed snapshot, and the `frontend_quality` CI job fails when they drift from it
(`npm run api:check`).

## Operational execution

Test markers, coverage thresholds, and CI requirements are defined in
[`18-engineering-and-quality.md`](18-engineering-and-quality.md). Exact local and service-backed commands are
maintained in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

### Canonical ordinary profiles

[`run_tests.py`](../backend/scripts/run_tests.py) defines the selections used by local development,
push checks, and CI. Each collected ordinary case must match exactly one profile before marker deselection:

| Profile | Selection |
|---|---|
| `fast` | No infrastructure, end-to-end, or protected markers |
| `postgres` | PostgreSQL required, Redis not required, no protected markers |
| `redis` | Redis required, no protected markers; may also require PostgreSQL |

`slow`, `gpu`, and `external` cases remain explicitly protected. An `integration` or `e2e` case without
an infrastructure or protected marker fails collection with its node ID instead of silently disappearing
from CI. PostgreSQL cases do not also need `integration`; a case requiring both databases belongs to the
Redis suite. Collection-only profile runs require neither running services nor TestClient support.

Execution fails early when service-backed profiles lack their explicit test URLs, or when the bounded
asyncio probe detects a runner that cannot support TestClient. Covered runs retain separate coverage data
and the existing partial thresholds. Every profile reports slow setup/call/teardown durations; CI also
publishes JUnit case timings. Full handoff and CI coverage combination still require all three suites.

### Reusable setup and fresh state

Ordinary development runs omit coverage and use focused paths; frontend watch mode reuses transformed
modules. The frontend partitions pure Node tests and isolated jsdom tests with complementary file patterns.
Shared application mounts dispose Vue instances and query clients after each test. Routers, stores,
dependency overrides, mock servers, and mutable records remain independent.

Backend authentication fixtures reuse real Argon2 seed hashes for fixed synthetic passwords within one
process. They still create fresh accounts, credentials, sessions, and cookies; login verification and
password-change hashing use the production hasher. PostgreSQL schema migration already has session scope;
transaction and committed-row cleanup retain their current isolation until separately optimized.

Push checks supplement hook filenames from validated Git refs with a NUL-delimited diff that includes
deleted files and both sides of renames. They always validate documentation and select affected components
conservatively. Uninspectable refs, shared inputs, unknown paths, and an empty path set select both components.
Successful checks are not cached. Full CI remains unconditional while impact selection is validated locally.
