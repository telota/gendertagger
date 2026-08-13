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

### End-to-end fixture
A tiny TEI file should travel through:

```text
import -> snapshot -> run -> predictions -> aggregation -> annotation -> export
```

and produce stable expected outputs.

## Golden scientific fixtures

Before replacing the existing Python script, freeze a representative subset of current inputs and outputs. The new implementation must reproduce normalized labels and reference aggregation behavior for that fixture.

Maintain two explicit oracles:

- `legacy_characterization`: immutable evidence of what the old pipeline actually did;
- `reference_v1`: the approved normative semantics of this design.

Differences between them require an explicit expectation and, when scientific semantics change, a design
update and ADR. Tests never regenerate expected output as part of their normal execution.

Phase 1 freezes these oracles under `tests/fixtures/scientific/`:

- `legacy_characterization.json` contains eight approved observed cases, source artifact hashes, raw method
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
- aggregation never mutates Predictions
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

Use branch coverage. Maintain complete branch coverage for normative normalization, reference aggregation,
certainty assignment, and TEI certainty projection once those modules exist. Ratchet the overall project floor
upward from the configured baseline instead of manufacturing tests solely to hit a global number.

## CI progression

| Phase | Required gates added |
|---|---|
| 0–1 | lockfile, Ruff, mypy, import boundaries, package build, contract/domain/scientific tests |
| 2 | PostgreSQL repositories plus Alembic clean-head and drift checks |
| 3 | API/auth/error/pagination/OpenAPI contract tests |
| 4 | Redis and at least one real non-eager Celery worker path |
| 5 | adapter conformance; heavy models only on protected/scheduled runners |
| 6 | frontend lint/type/unit/build plus generated-client drift |
| 7 | complete tiny-fixture workflow and reproducibility/export checks |
| 8 | image/Compose smoke, previous-release migration, backup/restore, SBOM/security gates |
