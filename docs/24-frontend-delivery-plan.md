# Frontend delivery plan

## Purpose and authority

[`15-implementation-plan.md`](15-implementation-plan.md) remains the authoritative phased plan and its
Phase 8 checklist remains the definition of done. This document expands that checklist into sequenced
milestones with exit criteria, records the decisions that must be taken before or during each milestone,
and names the risks that would otherwise surface late.

It does not reopen scope. Capabilities deliberately deferred stay recorded in
[`22-future-development.md`](22-future-development.md); the component-level source material is
[`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md).

Sizes below are relative (S/M/L), not calendar estimates. Absolute scheduling depends on team capacity and
is deliberately not asserted here.

## Where the work actually starts

Phase 8's backend prerequisites and blocking semantic decisions are met.

| Precondition | State | Blocks |
|---|---|---|
| A real `AuthenticationBackend` | **Met.** `DatabaseAuthenticationBackend` is the default: admin-provisioned local accounts and server-side sessions ([ADR-0031](decisions/ADR-0031-local-database-authentication.md)). | — |
| Three missing read endpoints | **Met.** `GET /projects` ([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)), `GET /aggregations/{id}/results/{result_id}/predictions`, and `GET /annotations?snapshot_id=&tei_id=` are delivered. | — |
| Collections to navigate by | **Met.** `GET /projects/{id}/snapshots`, `GET /snapshots/{id}/runs`, and `GET /runs/{id}/aggregations`, `/evaluations`, and `/exports` list their resources newest first, so the routes can recover the identifiers they carry. | — |
| Blocking semantic decisions | **Met.** D1–D6 are resolved. See [Decisions](#decisions-taken). | — |

M1 is delivered and M2 is not blocked, since a real authentication backend is in place. No milestone waits on
a missing read endpoint any more.

## Existing scaffolding and what it still needs

Deployment and CI already anticipate the client. Reusing it correctly is cheaper than rebuilding it.

**Already in place.**

- [`deploy/proxy/nginx.conf`](../deploy/proxy/nginx.conf) routes `/api/v1/` to the API with
  `proxy_buffering off` and 86400 s timeouts — SSE is ready — and serves everything else from the frontend
  container. Same-origin topology per [`17-frontend-integration.md`](17-frontend-integration.md) is already
  implemented.
- `client_max_body_size 500M` matches `GENDERTAGGER_MAX_SNAPSHOT_UPLOAD_BYTES`.
- `compose.yaml`, `compose.dev.yaml`, and `compose.prod.yaml` all declare a `frontend` service with
  resource limits.
- `.gitlab-ci.yml` already has `build_and_publish_frontend` and `frontend_sbom` jobs.

**Delivered by M1.**

- [`deploy/docker/frontend.Dockerfile`](../deploy/docker/frontend.Dockerfile) now runs `npm ci` and
  `npm run build` from `frontend/package.json` and its lockfile, separate from `backend/package.json`,
  which exists only for Pyright. Node is pinned by version and digest and agrees with `engines`.
- The production stage serves the build with a history-mode fallback
  ([`frontend/nginx/default.conf`](../frontend/nginx/default.conf)), decision D13.
- The `development` stage installs dependencies and starts the Vite server. `npm run dev` on the host,
  proxying `/api/v1` to `http://localhost:8000`, is the working hot-reload path.
- The image job built its context from the repository root, which cannot see `frontend/package.json` as a
  top-level file. `.kaniko_build` now takes an `IMAGE_CONTEXT` per image, and the frontend uses `frontend/`,
  matching the build context in `compose.yaml`.

**Delivered development-workflow follow-up.**

- `compose.dev.yaml` now selects the Vite `development` target with a distinct `frontend-dev` image tag,
  mounted source, and isolated container dependencies. The gateway forwards hot-reload WebSockets at
  `http://localhost:8080`; host-side Vite remains an optional alternative.
- Production image builds use `compose.yaml` with `compose.prod.yaml`, without the development override.
  Source edits, dependency refreshes, and explicit worker/migration steps are documented in the
  [quickstart development workflow](../QUICKSTART.md#development-workflow).

**Still needed.**

- `frontend_sbom` now produces a real dependency tree. The repository's provenance and licence culture applies
  to npm packages too: the M1 and M2 dependencies are justified in [`frontend/README.md`](../frontend/README.md),
  including the headless accessibility library chosen under decision D9.

## Accessibility as a delivery workstream

Accessibility is a legal obligation for a public-sector body, not a quality goal, and it cannot be a closing
phase. Retrofitting it after the components exist is the expensive path, and an audit at the end discovers
structural problems when they are hardest to fix.

It is therefore treated as a constraint on every milestone, with its own acceptance criteria, rather than as
a milestone of its own. The conformance target is **WCAG 2.2 AA**, specified in
[`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md).

### Why the wireframe cannot be carried over

The accepted wireframe is a layout reference and was never built for conformance. Measured against the file:
90 `div role="button"` constructs against 15 real buttons; 13 ARIA attributes in 1016 lines; only two roles
used; 591 `px` values against 11 `rem`; no skip link and no reduced-motion handling. The toggles, the
threshold slider, and the selection checkboxes are non-semantic `<span>` elements that no keyboard or screen
reader can operate, and the runtime tab pattern sets `role="tab"` without a `tablist` or panels.

Three of these disappear with decisions already taken — the slider with D2, the tab row with D7, the
`role="button"` shim with the coding guidelines. The rest are a standing instruction: **the wireframe's
interaction markup is not a reference for implementation**, only its layout and information architecture.

### Per-milestone accessibility criteria

| Milestone | Added criterion |
|---|---|
| M0 | Accessibility owner appointed (D18); statement obligation confirmed; test protocol drafted (D17) |
| M1 | `rem`-based token scale; automated checks in CI — linter accessibility rules, `axe-core` in component tests, contrast assertions for both themes |
| M2 | Skip link, focus management, live-region infrastructure, accessible theme and locale switches, documented keyboard model; the shell passes a manual screen-reader pass |
| M3 | Form labelling and error association; upload limits announced, not only shown |
| M4 | Long-running progress announced through a live region without flooding it |
| M5 | The hardest screen: pinned action bar must not obscure focus (2.4.11); shortcuts suppressed in text inputs; annotation results and conflicts announced; list selection state exposed |
| M6 | Annotation history readable as a structured list, not a visual timeline only |
| M7 | Every chart has a table equivalent; no meaning carried by colour alone |
| M8 | Export lifecycle and completion announced |
| M9 | Full internal conformance pass across the D17 matrix; user testing round completed (D18); statement and feedback mechanism published if required |

No milestone is complete while its criterion is outstanding. Automated checks are a floor: they catch a
minority of real defects, and none of the wireframe's non-semantic controls would have been fully caught by
them.

### Evidence and declaration

The conformance target is WCAG 2.2 AA (D15) and the assessment is internal (D16). Self-declaration is an
accepted basis, but it shifts the burden onto the record: the test protocol from D17 is written down before
M1, every pass is logged with date, scope, and findings, and the accessibility owner from D18 holds that
evidence. An accessibility statement, if required, is drafted during M9 from that accumulated record rather
than reconstructed at the end.

## Milestones

| ID | Milestone | Size | Hard dependencies |
|---|---|---|---|
| M0 | Decisions and backend prerequisites | M | scope-exclusion confirmation; accessibility assignments |
| M1 | Scaffold and transport | S | none — D3, D8, D11, D12 all resolved |
| M2 | Application shell | M | M1; a working auth backend; `GET /api/v1/branding` ([ADR-0036](decisions/ADR-0036-institution-branding-configuration.md)), **delivered** |
| M3 | Projects and import | M | M2 |
| M4 | Runs and aggregation | L | M3 |
| M5 | Review workbench | L | M4 |
| M6 | Person browser and audit view | M | M5; D5 resolved |
| M7 | Evaluation and statistics | M | M4 |
| M8 | Export | S | M4 |
| M9 | Optional paths and production build | M | M5 |

### M0 — Decisions and backend prerequisites

**Goal.** Remove the things that would force rework later.

**Status.** In progress. D1 is implemented: `DatabaseAuthenticationBackend` is the default backend,
`gendertagger users create` provisions accounts, and the generated transport already covers the login,
logout, and password-change endpoints. D6 is implemented: project roles come from per-project
memberships, and `GET /projects` lists only the caller's projects
([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)). All three blocking read endpoints are
delivered. The written confirmation of the scope exclusions and the two accessibility
[outstanding assignments](#outstanding-assignments) remain.

**Work.**

- D1–D6 are resolved. D3 is recorded as
  [ADR-0030](decisions/ADR-0030-bilingual-client-with-untranslated-canonical-vocabulary.md) and D6 as
  [ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md).
- Implement D1 per [ADR-0031](decisions/ADR-0031-local-database-authentication.md): admin-provisioned local
  accounts, DB-backed sessions, admin-only password reset. The same backend serves development and
  production; there is no separate throwaway development backend. **Done.**
- Apply D2 to the screen content of Import, Übersicht, and Einstellungen before those screens are designed
  in detail — the threshold control is removed, not reskinned.
- Implement the three blocking read endpoints from
  [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md): `GET /projects`, a per-person
  method-result read model, and annotation history. **Done.**
- Confirm the v1 scope exclusions in writing, so the wireframe's unsupported features are not silently
  expected.

**Exit criterion.** A developer can authenticate against a local deployment, list projects, and read one
person's full method results and annotation history through `/api/v1`.

### M1 — Scaffold and transport

**Goal.** A buildable, type-safe client skeleton with no hand-written schema.

**Status.** Delivered and merged to `main`. Lint, formatting, type checking, the test suite
with its coverage floor, the production build, the message-catalogue check, and the transport drift check all
pass locally from a clean `npm ci`, and each check was shown to fail on a deliberate violation. The Docker
image build and the GitLab jobs are written but have not been run yet.

**Work.**

- Scaffold Vite + Vue 3 + TypeScript in `frontend/`, keeping the existing Docker build context.
- Generate `schema.d.ts` from the FastAPI OpenAPI document; wrap it in a typed fetch client with
  `credentials: 'include'` and CSRF header attachment.
- Add a CI job that regenerates the client and fails on drift. The source is the committed snapshot
  `contracts/openapi-v1.json`, which the backend contract test already keeps equal to the live schema,
  so a contract change is caught even when nobody touches the frontend.
- Enable the real build stages in the Dockerfile and wire the dev target.
- Set up i18n for German and English per D3: message catalogues, locale-aware dates and numbers, and a lint
  rule against hard-coded user-facing strings. Canonical labels and tier names are excluded from translation.
- Establish the semantic, theme-scoped token layer for both themes per D8, so no component is ever written
  against a single-theme palette.
- Establish the frontend test stack, the 80 % coverage floor, and the missing-translation check, and join
  them to the existing `validate`/`test`/`coverage` stages (D11). Tests exist from the first component.

**Exit criterion.** `npm run build` produces the image served by the gateway, and a deliberate backend
contract change fails CI.

### M2 — Application shell

**Goal.** Everything every screen depends on, built once.

**Work.**

- Router with the nested project/snapshot/run/aggregation structure from
  [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md).
- Session handling against `GET /me` and `GET /auth/session`: login with a "keep me signed in" checkbox
  (unchecked by default), logout, role-aware hiding and disabling, and the forced password change (D1).
  Project controls follow `current_user_role` on the current project; only project creation and membership
  administration follow the global roles on `GET /me` (D6).
  **Partly delivered.** `useSessionStore` (Pinia; session and roles are exactly the "genuinely shared client
  state" docs/26-frontend-coding-guidelines.md assigns there) resolves the session once at app start,
  and `/login` and `/change-password` cover login with "keep me signed in", the forced-password-change
  gate and its own view, and logout — verified against a real Chrome instance over the DevTools Protocol,
  including that the backend's `Secure`-flagged cookies are in fact accepted and sent back over plain
  `http://localhost` (Chrome's documented allowance for that origin) and that the session survives a full
  page reload. `initialize()` also distinguishes an ordinary `401` (not signed in) from any other failure —
  a `5xx`, a network error, an unparseable response — as its own `error` status, so a genuine server problem
  at boot renders as one rather than as a misleading "please sign in" (see the M2 exit criterion below).
  Role-aware hiding and `current_user_role`-scoped project controls remain open: there is no
  project-scoped screen yet for them to apply to. The separate ADR-0039 administrative increment now
  delivers the corresponding global-admin read path: `/admin/users` waits for session initialization, is
  available only to a password-current global administrator, and keeps a signed-in non-administrator in an
  explicit permission state. Its TanStack Query pages are scoped to the principal and server-side search
  tuple, and are cancelled and removed on access loss. Account creation, mutation, reset, revocation, and
  membership screens remain pending.
- Recovery from a `401` at any moment: keep the unsent decision, offer an inline sign-in, and retry the
  request rather than redirecting away and losing the user's place (D1). **Delivered.** The API client takes
  an `onUnauthorized(request)` hook (`src/api/client.ts`); on a `401` it clones the request up front (so a
  body can still be retried after it has been sent once), awaits the hook, and — if the hook resolves —
  retries with a freshly read CSRF token, since the session that produced the stale one is gone. The shell's
  hook (`src/app/sessionGuard.ts`) opens a single inline prompt (`SessionRecoveryDialog`, the first Dialog
  built on D9) shared by every request that 401s around the same moment; signing in again there retries the
  original request without navigating away, and declining falls back to exactly `docs/26`'s rule — the
  session is cleared locally and the client routes to `/login`, preserving the page as `?redirect=`. It
  ignores `POST /auth/login`/`POST /auth/logout` (each already handles its own failures) and any `401` from
  before the session is known to be signed in (the ordinary anonymous state at boot), so a view's own guard
  still handles those. The username/password/submission logic itself was pulled out of `LoginView` into
  `useLoginForm`, shared by the full-page form and the recovery prompt.
- The eight cross-cutting concerns listed in that document: error envelope, `409` recovery, `413` limits,
  async `202`-poll composable, SSE composable, cursor pagination, roles, CSRF. The error envelope, CSRF, and
  now the `401` case above are delivered; the rest wait for a real consumer (an upload, a run, a list) rather
  than being built speculatively.
- Design tokens, typography scale, and the primitive components — with real `<button>`/`<a>` elements,
  focus management, and a focus trap for modals. The wireframe's `role="button"` keyboard shim is not
  carried over. **Partly delivered**: `AppButton`, `AppTextField`, `AppListbox`, and now a Dialog
  (`SessionRecoveryDialog`) with a real focus trap exist; no other modal has needed one yet.
- Locale switch and theme switch (system, light, dark), and the shared vocabulary components that render
  `CanonicalLabel`, `CertaintyTier`, and `AgreementTier` as canonical token plus translated gloss (D2, D3).
  **Partly delivered.** The locale and theme switches are live in `AppHeader` on every screen
  (`useLocale`, `useTheme`, both built on `AppListbox`); the vocabulary components remain open until a
  screen exists that renders canonical labels or tiers.
- Overlay primitives on the chosen headless accessibility library (D9); everything else in-house.
  **Partly delivered.** `AppListbox` (the header's switchers) and `Dialog` (`SessionRecoveryDialog`, see
  the `401` recovery item below) are built; a Menu remains open until something needs one.
- The publication footer on every page, the start-page publication details, and the public legal notice
  required by the operating institution's guideline for digital publications, as specified in
  [`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md#publication-details-footer-and-legal-notice).
  **Delivered.** `useBranding()` fetches `GET /api/v1/branding` (no branding fact is a frontend
  constant except the source-code licence, which is the same for every deployment) and each field the
  operator has not configured renders as an explicit "not configured" state rather than inventing one. The
  legal notice route (`/impressum`) is exempt from the session guard and reachable without signing in, and
  its loading/error states include a retry affordance since branding is that page's own content. A minimal
  `vue-router` (history mode, decision D13) was pulled forward from the rest of M2 to route to it. The
  earlier hard-coded draft on branch `wip/publication-footer-legal-notice` was discarded rather than
  merged.
- The backend prerequisite for the item above: `GET /api/v1/branding` and `GET /api/v1/branding/logo`
  ([ADR-0036](decisions/ADR-0036-institution-branding-configuration.md)). **Delivered**, unauthenticated and
  needing no grant, both registered in the route-coverage check in `backend/tests/api/test_authorization.py`.

**Exit criterion.** A viewer, reviewer, and operator each see a correctly scoped shell in both locales and
both themes; an expired session and a server error both render correctly. **Met**, for what M2 itself
builds: `useSessionStore`'s boot check (`GET /me`) now distinguishes an ordinary `401` (not signed in — the
existing shell renders normally) from anything else — a `5xx`, a network failure, an unparseable response —
which is a genuine failure and gets its own `error` status. `AppHeader` shows it as a visible message with a
retry, instead of a misleading "sign in" prompt when the real problem is the server; `/change-password`
shows the analogous load-error-and-retry state instead of "Loading …" forever. Viewer/reviewer/operator
role-scoping itself has nothing to show yet — there is no project-scoped screen in the shell for a role to
scope — so that part of the criterion is necessarily verified once M3 exists, not before it.

### Administrative local-account directory — ADR-0039

**Status.** Delivered as the first frontend administrative increment. `/admin/users` is a read-only,
global-admin screen backed by the generated `GET /api/v1/admin/users` client. It presents server-ordered
accounts with username/display-name search, opaque cursor pagination, account state, required-password-change
state, global roles, and a current-account marker. The route and sidebar both wait for the session result;
the screen retains its clear signed-in non-admin, signed-out, password-change, session-error, retry, empty,
search-empty, initial-error, pagination-error, and refetch states. Private administrative query data is
principal-scoped and removed on a principal or eligibility change and when the view unmounts.

Creation, updates, password resets, session revocation, project memberships, settings forms, and branding
consumers are subsequent administrative slices. ADR-0040 permits frontend edits only for its six branding
fields; this increment does not add those controls.


### M3 — Projects and import

**Goal.** The first write path, and the first real provenance surface.

**Work.**

- Project list and switcher from `GET /projects`, which returns only the caller's projects with the caller's
  role in each; project creation including `slug` and `description`, offered to global operators (D6).
  **Partly delivered.** `ProjectListView` lists and creates projects, cursor-paginated through the shell's
  first use of a query cache (`@tanstack/vue-query`, decision noted in `frontend/README.md`); a signed-out
  visitor is redirected to `/login` and a genuine server error gets its own state, matching the pattern
  from M2's exit criterion. Also delivered: the sidebar layout from `docs/25` (`AppSidebar`), previously
  outstanding from M2 and folded in here since M3 is what first needs cross-screen navigation. Not yet
  built: the project switcher (nothing to switch between screens yet) and the nested
  `/projects/:projectId/...` routes, added as their own screens land.
- `ProjectOverviewView` (`/projects/:projectId/overview`). **Delivered**, deliberately minimal: name, slug,
  role, description, and a link to import — the wireframe's KPI dashboard is not attempted here, since it
  reads `GET /aggregations/{id}/review-summary`, which needs a run and an aggregation that cannot exist
  before M4.
- Import with the full `source_format` × `packaging` matrix; the backend derives the import profile.
  **Delivered.** `ImportView` uploads to `POST /projects/{project_id}/snapshots`, gated to the project's
  own operators (`current_user_role`, not the global roles D6 gives project creation), for every
  combination the backend accepts: TEI as a `single` file, several `loose` files (repeated `source` parts),
  a `zip`, or a `tar_gz`; CSV, XLSX, and JSON only as `single` (the backend rejects anything else, so the
  delivery choice is not offered for them, and changing format or delivery drops a now-invalid file
  selection). The wireframe's GitLab source is a v1 scope exclusion (see below), not part of this matrix.
- The asynchronous snapshot lifecycle: `202` → poll → ready or failed, with `failure_diagnostic` surfaced.
  **Delivered**, and, per docs/23's cross-cutting-concerns table, as the general composable that
  aggregations/evaluations/exports will reuse: `composables/usePolledQuery.ts` wraps `useQuery` with a
  `refetchInterval` that stops once a caller-supplied `isTerminal` predicate is met.
- Upload limits shown before upload and on `413`. **Delivered.** `GET /snapshot-upload-limits` is read
  before anything is chosen and shown in the form (per-file and total bytes; for loose and archive
  deliveries also the member count and expanded-size bound), tied to the file input with
  `aria-describedby`. A selection over either bound is refused with an alert and the submit stays disabled;
  the server still enforces the bounds, and a `413` still maps to an inline message. If the limits cannot be
  loaded the form says so and does not block. Found in the first real-backend run: a ZIP sent under the
  default "single file" delivery is read as XML and only fails after the snapshot exists (`invalid TEI XML at
  line 1, column 1`), so the form also compares the file name with the chosen delivery (`.zip`,
  `.tar.gz`/`.tgz`) and refuses a mismatch before uploading. The server stays authoritative.
  The same run showed that CSV, XLSX and JSON share one fixed profile (`docs/08-ingestion-and-export.md`) that
  the form never named, and that the backend's `unknown columns` diagnostic does not list the expected ones.
  For the tabular formats the form therefore states the seven required columns (and that `persName`, `event`,
  `idno` are JSON arrays), and for CSV it reads the first line of the chosen file and refuses a header that is
  not exactly that list, naming expected and found columns. XLSX and JSON cannot be checked without parsing
  them, so they are left to the server; its diagnostic is shown on the snapshot list and the import screen.
- Snapshot provenance: `source_sha256`, `parser_version`, per-member manifest entries. **Delivered.** The
  project overview lists the project's snapshots (`GET /projects/{id}/snapshots`, newest first, cursor-paginated,
  every lifecycle state) with status, record count, parser version, and the full SHA-256; a disclosure per
  snapshot fetches `GET /snapshots/{id}/source-members` on demand and shows each source file's name, media
  type, size, and checksum. The import screen's `ready` state shows the checksum and links back to the list.

**Exit criterion.** An operator imports a TEI ZIP and a CSV through the browser and sees both snapshots
reach `ready` with their checksums. **Met** in the frontend: both formats can be imported and their
checksums read back on the project overview. It was verified against the mocked contract and then, on
2026-09-23, in the browser against the real API and worker (Docker Compose development stack): a two-file TEI ZIP
and a CSV of 8,277 persons both reached `ready`. That run found one frontend gap (an archive sent under the
default single-file delivery, see the upload-limits item) and showed that the repository's sample
`data/input/schleiermacher_persons.csv` is not in the CSV profile of `docs/08-ingestion-and-export.md`.

### M4 — Runs and aggregation

**Goal.** The pipeline the wireframe omits, made explicit and observable.

**Work.**

- Method roster from `GET /methods`, not a hardcoded list; per-method configuration forms driven by the
  registry contract.
- Run creation, scheduling, and live progress over SSE with reconnect-and-refetch.
- Per-execution failure surface: `failed_count`, `failure_class`, `failure_diagnostic`.
- Run and method provenance display — the reproducibility story from
  [`11-provenance-and-reproducibility.md`](11-provenance-and-reproducibility.md).
- **Aggregation as a first-class step**, per D4: automatic default `reference_v1` aggregation on run
  completion, an explicit advanced path, and a listing that makes re-aggregation without re-running
  methods a cheap, visible action.

**Delivery status (2026-09-24).**

- Method roster from `GET /methods`. **Delivered.** `features/runs/useMethods.ts`; the new-run form lists exactly
  what the server returns, with each method's implementation version and, where the method reports one, its own
  confidence range (stated as method-specific, never comparable across methods).
- Run creation and scheduling. **Delivered.** `/projects/:projectId/snapshots/:snapshotId/runs` (`RunListView`)
  lists the snapshot's runs newest first (`GET /snapshots/{id}/runs`, cursor-paginated) and, for project operators,
  starts a run: `POST /runs` then `POST /runs/{id}/executions` as one action. If scheduling fails the run stays
  `created` in the list. `execution.fail_run_on_optional_method_error` is exposed. Reached from every `ready`
  snapshot on the project overview. Verified against the real API and worker: a two-method run over four persons
  reached `completed` within seconds.
- **Gap (backend contract): no configuration schema.** `RunConfig.methods[].config` is an opaque object that only the
  server-side registry validates, and `MethodDescriptor` carries no schema. Seven of the ten methods reject an empty
  configuration (probed on 2026-09-24: only `parenthetical_qualifier`, `gender_guesser` and `nomquamgender`
  accept `{}`). Lookup methods (`gnd`, `wiki_gendersort`, `hivoto`, `hivoto_xgboost`, `hf_distilbert`,
  `hf_genderize`) require `lookup_sha256`, the digest of a compiled lookup artifact, and `local_llm` requires
  `model` and `base_url`. The form therefore offers a JSON text field per selected method, validated only as a JSON
  object client-side; the server's `422` is shown. Typed per-method forms need the contract to expose each method's
  configuration schema.
- **Gap (backend contract): no way to discover lookup artifacts.** Nothing lists the compiled lookup artifacts
  (or their digests) an operator could choose, so `lookup_sha256` has to be known out of band. A read-only
  listing, and `LLM_BASE_URL` as the default for `local_llm.base_url` (AGENTS.md rule 15), would remove this.
- Live progress and the per-execution failure surface. **Delivered.**
  `/projects/:projectId/snapshots/:snapshotId/runs/:runId` (`RunDetailView`) shows the run's status, an overall
  bar and each method execution with its own bar, counts, `failure_class` and `failure_diagnostic`. Starting a run
  opens this screen. `features/runs/useRunProgress.ts` is the one SSE composable: it writes into the same query
  cache the run and execution queries read, patching counts from `*.progress` events and refetching on state
  changes and terminal events. The server keeps no event log (no `Last-Event-ID`), so **every re-connection
  refetches**; a stream the server ends (terminal state, or its five-minute limit) is re-opened by the browser, and
  a refused request (`CLOSED`, e.g. an expired session) is retried with backoff after a refetch through the API
  client, which is where an expired session is recovered. A finished run opens no stream. Percentages are the
  server's, never recomputed. The connection state ("live", "reconnecting") sits in a status region.
- **Gap (backend contract): the event payloads are not in OpenAPI.** `GET /runs/{id}/events` is an untyped `200`,
  so the six event types (`run.state_changed`, `run.progress`, `method_execution.state_changed`,
  `method_execution.progress`, `run.completed`, `run.failed`) are declared by hand in `useRunProgress.ts` from
  `api/routes/run_events.py`, against AGENTS.md rule 17. A `text/event-stream` response schema per event (or a
  documented union) would let them be generated. Also: a `cancelled` run is not a terminal state for the stream,
  so it would stream until the five-minute limit.
- Aggregation as a first-class step (D4). **Delivered.** The run screen has an aggregations section
  (`GET /runs/{id}/aggregations`, newest first, re-reading itself while one is queued or running) and
  `/projects/:projectId/runs/:runId/aggregations/:aggregationId` (`AggregationDetailView`, polled to an end state)
  reads back the strategy, timestamps, configuration hash, resolved configuration and the exact selection by method
  name and version. When a run has finished successfully, a project operator's client creates the default
  `reference_v1` aggregation over every completed execution, in the order `GET /runs/{id}/executions` returns
  them, unless a queued, running or completed aggregation already exists. It runs once per run per visit and a
  failure (`409`) is shown, never swallowed or retried in a loop. The advanced form re-aggregates from a chosen
  subset without re-running any method; a `200` is reported as "an identical aggregation already exists" with a
  link (ADR-0034). Verified against the real API and worker on the seeded run: `202` queued, `completed` within
  seconds, an identical repeat answered `200`.
- **Constraint found (backend): `reference_v1` accepts only its complete method set.** Nine methods are required,
  each exactly once (`parenthetical_qualifier`, `gnd`, `gender_guesser`, `wiki_gendersort`, `hivoto`,
  `nomquamgender`, `hf_distilbert`, `hf_genderize`, `local_llm`), `hivoto_xgboost` is optional and ignored, and
  anything else is a `409` (ADR-0029). So "exclude a method and re-aggregate" (D4) is only possible for
  `hivoto_xgboost`, and a run of fewer methods can never be aggregated with the reference strategy. Together with
  the configuration gap above, a complete run needs a lookup artifact for six methods plus a model endpoint. The
  development stack has neither, so the automatic path was exercised on the seeded run only.
- **Gap (backend contract): the reference method set is not in the contract, and the `409` says nothing about
  why.** The client cannot tell which methods a strategy needs, and `details` is empty, so the message names the rule
  in general terms. A per-strategy required/optional method list on `AggregationStrategy` (or the `409` naming the
  missing methods, which the repository already computes) would let the form guide the selection.
- Run and method provenance. **Delivered.** The run screen has a provenance section (code commit, application and
  Python version, container image digest, dependency lock checksum and artifact, configuration hash, resolved
  configuration); a value that was not recorded says "Not recorded" rather than disappearing. Each method execution
  carries a disclosure with its implementation and normalization version, configuration hash, resolved configuration
  and, where it has them, model identifier, revision and checksum, prompt version and schema version
  ([`11-provenance-and-reproducibility.md`](11-provenance-and-reproducibility.md)). The aggregation screen shows the
  provenance of the run it was computed from, so the configuration hash and code provenance behind an aggregation
  are readable from the aggregation itself.

**Exit criterion.** An operator starts a run, watches it complete live, produces an aggregation, and can
read back the exact configuration hash and code provenance that produced it.

**Status of the exit criterion (2026-09-24).** Met in the frontend, in two parts that could not be exercised together on
the development stack. Starting a run and watching it complete over SSE was verified with the three methods that need
no configuration; producing an aggregation and reading back its hashes and code provenance was verified on the seeded
run, which holds all reference methods. A run of fewer methods cannot be aggregated with `reference_v1` at all (see
the constraint above), and a run of all of them needs six lookup artifacts and a model endpoint that this stack lacks.
The end-to-end path from a browser-started run to its aggregation therefore still needs an environment with those
artifacts, and the two contract gaps above (configuration schemas, lookup discovery) closed to be pleasant to use.

### M5 — Review workbench

**Goal.** The Phase 8 exit criterion.

**Work.**

- Three-column workbench driven by `GET /review-items` with the complete server-side filter set, both sort
  orders, and cursor pagination keyed to the filter tuple.
- Detail panel with per-method results, `override_source`, agreement and certainty tiers.
- Two distinct queue entry points per D2 — contested evidence (`low`, `contested`) and thin evidence
  (`single`, `uncertain`) — rather than one undifferentiated "below threshold" list.
- `verify`, `correct`, and `defer` actions with `comment`, keyboard shortcuts, and correct
  `expected_revision` handling.
- The `409 annotation_conflict` recovery flow as a designed interaction, not an error toast.
- Bulk selection as a client-side sequence with explicit partial-failure reporting.

**Exit criterion.** A reviewer corrects a machine result and the final-decision view changes without any
mutation of `Prediction` or `AggregatedResult` rows — the Phase 8 criterion from
[`15-implementation-plan.md`](15-implementation-plan.md), verified against a seeded snapshot.

### M6 — Person browser and audit view

**Goal.** Unrestricted register access and visible scholarly provenance.

**Work.**

- Reuse the workbench with `sort=tei_id` and the status/label filters, per decision D5.
- Detail rendering of the source-preserving fields: `name_forms`, `alt_names`, `events`, `external_ids`,
  `source_member_name`, `source_record_locator`.
- Annotation history view showing the superseding chain with reviewer attribution and timestamps.

**Exit criterion.** Any person in the register is reachable by search, and every past decision on that
person is visible with its author.

### M7 — Evaluation and statistics

**Goal.** Replace the wireframe's invented metrics with the real report.

**Work.**

- Evaluation creation as an asynchronous execution with status and report retrieval.
- Coverage, accuracy and effective accuracy, per-class recall with confidence intervals, confusion
  matrices, the pairwise Cohen's κ matrix, benchmark composition, and the ensemble tier distributions.
- Correct labelling of what each metric measures — see the Fleiss/Cohen conflict in
  [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md). Per D2 there is no cross-method mean
  confidence column.

**Exit criterion.** The published reference study's tables are reproducible from the browser against a
stored run.

### M8 — Export

**Goal.** Reproducible, provenanced output.

**Work.**

- Format selection including JSON, `label_source_policy`, `tei_profile`, and `human_resp_id`.
- Asynchronous export lifecycle and download.
- Manifest display: output checksums and the source snapshot hash.

**Exit criterion.** An operator produces a TEI export with human overrides applied and can verify its
checksum against the manifest.

### M9 — Optional paths and production build

**Goal.** Ship.

**Work.**

- Spielmodus as a presentation layer over the annotation contract, scoring deferred per D14 — the
  constraint from [`22-future-development.md`](22-future-development.md) holds: it must never influence
  which records are shown.
- Einstellungen reduced to whatever persistence exists, or read-only deployment facts.
- SPA routing fallback in the frontend image (D13), production build, same-origin smoke test through the
  gateway in both themes.
- Accessibility pass: keyboard paths, focus order, contrast against the token palette, screen-reader labels
  for the agreement indicators.

**Exit criterion.** The production Compose profile serves the built client through the gateway, deep links
resolve, and the review path works end to end behind a real session.

## Decisions taken

### D1 — Local accounts now, institutional SSO later

**Resolved as recommended and implemented.** The production provider is a local, database-backed account
system: admin-provisioned accounts, Argon2id password hashes, and server-side sessions that can be revoked.
Institutional OIDC/SSO remains a later, additive `AuthenticationBackend`; every backend terminates into the
same `CurrentUser`, so that swap stays contained. Recorded as
[ADR-0031](decisions/ADR-0031-local-database-authentication.md), with session lifetimes revised by
[ADR-0032](decisions/ADR-0032-sliding-session-lifetime.md).

**Consequences.**

- The client signs in with `POST /auth/login`, reads its principal from `GET /me`, and signs out with
  `POST /auth/logout`. The backend sets an HTTP-only `session` cookie and a readable `csrf_token` cookie,
  which the client mirrors into the `X-CSRF-Token` header on every unsafe request.
- Account provisioning and administration are available through the global-admin HTTP surface in
  [ADR-0039](decisions/ADR-0039-administer-local-accounts-over-http.md), which supersedes ADR-0031's
  CLI-only scope. The first client slice delivers only its read-only directory; there is neither
  self-registration nor email-based password recovery, and account mutations remain pending.
- A new or reset account must change its password first. `GET /auth/session` reports this right after login
  and on page load, and until `POST /me/password` succeeds, every endpoint except `GET /me`,
  `GET /auth/session`, `POST /auth/logout`, and `POST /me/password` returns
  `403 password_change_required`. The shell therefore needs a forced password-change view. A wrong current
  password is `400 invalid_current_password`; a `401` always means that the session is gone.
- The login form offers "keep me signed in", unchecked by default. Unchecked, the session uses
  browser-session cookies and ends after 24 hours without a request; checked, its cookies persist and the
  idle limit is 7 days. Use slides both limits forward, and every session ends 30 days after login.
- Every limit exceeds 20 hours, so session expiry falls under WCAG 2.2.1's 20-hour exception: the client
  shows no pre-expiry warning. It must still recover from a `401` without losing an unsent decision, since a
  session can also end through a logout elsewhere or an administrative password reset.

### D2 — Certainty and agreement tiers, not a confidence threshold

**Resolved from the paper** ([`paper/article.tex`](paper/article.tex), §Aggregation). The wireframe's
percentage threshold has no counterpart in the published method and is not implementable: *"The per-method
confidence values are recorded but do not influence the vote."* Aggregation is an unweighted majority vote
under a fixed authority priority chain, and decision quality is expressed categorically.

The UI adopts the paper's vocabulary verbatim. Certainty tiers:

| Tier | Condition |
|---|---|
| `high` | at least two methods voted and at least three quarters agreed, or an authority signal fired in agreement with the vote |
| `low` | at least two voted and a majority of half or more agreed |
| `contested` | at least two voted but agreement fell below half |
| `single` | only the LLM had usable output, with self-reported `high` confidence |
| `uncertain` | only the LLM had usable output, with `low` or `uncertain` self-reported confidence |
| `no_data` | no method could vote |

Agreement tiers are the share of answering methods that voted for the winning label: `unanimous`,
`strong_majority` (≥ 75 %), `weak_majority` (≥ 50 %), `no_consensus` (< 50 %), `single_rater`, `no_answer`.

**Consequences for the UI.**

- Replace the threshold slider on Import and the threshold row on Einstellungen. Automation is not tunable
  by the reviewer; it is a property of the aggregation strategy.
- Übersicht's "automatisch entschieden" tile becomes `certainty_tier = high`; "zur Prüfung" becomes the
  `review_triage_v1` ordering the backend already produces. Both tiles, and the badge on each queue entry
  point, add up groups of `GET /aggregations/{id}/review-summary` rather than counting pages, and the
  breakdown of where finished entries came from adds up the same response's `review_action` groups.
- The two review buckets are distinct and must not be merged: contested evidence (`low`, `contested`) and
  thin evidence (`single`, `uncertain`). On the case-study register these are 3.6 % and 12.7 % of entries
  respectively, against 83.8 % at `high` — so a queue built on "everything below a threshold" would be
  roughly four times the size of the genuinely contested set and would bury it. Each bucket is one
  `review-items` query, `certainty_tiers=low&certainty_tiers=contested` and
  `certainty_tiers=single&certainty_tiers=uncertain`, so its triage order and cursor come from the server.
- Per-method confidence may be displayed as method-specific provenance but must never be aggregated,
  averaged across methods, or used for ordering. This also removes the "Ø Konfidenz" column from the
  Statistik table.
- Triage is driven by disagreement, which the paper states is the intended signal: the entries on which the
  methods cannot agree *"concentrates exactly the cases where editorial attention is most warranted."*

No backend change and therefore no ADR: this aligns the UI with
[ADR-0009](decisions/ADR-0009-reference-agreement-certainty.md) and
[ADR-0022](decisions/ADR-0022-uncertainty-first-review-ordering.md) rather than altering them.

### D3 — English label vocabulary, bilingual interface

**Resolved.** The four canonical labels — `male`, `female`, `unknown`, `institution` — and the tier names
stay in English and untranslated in every locale. They are the controlled vocabulary written into the TEI
output, reported in the paper, and returned by the API; translating them in the UI would create a second
vocabulary for the same scientific values.

The interface chrome is internationalised in **German and English from M1**, not retrofitted.

**Consequences.**

- i18n is a scaffold-time concern: message catalogues, a locale switch, locale-aware dates and numbers, and
  a lint rule against hard-coded user-facing strings all land in M1/M2 rather than after the screens exist.
- Canonical values render as their token plus a translated gloss where a gloss helps — for example
  `unknown` with "nicht bestimmbar" / "not determinable", `uncertain` with "nur LLM, geringe Sicherheit" /
  "LLM only, low confidence".
- This dissolves the `uncertain`/`unknown` collision from
  [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md). The paper explicitly warns against
  conflating them: `uncertain` *"identifies entries where only the LLM responded and did so with low
  confidence, not a vote-level output category."* The wireframe's fourth action button is therefore
  relabelled `unknown`.
- The action bar becomes `male` / `female` / `unknown` / `institution`, matching the vote alphabet exactly.
- Locale coverage belongs in the test strategy (D11): a missing-translation check, and at least one
  end-to-end path per locale.

Recorded as [ADR-0030](decisions/ADR-0030-bilingual-client-with-untranslated-canonical-vocabulary.md), since it
fixes a durable client-boundary rule alongside [ADR-0006](decisions/ADR-0006-vue-browser-client-boundary.md).

### D4 — Aggregation is created automatically, with an explicit advanced path

**Resolved as recommended.** When a run reaches a terminal successful state, the client creates a default
`reference_v1` aggregation over all completed method executions. Explicit aggregation — choosing a strategy
and an exact subset of executions — remains available as an advanced action.

**Consequences.**

- The route keeps the aggregation identifier
  (`/runs/:runId/aggregations/:aggregationId/...`). The model stays visible and shareable; only the common
  path is shortened.
- Re-aggregation is a first-class action, not a hidden one. The paper treats it as a design benefit:
  methods are kept independent so *"slow methods need only run once before being re-aggregated freely."*
  Excluding a method and re-aggregating without re-running the LLM is exactly the workflow the UI should
  make cheap.
- Multiple aggregations per run must therefore be listable and comparable, and the UI must always show
  which aggregation the current review queue and export belong to. `GET /runs/{id}/aggregations` lists
  them newest first.
- Auto-creation must be idempotent and must fail visibly, not silently, when the execution set is not
  aggregatable — `POST /runs/{id}/aggregations` returns `409` in that case. The server makes it idempotent
  ([ADR-0034](decisions/ADR-0034-reuse-matching-aggregation-on-creation.md)): repeating the request returns
  the existing queued, running, or completed aggregation with `200` instead of `202`, and only a failed or
  cancelled one leads to a fresh attempt. The client therefore sends the executions in a stable order, the
  one `GET /runs/{id}/executions` returns, and may repeat the request after every reload.

### D5 — `review-items` is the person-browser data source

**Resolved.** “Manuell annotieren” uses `GET /review-items` with the route's aggregation ID and
`sort=tei_id`. It reuses the same workbench and server-side `q`, review-state, label, certainty-tier, and
agreement-tier filters as “Redigieren”; only the default sort and entry context differ.

Browsing therefore requires a completed aggregation. That is intentional: a completed aggregation has one
result for every person in its immutable snapshot and supplies the final decision, current review state, and
review revision the annotation workbench needs. The aggregation already appears in the route, so the client
does not infer one from global state.

`GET /snapshots/{snapshot_id}/people` remains the stable raw-register collection, not a parallel search and
filter API. `GET /snapshots/{snapshot_id}/people/{tei_id}` supports direct detail reloads and source-rich
provenance views after a person has been selected. No duplicate query semantics are added to the snapshot
people collection.

**Consequences.**

- M6 is a second configuration of the M5 cursor/query composable, keyed by the complete filter tuple with
  `sort=tei_id`; it does not need another backend collection.
- Search and filter behavior cannot drift between “Redigieren” and “Manuell annotieren.”
- Deep links retain the run and aggregation context required for predictions, final decisions, annotations,
  and conflict recovery.

### D6 — Project visibility and role scope

**Resolved and implemented: project-scoped membership roles.** Recorded as
[ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md). Team membership is per project, as the
wireframe states. Viewer, reviewer, and operator are project roles held through memberships; only two global
roles remain — `operator`, which may create projects and becomes operator of each one it creates, and
`admin`, which holds operator in every project and administers memberships.

**Consequences.**

- `GET /projects` lists only the projects where the caller has a role, cursor-paginated in slug order. Every
  project representation carries `current_user_role`, the caller's effective role, which the shell uses to
  scope controls for the current project.
- A resource in a project the caller does not belong to returns `404`, exactly like one that does not exist;
  a member below a route's least role receives `403`. The client treats both as it already treats missing
  resources and forbidden actions.
- Memberships are managed by administrators through admin-only `/projects/{project_id}/members` endpoints
  and the `gendertagger projects` CLI. `GET /admin/users` has a delivered read-only administrator screen
  under [ADR-0039](decisions/ADR-0039-administer-local-accounts-over-http.md); membership editing remains a
  subsequent frontend slice.
- The upgrade drops the global viewer and reviewer roles and assigns no memberships, so every deployment
  must assign project memberships after migrating.

### Architectural decisions

All resolved. They are binding on
[`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md) and
[`26-frontend-coding-guidelines.md`](26-frontend-coding-guidelines.md).

**D7 — Sidebar only.** The wireframe's second navigation row is dropped. One navigation surface, one current
location.

**D8 — Dark mode ships.** Both themes are built from the first milestone rather than retrofitted. Tokens
become semantic and theme-scoped, both palettes are contrast-verified, and the theme follows
`prefers-color-scheme` with an explicit user override. The verified dark palette is in
[`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md).

**D9 — A small headless accessibility library for overlay primitives.** Menus, modals, listboxes, and
tooltips use it; everything else is built in-house on the project tokens. The library is chosen for
unstyled behavior and focus management only — it brings no visual opinion and no design system.

**Resolved: `@headlessui/vue`.** Considered against Reka UI and Ark UI (Vue), which cover all four named
primitives in one package; Headless UI Vue was chosen anyway and has been stalled at v1.7.23 for some time,
behind its React sibling. It covers Menu, Dialog (modal), and Listbox, but ships no Tooltip primitive.
**Tooltips are therefore hand-rolled in-house** on the project tokens, following the WAI-ARIA APG tooltip
pattern (`aria-describedby` to a `role="tooltip"` element, shown on hover and focus, dismissed on `Escape`
or blur) — the same "everything else in-house" treatment D9 already gives anything the chosen library
doesn't cover. Decision D9 still admits exactly one behavioural dependency; a second library for tooltips
alone (for example `@floating-ui/vue`, positioning only) is not added. `@headlessui/vue` also pulls in
`@tanstack/vue-virtual` as its own dependency, for virtualized Listbox/Combobox rendering; both carry the
MIT licence.

**D10 — Charts are hand-rolled SVG.** Distribution bars, the κ matrix, and confusion matrices are built
against the tokens. Revisit only if a chart requirement appears that SVG plus the existing components
genuinely cannot serve.

**D11 — Testing from the first commit, in CI, with an 80 % coverage floor.** The frontend suite joins the
existing `validate`/`test`/`coverage` stages rather than arriving later. Layers, rules, and the floor are
specified in [`26-frontend-coding-guidelines.md`](26-frontend-coding-guidelines.md). The floor is ratcheted
upward, never gamed, matching the backend policy in
[`18-engineering-and-quality.md`](18-engineering-and-quality.md).

**D12 — Node 26, pinned; client dependencies in `frontend/`.** `frontend/package.json` and
`frontend/package-lock.json` own the client tree; the root `package.json` stays the Pyright-only manifest.
CI installs with `npm ci`, and the existing `lockfile` and `dependency_audit` jobs extend to cover it.
Node 26 replaced the original Node 22 pin: Node 22 is in maintenance and reaches end of life in April 2027,
while Node 26 enters LTS in October 2026 and is supported until April 2029. Every locked dependency supports
it.

**D13 — History-mode routing.** The SPA fallback is added to the frontend nginx image. Hash routing is
rejected because scholarly URLs are shared and cited.

**D14 — The game mode ships in v1, without scoring.** It is a presentation layer over the same annotation
contract. Scores, combos, streaks, and the leaderboard are deferred, and the constraint from
[`22-future-development.md`](22-future-development.md) holds regardless: nothing in the game path may
influence which records are shown for review.

### Accessibility decisions

**D15 — Conformance target is WCAG 2.2 AA.** The client is built to WCAG 2.2 AA, which satisfies every
regime that could apply to a jointly maintained Berlin/Brandenburg public-law body, so implementation does
not wait on the legal question.

One administrative item remains and is **not** settled by this decision: whether a published accessibility
statement, a feedback mechanism, and a named enforcement path are legally mandatory here, and who signs the
statement off. That is a deliverable question rather than a build-target question, it cannot be answered
from inside the repository, and it is tracked in [Outstanding assignments](#outstanding-assignments).

**D16 — Internal self-assessment only.** No external examination is commissioned. Self-declaration is an
accepted basis under EN 301 549, but the rigour then has to come from the process rather than from an
external report: the test protocol is written down, every pass is recorded with date, scope, and findings,
and the evidence accumulates across milestones instead of being reconstructed at the end. Without an
external check, D17 and D18 carry the whole weight of the assessment.

**D17 — Test matrix.** Required on every screen:

| Layer | Scope |
|---|---|
| Automated | `axe-core` in component tests; linter accessibility ruleset; contrast assertions in both themes |
| Keyboard | Full pass on every screen, both themes, both locales — no pointer used |
| Screen reader | NVDA with Firefox, and VoiceOver with Safari |
| Zoom and reflow | 400 % zoom / 320 CSS px width; text-spacing overrides applied |

JAWS with Chrome is added only if the institutional user base requires it; that is a question for the
accessibility owner once the user base is known. Automated coverage alone is explicitly not a test strategy.

**D18 — One named owner, and users involved once.** A single named person owns accessibility for the client:
they maintain the test protocol, sign off the per-milestone criteria, and hold the evidence that the
declaration would rest on. The person is still to be appointed — see
[Outstanding assignments](#outstanding-assignments).

At least one round of testing with people with disabilities takes place before M9. With no external audit
(D16), this is the only point at which the assessment is exposed to users who are not its authors, so it is
scheduled rather than left to goodwill.

**D19 — The game-mode timer is switchable off.** The countdown may exist, but the user can disable it, the
setting is reachable **before the first timed round begins**, and the choice persists. Disabling the timer
must not degrade the annotation path: the same records, the same actions, the same writes. This satisfies
WCAG 2.2.1 through its "turn off" provision.

## Outstanding assignments

Not decisions, but named tasks that can only be discharged outside the repository. The two accessibility
tasks gate M0; the other two gate what each names:

- confirm whether a published accessibility statement and feedback mechanism are legally required, and who
  signs the statement off (follows from D15);
- appoint the accessibility owner (follows from D18);
- have the BBAW administration confirm the provider details and the wording of the legal notice, and the
  data protection officer decide whether the application needs a privacy statement of its own, given the
  session and CSRF cookies of [ADR-0031](decisions/ADR-0031-local-database-authentication.md). Both gate any
  public deployment of this instance;
- set this deployment's `GENDERTAGGER_BRANDING__*` settings once [ADR-0036](decisions/ADR-0036-institution-branding-configuration.md)
  is implemented, and mount the publisher's logo file at the configured `branding.logo_path`. Confirm the
  list of editors and the publication period shown on the start page. These gate the M2 footer showing
  correct content, though the footer itself renders correctly without them, as an unconfigured state.

### Scope exclusions to confirm

Recommend recording these as explicitly out of scope for v1, so the wireframe does not create silent
expectations. Each is analysed in [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md).

- GitLab repository binding, synchronisation, and commit export
- Notifications and the activity feed
- Autosave and "last saved" state, which contradict append-only annotations
- Persisted user and project settings
- Game scoring, combos, and the leaderboard
- A bulk annotation endpoint
- Per-case review-time telemetry

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| No real authentication provider | Client cannot ship regardless of its completeness | Resolved by D1: the local account backend (ADR-0031) is implemented and is the default |
| Aggregation is invisible in the accepted design | Users expect review immediately after classification | Resolved by D4: auto-create the default aggregation, keep the step legible in the route and the UI |
| D6 left open while `GET /projects` is implemented | Narrowing the response later is a breaking contract change | Resolved by D6: `GET /projects` shipped with its final visibility rule (ADR-0033) |
| The membership upgrade removes non-admin access | Users see no projects until an administrator assigns memberships | Plan membership assignment with `gendertagger projects add-member` as part of each deployment's upgrade |
| Tier vocabulary is unfamiliar to reviewers | Six certainty tiers replace one intuitive percentage | Glosses per D3, and two clearly separated queue entry points rather than six raw filters |
| Wireframe promises unbuilt features | Stakeholder expectation gap at delivery | Confirm the scope exclusions in writing at M0 |
| Frontend dependency tree meets a provenance-strict repository | SBOM and licence review friction late in delivery | Resolved: D9 sets the dependency budget at one library, `@headlessui/vue` (MIT), justified in `frontend/README.md` |
| No UI-level acceptance coverage | Scientific fixtures pass while the review path is broken | Define the seeded-snapshot acceptance test as part of D11 |
| Accessibility deferred to a closing phase | Legal exposure plus structural rework; the wireframe's controls are unusable as drawn | Per-milestone criteria above; automated checks from M1 |
| Internal-only assessment misses defects (D16) | No external check before release | The D17 matrix is mandatory, not advisory, and the D18 user round is scheduled rather than optional |
| Game-mode timer conflicts with WCAG 2.2.1 | A shipped feature that cannot be made conformant | Resolved by D19: the timer is switchable off before the first round |
| Unconfirmed legal notice goes public | Wrong provider, representative, or tax details in a legally binding statement | Its confirmation is an outstanding assignment that gates public deployment, and production promotion stays manual |

## Immediate next steps

1. Confirm the v1 scope exclusions with the stakeholders who reviewed the wireframe, and confirm with them
   that the threshold control is removed rather than redesigned (D2) — this is the most visible change
   against the accepted wireframe.
2. Appoint the accessibility owner and confirm whether an accessibility statement is legally required.
   Both are organisational, both gate M0, and neither is resolvable from inside the repository.
3. Begin M2 in parallel with items 1–2. Its hard dependencies, M1 and a working authentication backend, are
   both in place; its overlay primitives still need the headless accessibility library chosen (D9).
