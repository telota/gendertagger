# Implementation plan

The order is intentional: contracts and scientific regression behavior first, infrastructure composition later.
CI starts with repository initialization and grows with every phase. Phase 7 hardens delivery and
deployment before Phase 8 adds the browser client.

## Phase 0: repository guardrails and preserved baseline

- add repository ignore, line-ending, and editor rules before the first commit [DONE]
- establish the minimal importable package, locked development toolchain, local hooks, and initial CI [DONE]
- establish enforceable naming, docstring, Markdown, link, manifest, and ADR conventions [DONE]
- identify/import the existing script/modules into a migration branch or reference directory [DONE]
- capture small licensed `legacy_characterization` and approved `reference_v1` fixtures [DONE]
- capture current normalization and aggregation outputs [DONE]
- capture method configuration/prompt/model references [DONE]

Exit criterion: a clean checkout installs from the lockfile and runs the same required checks locally and in CI;
the old behavior can be tested independently of the new service.

## Phase 1: contracts and domain behavior

- implement Pydantic enums/models [DONE]
- implement RunConfig + YAML loading/validation [DONE]
- implement method descriptor/adapter protocol [DONE]
- port normalization into pure functions/adapters [DONE]
- port reference aggregation into pure functions [DONE]
- implement certainty/agreement rules [DONE]
- add domain regression tests [DONE]

Exit criterion: scientific behavior passes the golden fixture without DB/API/Celery.

## Phase 2: PostgreSQL persistence

- SQLAlchemy models [DONE]
- repositories/unit-of-work/session design [DONE]
- Alembic initial migration [DONE]
- projects/snapshots/person records [DONE]
- runs/method executions/predictions [DONE]
- aggregation/results [DONE]
- annotations/users/artifacts [DONE]
- DB integration tests [DONE]

Exit criterion: domain objects can round-trip without leaking ORM types upward.

## Phase 3: FastAPI vertical slice

- app/settings/dependencies [DONE]
- auth skeleton [DONE]
- projects/snapshot import endpoints [DONE]
- run creation/read endpoints [DONE]
- methods registry endpoint [DONE]
- aggregation/result endpoints [DONE]
- annotation endpoint [DONE]
- OpenAPI/error contract tests [DONE]
- JSON/API conventions and cursor-pagination primitives [DONE]
- server-side review/list query primitives [DONE]
- typed `CurrentUser` boundary [DONE]

Exit criterion: one run can be created and inspected through HTTP using synchronous placeholder execution.

## Phase 4: Celery execution

- Redis/Celery configuration [DONE]
- persisted task batches [DONE]
- generic transactional dispatch outbox, relay, and reconciliation [DONE]
- CPU queue [DONE]
- atomic ownership-aware batch claims under at-least-once delivery [DONE]
- idempotent batch execution [DONE]
- progress/state transitions [DONE]
- retries/partial failures [DONE]
- persisted Run/MethodExecution progress [DONE]
- SSE progress endpoint with reconnect-safe GET fallback [DONE]

Exit criterion: at least one cheap method runs asynchronously end-to-end.

## Phase 5: method migration

Complete the asynchronous snapshot-import and reference-aggregation paths alongside method migration:

For snapshot imports:

- extend the generic outbox with one unique typed `dataset_snapshot` owner [DONE]
- define versioned source-format, packaging, profile, manifest, member-provenance, and resolved-limit
  contracts [DONE]
- durably stage single or loose uploads before atomically creating their Artifact records, ordered source
  members, pending snapshot, and dispatch [DONE]
- add the identifier-only snapshot-import task envelope and CPU-worker entry point [DONE]
- register single/loose/ZIP/TAR.GZ TEI and single CSV/XLSX/JSON importers without filename inference [DONE]
- preflight ZIP/ZIP64 directory metadata before member allocation and securely stream OOXML metadata before
  read-only XLSX loading, rejecting unsafe members, active content, external relationships, spreadsheet
  coercion, excessive dimensions, and expansion attacks [DONE]
- preserve structured names, repeated forenames, life dates, notes, events, authority IDs, and exact
  source-member/record-locator provenance while excluding source `<sex>` targets [DONE]
- add a default TEI v3 profile sharing strict authority normalization with tabular records, reject JSON/CSV
  persistence-invalid strings and oversized JSON integers, and preserve the versioned TEI v1 and v2
  projections unchanged [DONE]
- conditionally claim duplicate-safe import work and load exact artifacts, manifests, configuration, and limits
  by snapshot ID [DONE]
- stream package validation, parsing, PersonRecord flushes, and the ready transition in one transaction without
  partial commits [DONE]
- roll transient failures back to pending for retry and persist permanent sanitized failures from a clean
  claim [DONE]
- test the supported format matrix, hostile containers, deterministic manifests, broker outage, missing/stale
  intent repair, duplicate delivery, transient rollback, and permanent failure [DONE]

For aggregation:

- add the identifier-only aggregation task envelope and CPU-worker entry point [DONE]
- atomically create and queue each AggregationExecution with its dispatch intent [DONE]
- atomically claim duplicate-safe aggregation work [DONE]
- enforce required per-person Prediction completeness without synthesizing method outputs [DONE]
- persist the complete result set and terminal lifecycle atomically at the current dataset scale [DONE]
- test permanent completeness failure, transient rollback/retry, duplicate delivery, and reconciliation [DONE]

Migrate adapters incrementally:

1. parenthetical-qualifier rule [DONE]
2. gender-guesser [DONE]
3. Wiki-Gendersort [DONE]
4. HIVOTO [DONE]
5. nomquamgender [DONE]
6. GND local snapshot [DONE]
7. transformer classifiers [DONE]
8. local LLM
9. HIVOTO-XGBoost as experimental method [DONE]

Do not wait for all methods before exercising the architecture.

Exit criterion: every declared format/packaging/profile combination reaches one complete immutable
DatasetSnapshot asynchronously with reproducible exact-source and record provenance, and the reference
ensemble reproduces golden outputs through the API, generic dispatch coordinator, CPU worker, persisted
AggregationExecution, and complete immutable result set.

Optional ingestion expansions such as artifact garbage collection, HTTP acceptance idempotency, resumable
progress/cancellation, shared object storage, and additional tabular packaging are tracked in
[`16-open-questions.md`](16-open-questions.md). They are deliberately outside this phase's exit criterion and
should be implemented as separate, reviewable changes when operational requirements justify them.

## Phase 6: evaluation and export

- GND benchmark definition
- metrics and Cohen's kappa
- evaluation reports/artifacts
- TEI export profile
- JSON/CSV exports
- export manifests/provenance

Exit criterion: reference study outputs can be regenerated from a stored run.

## Phase 7: deployment hardening

- production Compose profile for API, workers, and data services
- CPU/GPU/LLM worker separation
- reverse proxy
- backup/restore test
- health/readiness
- structured logging
- resource limits
- protected tagged artifact/image publication with checksums, SBOM, and provenance
- previous-release migration rehearsal and deployment smoke tests
- manual production promotion of immutable artifacts

## Phase 8: Vue annotation/review UI

- stabilize review-items/query API [DONE]
- add review-stream revision conflict handling (`409`) [DONE]
- scaffold Vue 3 + TypeScript + Vite in `frontend/`
- generate transport client/types from FastAPI OpenAPI
- use a server-state query/cache layer; keep Pinia for genuinely shared client state only
- frontend browse/game interface
- verify/correct/defer actions
- audit/history view
- secure HTTP-only session + CSRF integration
- same-origin production build/routing

Exit criterion: a reviewer can correct a machine result and the final-decision view changes without mutating Predictions/AggregatedResults.

## Current implementation focus

Resolve the remaining Phase 0 tracked-data governance decision and the Phase 1 parenthetical mixed-category
compatibility edge, then continue Phase 5 adapter migration with the local LLM, the last of the nine required
reference methods. The transformer classifiers (`hf_distilbert`, `hf_genderize`) and the experimental
HIVOTO-XGBoost adapter reuse the same content-addressed multi-file model manifest (see
[ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md) and
[ADR-0025](decisions/ADR-0025-hivoto-xgboost-adapter.md)); HIVOTO-XGBoost's manifest additionally reuses the
already-compiled `hivoto_lookup` artifact rather than recompiling it. The asynchronous snapshot-import,
lookup-asset, method-execution, and reference-aggregation paths are implemented and must remain covered as
each adapter is added. Do not begin Phase 6 evaluation and export until the complete nine-method reference
ensemble reproduces
the golden outputs through the persisted API-to-worker workflow.
