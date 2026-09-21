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
8. local LLM [DONE]
9. HIVOTO-XGBoost as experimental method [DONE]

Do not wait for all methods before exercising the architecture.

Exit criterion: every declared format/packaging/profile combination reaches one complete immutable
DatasetSnapshot asynchronously with reproducible exact-source and record provenance, and the reference
ensemble reproduces golden outputs through the API, generic dispatch coordinator, CPU worker, persisted
AggregationExecution, and complete immutable result set.

Optional ingestion expansions such as artifact garbage collection, HTTP acceptance idempotency, resumable
progress/cancellation, shared object storage, and additional tabular packaging are tracked in
[`22-future-development.md`](22-future-development.md). They are deliberately outside this phase's exit
criterion and should be implemented as separate, reviewable changes when operational requirements justify
them.

## Phase 6: evaluation and export

- GND benchmark definition [DONE]
- metrics and Cohen's kappa [DONE]
- evaluation reports/artifacts [DONE]
- TEI export profile [DONE]
- JSON/CSV exports [DONE]
- export manifests/provenance [DONE]

Exit criterion: reference study outputs can be regenerated from a stored run.

## Phase 7: deployment hardening

- production Compose profile for API, workers, and data services [DONE]
- CPU/GPU/LLM worker separation [DONE]
- reverse proxy [DONE]
- backup/restore test [DONE]
- health/readiness [DONE]
- structured logging [DONE]
- resource limits [DONE]
- protected tagged artifact/image publication with checksums, SBOM, and provenance [DONE]
- previous-release migration rehearsal and deployment smoke tests [DONE]
- manual production promotion of immutable artifacts [DONE]

## Phase 8: Vue annotation/review UI

Milestone sequencing, open decisions, and delivery risks for this phase are expanded in
[`24-frontend-delivery-plan.md`](24-frontend-delivery-plan.md); the component-level source material
is [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md). The checklist below remains the
definition of done.

- stabilize review-items/query API [DONE]
- add review-stream revision conflict handling (`409`) [DONE]
- scaffold Vue 3 + TypeScript + Vite in `frontend/` [DONE]
- generate transport client/types from FastAPI OpenAPI [DONE]
- use a server-state query/cache layer; keep Pinia for genuinely shared client state only
- frontend browse/game interface
- verify/correct/defer actions
- audit/history view
- secure HTTP-only session + CSRF integration
- same-origin production build/routing

Exit criterion: a reviewer can correct a machine result and the final-decision view changes without mutating Predictions/AggregatedResults.

## Current implementation focus

Phases 0 through 7 are complete. All nine reference method adapters are implemented and registered,
alongside the experimental HIVOTO-XGBoost adapter, and the asynchronous snapshot-import, lookup-asset,
method-execution, reference-aggregation, evaluation, and export paths all run end to end through the
persisted API-to-worker workflow.

The active work is Phase 8, the Vue annotation and review client. Its backend prerequisites are already
met: the review-items query API is stable and review-stream revision conflicts return `409`. The remaining
Phase 8 items are frontend work. The scaffold and the generated transport client are in place
(milestone M1); the application shell and every screen remain to be built. The second active track is
operating the stack in production under [`21-production-promotion.md`](21-production-promotion.md).

The transformer classifiers (`hf_distilbert`, `hf_genderize`) and the experimental HIVOTO-XGBoost adapter
share the content-addressed multi-file model manifest (see
[ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md) and
[ADR-0025](decisions/ADR-0025-hivoto-xgboost-adapter.md)); HIVOTO-XGBoost's manifest reuses the
already-compiled `hivoto_lookup` artifact rather than recompiling it. Scientific behavior stays gated on
the golden fixtures as the client is built on top of it.
