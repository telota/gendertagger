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

### Account preferences increment (ADR-0043)

[ADR-0043](decisions/ADR-0043-account-level-user-preferences.md) defines a bounded personal-presentation
extension: locale (`de`, `en`, browser default), theme (`system`, `light`, `dark`), and explicit desktop
sidebar collapse. It partially supersedes ADR-0030's browser-only locale restriction for authenticated
local accounts while preserving its scientific vocabulary rules and immutable decision history.

1. **Architecture and backend persistence — DELIVERED.** The ADR and governing documentation precede
   closed Pydantic contracts, typed per-account persistence, forward migration `20260925_0008`, and
   application-service/repository behavior. Absent rows return defaults at revision zero without writes.
2. **Self-service API and verification — DELIVERED.** Password-current `GET` and CSRF-protected `PATCH` at
   `/api/v1/me/preferences` derive ownership exclusively from the principal and enforce revision checks
   with safe concurrent first writes. The OpenAPI snapshot and frontend transport are regenerated.
   Run the locked quality gates and PostgreSQL migration/integration checks, including account isolation,
   persistence across sessions, partial updates, explicit locale clearing, auth/CSRF failures, conflicts,
   and concurrent initialization.
3. **Personal settings and presentation integration — DELIVERED.** The lazy `/settings` route
   (`userSettings`) is discoverable in the title-bar account controls and available to every signed-in,
   password-current account independently of its roles. The focused locale/theme/desktop-sidebar form
   keeps drafts local, restores defaults in the draft, and saves explicitly with the canonical revision.
   Principal-scoped query state supplies saved presentation choices; failures retain drafts and a `409`
   requires deliberate reloading of saved values before another save. Pending responses cannot cross
   account boundaries. Anonymous browser choices remain separate and are never migrated to accounts.
   Browser-default locale stays unresolved in storage. Only the saved desktop choice controls collapse
   at widths of at least 1080 CSS pixels; responsive changes never persist preference updates.

The backend and frontend increments remain separately reviewable. Personal preferences do not extend
`/admin/settings`, project settings, or scientific configuration; a wider sidebar redesign is outside
this increment. Frontend verification covers request states, conflicts, account transitions, real
presentation effects, responsive separation, generated-contract consistency, bilingual accessibility,
and the production build.

### Administrative settings increment (ADR-0040)

[ADR-0040](decisions/ADR-0040-administrative-branding-overrides.md) accepts administrative overrides for
six branding fields as a separate extension to the review-client scope. Both backend slices and the
revision-protected frontend editing slice are delivered.

1. **Persistence and administrative read API — DELIVERED.** Closed Pydantic contracts, singleton migration,
   repository/application-service boundaries, default/override resolution, and `GET /api/v1/admin/settings`
   preserve absent keys versus explicit nulls while leaving public branding unchanged.
2. **Writes and public branding integration — DELIVERED.** `PATCH /api/v1/admin/settings` and
   `POST /api/v1/admin/settings/reset` perform revision-checked atomic mutations with safe attribution.
   Public branding resolves committed overrides per request, retains its schema and unauthenticated access,
   and returns the accepted `Cache-Control: no-store` and `503 settings_unavailable` behavior.
3. **Administrative overview — DELIVERED.** `/admin/settings` uses the generated administrative read
   operation for an eligible administrator and presents effective values, deployment fallbacks, and explicit
   override metadata without exposing deployment-only data.
4. **Revision-protected editing and public refresh — DELIVERED.** The form can patch only the six permitted
   fields with a sparse body and baseline revision. Per-field set, clear, and unchanged modes preserve a
   deliberately pinned value equal to its fallback. Reset uses its separate endpoint and confirmation; dirty
   edits block reset rather than silently combining operations. A `409` fetches the newest private settings
   snapshot without replacing the draft or replaying a write; the administrator explicitly reconciles or
   discards. Success adopts the server response and refreshes the shared public-branding query for mounted
   public consumers. A public refresh failure is visible and retried as a read only. Settings mutations are
   excluded from automatic unauthorized replay.

Exit criteria: the
[ADR acceptance criteria](decisions/ADR-0040-administrative-branding-overrides.md#acceptance-criteria-and-future-verification)
are verified. In particular, cleared values survive round trips, resets reveal current deployment
fallbacks, concurrent writes cannot lose changes, invalid requests leave state and revision unchanged,
and committed overrides are visible across API instances without restart. Verify authorization, CSRF,
storage-outage errors, unchanged public branding and logo contracts, and secret-free logs. Import
limits, session policy, scientific behavior, and deployment-only configuration remain unchanged.

Focused frontend contract tests cover sparse patching, local validation, clear/reset separation, conflict
reconciliation, unavailable and uncertain write outcomes, public-cache refresh, and principal cleanup.
Runtime suites and browser verification remain reserved for the user's manual testing stage in this workflow.
Manually verify: an equal-valued override stays pinned after the deployment fallback changes; a dirty form
cannot reset; two administrators produce and reconcile a `409`; and an already-mounted footer, home page,
and legal notice update after a successful save without navigation. Also verify the localized responsive,
keyboard, `503`, and public-refresh-retry states. Do not treat the static checks as that runtime evidence.

### Team and delegated project-membership increment (ADR-0041)

[ADR-0041](decisions/ADR-0041-admin-managed-teams-and-delegated-project-membership.md) is accepted design
work. There is no production or legacy project/team data, so its pre-deployment schema changes amend the
baseline without a backfill or temporary unassigned-project state. The baseline remains followed by
`20260924_0006_administrative_settings.py`; that settings migration is preserved. Every slice stops for
review and a manual commit.

1. **Team persistence and administrative APIs — DELIVERED.** Canonical team contracts, baseline `teams` and
   `team_memberships` schema, repositories/services, global-admin-only team and roster APIs, CLI parity,
   advisory-lock-protected direct roster mutations, secret-free operational logs, generated contract outputs,
   and focused tests are delivered. This slice does not change project creation, project visibility, or
   current project-membership authorization.
2. **Project/team association, manager authority, and membership APIs — DELIVERED.** Required project team,
   manager, and creator relationships; team-aware project creation; scoped candidate lookup; delegated
   membership and manager-transfer APIs; and management-only discovery through
   [`ADR-0042`](decisions/ADR-0042-management-only-project-discovery.md). Project-linked deletion guards,
   derived-grant cleanup, account-deactivation integration, CLI parity, generated contracts, and focused
   tests are delivered.
3. **Team administration UI — DELIVERED.** Global administrators can search and cursor-page teams, create,
   rename, and confirm deletion of teams, and administer one selected direct roster through the existing
   administrator account directory. Team and roster queries are principal-scoped and removed on access loss;
   mutations are not replayed after authentication recovery. Focused frontend tests cover the shipped
   transport and lifecycle states. Runtime suites and manual browser verification remain pending.
4. **Project creation integration and project-membership UI — DELIVERED.** Eligible-team selection,
   administrator roster-derived initial-manager selection, management-only project discovery, member-role
   changes, candidate search, and confirmed manager transfer are implemented. Runtime suites and browser
   verification remain reserved for the user's manual testing stage.

Verification still covers global-role and manager boundaries, candidate-directory privacy, team-removal/grant
races, manager replacement and administrator recovery, deactivation/rejoin non-restoration, fresh-schema
creation, legacy-client fail-closed behavior, CLI parity, and stale principal-scoped frontend state. Runtime
suites and browser verification remain reserved for the user's manual testing stage in this workflow.
