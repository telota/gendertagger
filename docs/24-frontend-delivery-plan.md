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

Phase 8's backend prerequisites are met. Of the three practical preconditions for the client, two are met and
one is partly met.

| Precondition | State | Blocks |
|---|---|---|
| A real `AuthenticationBackend` | **Met.** `DatabaseAuthenticationBackend` is the default: admin-provisioned local accounts and server-side sessions ([ADR-0031](decisions/ADR-0031-local-database-authentication.md)). | — |
| Three missing read endpoints | **Met.** `GET /projects` ([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)), `GET /aggregations/{id}/results/{result_id}/predictions`, and `GET /annotations?snapshot_id=&tei_id=` are delivered. | — |
| Collections to navigate by | **Met.** `GET /projects/{id}/snapshots`, `GET /snapshots/{id}/runs`, and `GET /runs/{id}/aggregations`, `/evaluations`, and `/exports` list their resources newest first, so the routes can recover the identifiers they carry. | — |
| Blocking semantic decisions | **Partly taken.** D1–D4 and D6 resolved; D5 deliberately open. See [Decisions](#decisions-taken). | Manuell annotieren (D5) |

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
  `npm run build` from `frontend/package.json` and its lockfile, separate from the root `package.json`,
  which exists only for Pyright. Node is pinned by version and digest and agrees with `engines`.
- The production stage serves the build with a history-mode fallback
  ([`frontend/nginx/default.conf`](../frontend/nginx/default.conf)), decision D13.
- The `development` stage installs dependencies and starts the Vite server. `npm run dev` on the host,
  proxying `/api/v1` to `http://localhost:8000`, is the working hot-reload path.
- The image job built its context from the repository root, which cannot see `frontend/package.json` as a
  top-level file. `.kaniko_build` now takes an `IMAGE_CONTEXT` per image, and the frontend uses `frontend/`,
  matching `compose.dev.yaml`.

**Still needed.**

- `compose.dev.yaml` still builds the `production` target, so there is no hot reload inside Compose. Switching
  it to the `development` target with a bind mount is left until someone needs it.
- `frontend_sbom` now produces a real dependency tree. The repository's provenance and licence culture applies
  to npm packages too: the M1 dependencies are justified in [`frontend/README.md`](../frontend/README.md), and
  the headless accessibility library still has to be chosen — see decision D9.

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
| M2 | Application shell | M | M1; a working auth backend |
| M3 | Projects and import | M | M2 |
| M4 | Runs and aggregation | L | M3 |
| M5 | Review workbench | L | M4 |
| M6 | Person browser and audit view | M | M5; **D5 (open)** |
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

- D1, D2, D3, D4, and D6 are resolved. D3 is recorded as
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
  `tests/fixtures/openapi-v1.json`, which the backend contract test already keeps equal to the live schema,
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
- Recovery from a `401` at any moment: keep the unsent decision, offer an inline sign-in, and retry the
  request rather than redirecting away and losing the user's place (D1). The login form handles its own
  failures, `401 invalid_credentials` and the gateway's `429 rate_limited` with its `Retry-After`, so the
  global `401` recovery ignores `POST /auth/login`.
- The eight cross-cutting concerns listed in that document: error envelope, `409` recovery, `413` limits,
  async `202`-poll composable, SSE composable, cursor pagination, roles, CSRF.
- Design tokens, typography scale, and the primitive components — with real `<button>`/`<a>` elements,
  focus management, and a focus trap for modals. The wireframe's `role="button"` keyboard shim is not
  carried over.
- Locale switch and theme switch (system, light, dark), and the shared vocabulary components that render
  `CanonicalLabel`, `CertaintyTier`, and `AgreementTier` as canonical token plus translated gloss (D2, D3).
- Overlay primitives on the chosen headless accessibility library (D9); everything else in-house.
- The publication footer on every page, the start-page publication details, and the public legal notice
  required by the BBAW guideline for digital publications, as specified in
  [`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md#publication-details-footer-and-legal-notice).
  The legal notice route stays exempt from the session guard, so it is reachable without signing in.

**Exit criterion.** A viewer, reviewer, and operator each see a correctly scoped shell in both locales and
both themes; an expired session and a server error both render correctly.

### M3 — Projects and import

**Goal.** The first write path, and the first real provenance surface.

**Work.**

- Project list and switcher from `GET /projects`, which returns only the caller's projects with the caller's
  role in each; project creation including `slug` and `description`, offered to global operators (D6).
- Import with the full `source_format` × `packaging` matrix and explicit profile selection.
- The asynchronous snapshot lifecycle: `202` → poll → ready or failed, with `failure_diagnostic` surfaced.
- Upload limits shown before upload and on `413`.
- Snapshot provenance: `source_sha256`, `parser_version`, per-member manifest entries.

**Exit criterion.** An operator imports a TEI ZIP and a CSV through the browser and sees both snapshots
reach `ready` with their checksums.

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

**Exit criterion.** An operator starts a run, watches it complete live, produces an aggregation, and can
read back the exact configuration hash and code provenance that produced it.

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
- Accounts are created by an administrator with `gendertagger users create`. No screen manages users, and
  there is neither self-registration nor email-based password recovery.
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
  and the `gendertagger projects` CLI. No v1 screen manages them; an administrator screen would first need a
  user directory ([`22-future-development.md`](22-future-development.md)).
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

## Decisions still open

One decision remains, D5, deliberately deferred, plus four administrative assignments. D1 and D6 are
resolved — see [ADR-0031](decisions/ADR-0031-local-database-authentication.md) and
[ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md). What follows is what each costs and when
it must be answered.

### D5 — Data source for "Manuell annotieren"

`GET /snapshots/{id}/people` has no filters and no free-text search; `GET /review-items` has both but
requires a completed aggregation.

**Blocks M6 only.** The cost of deferring is low: M5 builds the shared workbench against `review-items`
regardless, so M6 is a second binding of an existing component. Decide before M6 starts.

**What changes with the answer.** Choosing `review-items` means browsing the register requires a completed
aggregation, and the screen inherits the full filter set for free. Choosing `snapshots/people` keeps
browsing independent of any run but requires new server-side filter and search support on that endpoint —
a backend change that would need to be scheduled.

### Outstanding assignments

Not decisions, but named tasks that can only be discharged outside the repository. The two accessibility
tasks gate M0; the other two gate what each names:

- confirm whether a published accessibility statement and feedback mechanism are legally required, and who
  signs the statement off (follows from D15);
- appoint the accessibility owner (follows from D18);
- have the BBAW administration confirm the provider details and the wording of the legal notice, and the
  data protection officer decide whether the application needs a privacy statement of its own, given the
  session and CSRF cookies of [ADR-0031](decisions/ADR-0031-local-database-authentication.md). Both gate any
  public deployment;
- supply the publisher's logo files, and confirm the list of editors and the publication period shown on the
  start page. These gate the M2 footer.

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
| Frontend dependency tree meets a provenance-strict repository | SBOM and licence review friction late in delivery | Set the dependency budget (D9) before M2 |
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
