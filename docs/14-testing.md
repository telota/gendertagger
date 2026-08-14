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

### Celery integration tests
Test idempotent retries, batch completion, partial failure, and run completion logic. Avoid eager-mode-only confidence; include at least one real broker integration test in CI or a dedicated profile.

### Asynchronous snapshot-import tests

Exercise snapshot import at the contract, artifact-storage, PostgreSQL, service, API, relay, and real-worker
boundaries:

- the multipart endpoint accepts the complete supported matrix—TEI single/loose/ZIP/TAR.GZ and single
  CSV/XLSX/JSON—durably preserves every exact byte sequence and checksum, and returns a persisted pending
  DatasetSnapshot without invoking a content parser;
- incompatible format/profile/packaging combinations, unsafe or colliding loose names, wrong source-part
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
- valid TEI v1/v2/v3 and tabular sources stream PersonRecords and the ready transition in one transaction with
  matching importer/profile, name-form/event, authority-ID, and member/record-locator provenance;
- direct repository callers cannot mismatch the composite parser version, omit required v2/v3/tabular name
  forms, add events to v1/v2, or attach incomplete source artifacts and members;
- loose and archived TEI enforce collection-wide `xml:id` uniqueness and produce the same canonical person
  projections for equivalent logical XML members;
- JSON native arrays and CSV/XLSX JSON-valued `persName`, `event`, and `idno` cells preserve multiple
  forenames, alternate forms, notes, life dates, events, and GND/VIAF identifiers;
- TEI v3 and tabular typed bare/URI identifiers have parity, exact canonical authority hosts and paths reject
  type conflicts and spoofed hosts, and duplicate normalized schemes fail while v1 characterization is stable;
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
- TEI inline-markup fixtures prove v3 word-boundary insertion excludes comment and Oxygen instruction payloads
  and rejects unsupported descendants, while v1 and v2 separator-free/flattening behavior remains reproducible;
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

Phase 1 freezes these oracles under `tests/fixtures/scientific/`:

- `legacy_characterization.json` contains ten approved observed cases, source artifact hashes, raw method
  labels, LLM self-certainty, and legacy aggregate outputs;
- `reference_v1.json` contains the expected normalized status/label for all ten profiles, the complete
  reference aggregation result, and every approved difference from legacy behavior.

The excerpt is deliberately limited to TEI IDs and scientific method outputs. It excludes names, dates,
biographical text, alternative names, and LLM reasoning. The scientific regression test reads raw labels from
the immutable legacy oracle and executes normalization, reference voting, agreement, and certainty before
comparing against the independent `reference_v1` expectations.

## Migration tests

CI should verify:

- clean DB can migrate to head
- migration downgrade policy if supported
- no unexpected Alembic drift

## Property tests worth considering

- rerunning the same idempotent batch does not create duplicate Predictions
- duplicate snapshot-import delivery never creates duplicate or partial PersonRecords
- aggregation never mutates Predictions
- duplicate aggregation delivery never creates duplicate or partial AggregatedResults
- removing one required Prediction fails reference aggregation rather than changing its vote
- an immutable ready snapshot cannot change
- `abstain` never contributes a vote
- human annotation precedence does not alter historical machine output


## Browser/API contract tests

Before Vue implementation, add backend tests for:

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

When the Vue client exists, CI should generate/check its TypeScript transport client from OpenAPI so Python and TypeScript contracts cannot silently drift.

## Suites and markers

- `unit`, `contract`, `scientific`: required, deterministic merge-request tests;
- `integration`, `postgres`, `redis`: tests with service/process boundaries;
- `e2e`: complete workflow tests over tiny fixtures;
- `slow`, `gpu`, `external`: explicitly enabled protected or scheduled jobs.

Marker selection does not make a suite optional. Every phase declares which suites are required for merge.
Infrastructure-specific tests also carry the `integration` marker; separate CI jobs select their narrower
`postgres`, `redis`, or `e2e` requirement when those suites are introduced.

## Coverage

Use branch coverage. Fast, PostgreSQL, and Redis jobs publish separate raw coverage data; a downstream gate
combines them and enforces the configured 80% project floor. The fast suite independently enforces a 70%
non-regression floor. Service-backed repository code remains measured through the service-backed suites rather
than mock-only tests written to satisfy a fast-only percentage. Maintain complete branch coverage for normative
normalization, reference aggregation, certainty assignment, and TEI certainty projection once those modules
exist. Ratchet the overall project floor upward from the configured baseline instead of manufacturing tests
solely to hit a global number.

## CI progression

| Phase | Required gates added |
|---|---|
| 0–1 | lockfile, Ruff, mypy, Pyright, import boundaries, package build, contract/domain/scientific tests |
| 2 | PostgreSQL repositories plus Alembic clean-head and drift checks |
| 3 | API/auth/error/pagination/OpenAPI contract tests |
| 4 | Redis and at least one real non-eager Celery worker path |
| 5 | adapter conformance, asynchronous snapshot-import atomicity, and asynchronous reference-aggregation completeness; heavy models only on protected/scheduled runners |
| 6 | frontend lint/type/unit/build plus generated-client drift |
| 7 | complete tiny-fixture workflow and reproducibility/export checks |
| 8 | image/Compose smoke, previous-release migration, backup/restore, SBOM/security gates |
