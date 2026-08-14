# Implementation plan

The order is intentional: contracts and scientific regression behavior first, infrastructure composition later.
CI starts with repository initialization and grows with every phase; Phase 8 hardens delivery and deployment.

## Phase 0: repository guardrails and preserved baseline

- add repository ignore, line-ending, and editor rules before the first commit
- establish the minimal importable package, locked development toolchain, local hooks, and initial CI
- establish enforceable naming, docstring, Markdown, link, manifest, and ADR conventions
- identify/import the existing script/modules into a migration branch or reference directory
- capture small licensed `legacy_characterization` and approved `reference_v1` fixtures
- capture current normalization and aggregation outputs
- capture method configuration/prompt/model references

Exit criterion: a clean checkout installs from the lockfile and runs the same required checks locally and in CI;
the old behavior can be tested independently of the new service.

## Phase 1: contracts and domain behavior

- implement Pydantic enums/models
- implement RunConfig + YAML loading/validation
- implement method descriptor/adapter protocol
- port normalization into pure functions/adapters
- port reference aggregation into pure functions
- implement certainty/agreement rules
- add domain regression tests

Exit criterion: scientific behavior passes the golden fixture without DB/API/Celery.

## Phase 2: PostgreSQL persistence

- SQLAlchemy models
- repositories/unit-of-work/session design
- Alembic initial migration
- projects/snapshots/person records
- runs/method executions/predictions
- aggregation/results
- annotations/users/artifacts
- DB integration tests

Exit criterion: domain objects can round-trip without leaking ORM types upward.

## Phase 3: FastAPI vertical slice

- app/settings/dependencies
- auth skeleton
- projects/snapshot import endpoints
- run creation/read endpoints
- methods registry endpoint
- aggregation/result endpoints
- annotation endpoint
- OpenAPI/error contract tests
- JSON/API conventions and cursor-pagination primitives
- server-side review/list query primitives
- typed `CurrentUser` boundary

Exit criterion: one run can be created and inspected through HTTP using synchronous placeholder execution.

## Phase 4: Celery execution

- Redis/Celery configuration
- persisted task batches
- generic transactional dispatch outbox, relay, and reconciliation
- CPU queue
- atomic ownership-aware batch claims under at-least-once delivery
- idempotent batch execution
- progress/state transitions
- retries/partial failures
- persisted Run/MethodExecution progress
- SSE progress endpoint with reconnect-safe GET fallback

Exit criterion: at least one cheap method runs asynchronously end-to-end.

## Phase 5: method migration

Complete the asynchronous snapshot-import and reference-aggregation paths alongside method migration:

For snapshot imports:

- extend the generic outbox with one unique typed `dataset_snapshot` owner
- define versioned source-format, packaging, profile, manifest, member-provenance, and resolved-limit contracts
- durably stage single or loose uploads before atomically creating their Artifact records, ordered source
  members, pending snapshot, and dispatch
- add the identifier-only snapshot-import task envelope and CPU-worker entry point
- register single/loose/ZIP/TAR.GZ TEI and single CSV/XLSX/JSON importers without filename inference
- preflight ZIP/ZIP64 directory metadata before member allocation and securely stream OOXML metadata before
  read-only XLSX loading, rejecting unsafe members, active content, external relationships, spreadsheet
  coercion, excessive dimensions, and expansion attacks
- preserve structured names, repeated forenames, life dates, notes, events, authority IDs, and exact
  source-member/record-locator provenance while excluding source `<sex>` targets
- add a default TEI v3 profile sharing strict authority normalization with tabular records, reject JSON/CSV
  persistence-invalid strings and oversized JSON integers, and preserve the versioned TEI v1 and v2
  projections unchanged
- conditionally claim duplicate-safe import work and load exact artifacts, manifests, configuration, and limits
  by snapshot ID
- stream package validation, parsing, PersonRecord flushes, and the ready transition in one transaction without
  partial commits
- roll transient failures back to pending for retry and persist permanent sanitized failures from a clean claim
- test the supported format matrix, hostile containers, deterministic manifests, broker outage, missing/stale
  intent repair, duplicate delivery, transient rollback, and permanent failure

For aggregation:

- add the identifier-only aggregation task envelope and CPU-worker entry point
- atomically create and queue each AggregationExecution with its dispatch intent
- atomically claim duplicate-safe aggregation work
- enforce required per-person Prediction completeness without synthesizing method outputs
- persist the complete result set and terminal lifecycle atomically at the current dataset scale
- test permanent completeness failure, transient rollback/retry, duplicate delivery, and reconciliation

Migrate adapters incrementally:

1. parenthetical-qualifier rule
2. gender-guesser
3. Wiki-Gendersort
4. HIVOTO
5. nomquamgender
6. GND local snapshot
7. transformer classifiers
8. local LLM
9. HIVOTO-XGBoost as experimental method

Do not wait for all methods before exercising the architecture.

Exit criterion: every declared format/packaging/profile combination reaches one complete immutable
DatasetSnapshot asynchronously with reproducible exact-source and record provenance, and the reference
ensemble reproduces golden outputs through the API, generic dispatch coordinator, CPU worker, persisted
AggregationExecution, and complete immutable result set.

Optional ingestion expansions such as artifact garbage collection, HTTP acceptance idempotency, resumable
progress/cancellation, shared object storage, and additional tabular packaging are tracked in
[`16-open-questions.md`](16-open-questions.md). They are deliberately outside this phase's exit criterion and
should be implemented as separate, reviewable changes when operational requirements justify them.

## Phase 6: Vue annotation/review UI

- stabilize review-items/query API
- add review-stream revision conflict handling (`409`)
- scaffold Vue 3 + TypeScript + Vite in `frontend/`
- generate transport client/types from FastAPI OpenAPI
- use a server-state query/cache layer; keep Pinia for genuinely shared client state only
- frontend browse/game interface
- verify/correct/defer actions
- audit/history view
- secure HTTP-only session + CSRF integration
- same-origin production build/routing

Exit criterion: a reviewer can correct a machine result and the final-decision view changes without mutating Predictions/AggregatedResults.

## Phase 7: evaluation and export

- GND benchmark definition
- metrics and Cohen's kappa
- evaluation reports/artifacts
- TEI export profile
- JSON/CSV exports
- export manifests/provenance

Exit criterion: reference study outputs can be regenerated from a stored run.

## Phase 8: deployment hardening

- production Compose profile
- CPU/GPU/LLM worker separation
- reverse proxy
- backup/restore test
- health/readiness
- structured logging
- resource limits
- protected tagged artifact/image publication with checksums, SBOM, and provenance
- previous-release migration rehearsal and deployment smoke tests
- manual production promotion of immutable artifacts

## First IDE task

Finish the Phase 0 reference fixtures after the repository tooling, then start with Phase 1 contracts only. Do
not let the coding agent scaffold FastAPI, SQLAlchemy, Celery, Vue, Docker, and ten classifier adapters in one
heroic commit. That path leads directly to a very modern archaeological site.
