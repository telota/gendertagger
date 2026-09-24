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
- define source-format, packaging, derived-profile, manifest, member-provenance, and resolved-limit
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
- add the TEI profile sharing strict authority normalization with tabular records and reject JSON/CSV
  persistence-invalid strings and oversized JSON integers [DONE]
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

Exit criterion: every declared format/packaging combination reaches one complete immutable
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
- secure HTTP-only session + CSRF integration (backend provider done per
  [ADR-0031](decisions/ADR-0031-local-database-authentication.md); client session handling remains)
- same-origin production build/routing

Exit criterion: a reviewer can correct a machine result and the final-decision view changes without mutating Predictions/AggregatedResults.

### Administrative settings increment (ADR-0040)

[ADR-0040](decisions/ADR-0040-administrative-branding-overrides.md) accepts administrative overrides for
six branding fields as a separate extension to the review-client scope. Slice 1, persistence and the
administrative read API, is delivered. Public branding remains environment-backed until Slice 2. Stop for
architect/user review and a manual commit before starting the next slice.

1. **Persistence and administrative read API — DELIVERED.** Adds the closed Pydantic contracts, singleton
   migration, repository/application-service boundaries, default/override resolution, and
   `GET /api/v1/admin/settings`. It initializes revision `0` with an empty override document and preserves
   absent keys versus explicit nulls. OpenAPI, generated transport, and focused coverage are updated. Public
   branding behavior remains unchanged in this slice.
2. **Writes and public branding integration.** Add `PATCH /api/v1/admin/settings` and
   `POST /api/v1/admin/settings/reset` with the shared revision-checked transaction, field validation,
   and safe operational attribution. Integrate the shared resolver into public branding while retaining
   its schema and unauthenticated access. Apply `Cache-Control: no-store` and the accepted
   `503 settings_unavailable` behavior without environment fallback. Document migration ordering,
   consistent replica fallbacks, and older-release rollback behavior.
3. **Frontend separately.** Add accessible forms, effective/deployment-default indicators, distinct
   clearing and resetting actions, stale-write handling, and refresh of mounted branding consumers.
   Use generated contracts and existing session/CSRF behavior.

Exit criteria: the
[ADR acceptance criteria](decisions/ADR-0040-administrative-branding-overrides.md#acceptance-criteria-and-future-verification)
are verified. In particular, cleared values survive round trips, resets reveal current deployment
fallbacks, concurrent writes cannot lose changes, invalid requests leave state and revision unchanged,
and committed overrides are visible across API instances without restart. Verify authorization, CSRF,
storage-outage errors, unchanged public branding and logo contracts, and secret-free logs. Import
limits, session policy, scientific behavior, and deployment-only configuration remain unchanged.

The eventual implementation requires model/service, PostgreSQL concurrency, API/contract, and frontend
coverage. Runtime suites and browser verification remain reserved for the user's manual testing stage
in this workflow. Only the documentation checker and `git diff --check` run for this documentation-only
increment; accepting the design does not claim those future runtime checks have passed.
