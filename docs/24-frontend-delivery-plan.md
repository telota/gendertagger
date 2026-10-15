# Frontend delivery plan

## Purpose and authority

[`15-implementation-plan.md`](15-implementation-plan.md) remains the authoritative phased plan and its
Phase 8 checklist remains the definition of done. This document expands that checklist into sequenced
milestones with exit criteria, records the decisions that must be taken before or during each milestone,
and names the risks that would otherwise surface late.

It does not reopen scope. Capabilities deliberately deferred stay recorded in
[`22-future-development.md`](22-future-development.md); the component-level source material is
[`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md).

Status entries record individual delivered increments, not publication readiness or a complete release
pipeline. Current actionable findings and dated verification limits belong to
[`RELEASE_GAPS.md`](../RELEASE_GAPS.md); earlier milestone observations are historical when superseded
by a later delivered increment.

Sizes below are relative (S/M/L), not calendar estimates. Absolute scheduling depends on team capacity and
is deliberately not asserted here.

## Where the work actually starts

Phase 8's backend prerequisites and blocking semantic decisions are met.

| Precondition                   | State                                                                                                                                                                                                                           | Blocks |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| A real `AuthenticationBackend` | **Met.** `DatabaseAuthenticationBackend` is the default: admin-provisioned local accounts and server-side sessions ([ADR-0031](decisions/ADR-0031-local-database-authentication.md)).                                           | —      |
| Three missing read endpoints   | **Met.** `GET /projects` ([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)), `GET /aggregations/{id}/results/{result_id}/predictions`, and `GET /annotations?snapshot_id=&tei_id=` are delivered.              | —      |
| Collections to navigate by     | **Met.** `GET /projects/{id}/snapshots`, `GET /snapshots/{id}/runs`, and `GET /runs/{id}/aggregations`, `/evaluations`, and `/exports` list their resources newest first, so the routes can recover the identifiers they carry. | —      |
| Blocking semantic decisions    | **Met.** D1–D6 are resolved. See [Decisions](#decisions-taken).                                                                                                                                                                 | —      |

The shell and the M3–M9 workflow screens are now implemented, as recorded in their delivery sections
below and the [client overview](../frontend/README.md). M1-only descriptions are historical, not the
current capability inventory. Implementation does not close the outstanding accessibility assignments
or establish a verified public release.

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
- `.gitlab-ci.yml` already has `frontend_publish_image` and `frontend_sbom` jobs.

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

**Dependency accountability.** The frontend SBOM job is configured to scan the built image by digest.
Direct npm dependencies and licences are justified in [the client overview](../frontend/README.md).
Configured CI jobs are not evidence of a published release or retained SBOM; promotion still requires
the [selected pipeline's artifacts and verification record](21-production-promotion.md).

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

| Milestone | Added criterion                                                                                                                                                                      |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| M0        | Accessibility owner appointed (D18); statement obligation confirmed; test protocol drafted (D17)                                                                                     |
| M1        | `rem`-based token scale; automated checks in CI — linter accessibility rules, `axe-core` in component tests, contrast assertions for both themes                                     |
| M2        | Skip link, focus management, live-region infrastructure, accessible theme and locale switches, documented keyboard model; the shell passes a manual screen-reader pass               |
| M3        | Form labelling and error association; upload limits announced, not only shown                                                                                                        |
| M4        | Long-running progress announced through a live region without flooding it                                                                                                            |
| M5        | The hardest screen: pinned action bar must not obscure focus (2.4.11); shortcuts suppressed in text inputs; annotation results and conflicts announced; list selection state exposed |
| M6        | Annotation history readable as a structured list, not a visual timeline only                                                                                                         |
| M7        | Every chart has a table equivalent; no meaning carried by colour alone                                                                                                               |
| M8        | Export lifecycle and completion announced                                                                                                                                            |
| M9        | Full internal conformance pass across the D17 matrix; user testing round completed (D18); statement and feedback mechanism published if required                                     |

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

| ID  | Milestone                           | Size | Hard dependencies                                                                                                                        |
| --- | ----------------------------------- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| M0  | Decisions and backend prerequisites | M    | scope-exclusion confirmation; accessibility assignments                                                                                  |
| M1  | Scaffold and transport              | S    | none — D3, D8, D11, D12 all resolved                                                                                                     |
| M2  | Application shell                   | M    | M1; a working auth backend; `GET /api/v1/branding` ([ADR-0036](decisions/ADR-0036-institution-branding-configuration.md)), **delivered** |
| M3  | Projects and import                 | M    | M2                                                                                                                                       |
| M4  | Runs and aggregation                | L    | M3                                                                                                                                       |
| M5  | Review workbench                    | L    | M4                                                                                                                                       |
| M6  | Person browser and audit view       | M    | M5; D5 resolved                                                                                                                          |
| M7  | Evaluation and statistics           | M    | M4                                                                                                                                       |
| M8  | Export                              | S    | M4                                                                                                                                       |
| M9  | Optional paths and production build | M    | M5                                                                                                                                       |

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
  **Implemented.** `useSessionStore` (Pinia; session and roles are exactly the "genuinely shared client
  state" docs/26-frontend-coding-guidelines.md assigns there) resolves the session once at app start,
  and `/login` and `/change-password` cover login with "keep me signed in", the forced-password-change
  gate and its own view, and logout — verified against a real Chrome instance over the DevTools Protocol,
  including that the backend's `Secure`-flagged cookies are in fact accepted and sent back over plain
  `http://localhost` (Chrome's documented allowance for that origin) and that the session survives a full
  page reload. `initialize()` also distinguishes an ordinary `401` (not signed in) from any other failure —
  a `5xx`, a network error, an unparseable response — as its own `error` status, so a genuine server problem
  at boot renders as one rather than as a misleading "please sign in" (see the M2 exit criterion below).
  Project-scoped screens now use `current_user_role`; account/team/settings administration and project
  membership screens are also implemented. Their later delivery sections record capability and
  verification separately. `/admin/users` waits for session initialization, is available only to a
  password-current global administrator, and gives signed-in non-administrators an explicit permission
  state. Principal-scoped TanStack Query requests are cancelled and removed on access loss.
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
  carried over. **Delivered:** `AppButton`, labeled native fields, and shared `AppDialog` presentation
  serve the current consumers; HeadlessUI owns dialog focus trapping.
- Locale switch and theme switch (system, light, dark), and the shared vocabulary components that render
  `CanonicalLabel`, `CertaintyTier`, and `AgreementTier` as canonical token plus translated gloss (D2, D3).
  **Delivered.** Locale and theme choices use `SidebarPreferences`' HeadlessUI listboxes and the
  `useLocale`/`useTheme` mechanisms. Signed-in saved choices also have the personal-settings surface below;
  domain vocabulary presenters render canonical labels and tiers without changing their meaning.
- Overlay primitives on the chosen headless accessibility library (D9); everything else in-house.
  **Delivered.** `SidebarPreferences` owns its live listbox interactions; `AppDialog` shares dialog
  presentation without owning dismissal policy, requests, or caller-specific business state.
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

**Status.** The read-only directory, global-admin account creation, mutable-account editing, password reset,
and session revocation are delivered. The generated `POST /api/v1/admin/users`,
`PATCH /api/v1/admin/users/{user_id}`, `POST /api/v1/admin/users/{user_id}/reset-password`, and
`POST /api/v1/admin/users/{user_id}/revoke-sessions` operations keep server-ordered, cursor-paginated
directory data in a principal-scoped query cache and never replay an administrative write after `401`
recovery. Creation and reset disclose generated temporary passwords only in component-local state; reset
captures its target and operation, retains the disclosure when the follow-up directory refresh fails, and
clears it on dismissal, unmount, principal/access change, and logout. Reset controls explain the forced
password change, session revocation, and inactive-account boundary. The current administrator links to
`/change-password` instead of using an administrative self-reset. Session revocation confirms its
password/role/activation invariants; self-revocation clears local private state and routes to sign-in without
an extra logout or administrative refetch. Mutation responses from an obsolete view, principal, or access
state are discarded. Editing permits only display name, global roles, and activation state, confirms
deactivation, and prevents obvious self-lockout controls without treating the paginated client directory as
an authority on the last active administrator. Manual browser verification of the new German/English,
light/dark, keyboard, responsive, and recovery states remains pending review.

**Presentation (2026-09-25).** The screen is titled Users (Benutzer*innen) and uses the project pages' width.
Account creation is an inline card opened from an Add user button in the heading row; hiding it preserves a
draft and a one-time temporary password. Editing expands beneath the account's own row, with focus moving in
and back; deactivation and the security actions keep their confirmations. Row actions are ghost buttons, and
account and password states are plain coloured text. The rationale and open checks are recorded in
[`27-frontend-improvement-plan.md`](27-frontend-improvement-plan.md).

The existing read path presents server-ordered accounts with username/display-name search, opaque cursor
pagination, account state, required-password-change state, global roles, and a current-account marker. The
route and sidebar wait for the session result; the screen retains its clear signed-in non-admin, signed-out,
password-change, session-error, retry, empty, search-empty, initial-error, pagination-error, and refetch
states. Private administrative query data is principal-scoped and removed on a principal or eligibility
change and when the view unmounts.

ADR-0041's global-administrator team administration UI is delivered: it keeps team and roster discovery
principal-scoped, provides confirmed lifecycle and roster mutations, and does not replay a mutation after
authentication recovery. The project-creation and project-membership UI remains pending. In particular,
project managers still receive no account-directory UI, and no manager-transfer screen is linked before that
project-scoped workflow is delivered. Focused frontend tests are added; runtime suites and manual browser
verification remain pending. ADR-0040 still permits frontend edits only for its six branding fields; the
implementation does not expose any other deployment settings.

### Account presentation preferences — ADR-0043

**Status. Delivered in two increments.**
[ADR-0043](decisions/ADR-0043-account-level-user-preferences.md) defines account-owned locale, theme, and
explicit desktop-sidebar collapse preferences. The first increment delivered backend contracts,
persistence, migration, `GET`/`PATCH /api/v1/me/preferences`, tests, and generated OpenAPI/TypeScript
transport. The subsequent frontend increment supplies the lazy `/settings` route named `userSettings`
and a translated Personal settings item in the header account menu. Every resolved, signed-in,
password-current user has access without any project or global role. Administrative branding remains at
`/admin/settings`, and project/scientific settings are outside this resource.

The form contains Interface language (Browser default, Deutsch, English), Theme (System, Light, Dark), and
Desktop sidebar (Expanded, Collapsed). Drafts remain local component state, including restored defaults;
Save is explicit and exposes unsaved, saving, and saved states. Loading and read-error/retry states are
separate from the editable form. Failed saves retain the draft. Saves carry `expected_revision`, preserve
omitted fields, and update the principal-scoped query cache only from the canonical response. A
`409 preferences_revision_conflict` retains the draft and requires deliberately reloading saved values
before another save; no silent replay or overwrite is allowed.

Saved preferences apply through the existing locale/theme mechanisms and the shell. `locale: null`
remains null on the server and resolves to the first supported browser-language primary subtag, then
German. `theme: system` follows the browser's color-scheme preference. At widths of at least 1080 CSS
pixels, the saved desktop choice selects the expanded sidebar or accessible icon rail; below that width,
responsive layout remains independent. Viewport changes and temporary mobile state never save
`desktop_sidebar_collapsed`. Wider sidebar redesign is outside this increment.

Private cache state and outstanding request ownership are invalidated on logout or account changes;
a late result cannot alter another account's cache, draft, or presentation. Existing
`gendertagger.locale`/`gendertagger.theme` localStorage values remain anonymous-only and are never migrated
to accounts or overwritten by account choices. Startup may use anonymous values before identity resolves.
A resolved account uses browser-default locale, system theme, and an expanded desktop sidebar while its
first preferences read is pending or unavailable, then uses its canonical API preferences. There is no
account startup cache. Logout restores the untouched anonymous choices. A failed read or save is always
shown as failure, even while fallback presentation is usable.

Backend acceptance covers defaults without read-side initialization, account isolation, persistence
across sessions, strict validation, locale clearing, auth/forced-password/CSRF behavior, stale no-ops, and
concurrent first writes on PostgreSQL. Frontend acceptance covers loading/saving, defaults, read and write
failures, conflicts, account switching and anonymous transitions, saved presentation effects, responsive
separation, keyboard and accessible status behavior, both locales/themes, contract drift, and production
build. The
[implementation plan](15-implementation-plan.md#account-preferences-increment-adr-0043) owns sequencing.

### Contextual sidebar completion

**Status. Delivered (2026-09-25).**

Review, People, Evaluation, Export, Users, Teams, and Branding settings retain their implemented routes;
no placeholder replaces a functioning screen. Evaluation and Export remain run-scoped destinations as
delivered in M7/M8. Game mode is a separate optional path, delivered under D22.

- A desktop collapse button sits below language and theme in the sidebar footer and saves only
  `desktop_sidebar_collapsed` and `expected_revision` through
  ADR-0043. It waits for eligible, loaded account preferences, adopts the confirmed response, and leaves
  the saved layout unchanged after a failed write. Conflicts require explicit reload before another
  attempt. It does not introduce a localStorage key or mirror canonical preferences in Pinia.
- Only eligible signed-in sessions mount the sidebar and mobile drawer. Signed-out, unresolved,
  failed-session and password-change-required states use a compact public header with home branding,
  account/session controls, and language/theme choices; legal links stay in the footer.
- At least 1080 CSS px uses the saved expanded/rail choice; 720–1079 px always uses a compact rail.
  Below 720 px the persistent sidebar is hidden and the title-bar navigation button opens a Headless UI
  Dialog drawer. The drawer traps focus, makes background content inert, closes on Escape, backdrop
  activation, successful navigation, or leaving the mobile breakpoint, and restores trigger focus.
  Its open state is local to the shell; resizing and opening/closing never write account preferences.
- One typed navigation model supplies both presentations with visibility, targets, missing-context
  explanations, icons, and exact route-name ownership. Detail routes mark their owning destination
  current. Disabled destinations expose their prerequisite on focus and hover without navigating.
  Rail labels use the in-house D9 tooltip pattern, including Escape dismissal and hoverable content.
  Activating a trigger dismisses its tooltip before saving or layout changes; the expanded collapse
  button uses its visible label without a redundant tooltip.
- Language and theme controls use the sidebar footer for eligible sessions and a compact header variant
  otherwise. The same component preserves preference persistence and recovery. Expanded and drawer
  presentations show labels; rail presentations retain named icon triggers. Choice panels open upward
  without being clipped. Signed-in choices save only the changed field with its revision; conflicts
  require explicit reload and failures remain visible. Anonymous choices retain the existing browser
  storage. While identity is unresolved or account access is unavailable, temporary presentation changes
  write neither account preferences nor anonymous storage. New canonical account values replace these
  temporary changes. Personal settings now lives in the header account menu with Sign out;
  the menu trigger shows account identity. The
  [global header guidelines](25-frontend-design-guidelines.md#global-header) supersede the earlier
  footer placement.
- Project switching sits above readable project destinations, including an accessible rail control and
  the mobile drawer. The header supplies short breadcrumbs. Global routes use Projects without an
  implied current project; draft path departures and sign-out use the shared leave dialog.
- Navigation scrolls independently so brand, controls, and preference footer remain reachable. Shell
  dimensions use semantic tokens; transitions honor reduced motion. The drawer and menus must reflow
  at 320 CSS px and retain long German labels without horizontal page scrolling.

Acceptance includes bilingual role/context and exact-current tests, canonical partial saves, failures and
conflicts, account transitions, breakpoint separation, tooltip keyboard behavior, drawer dismissal and
focus restoration, and automated accessibility checks. Real-browser layout/focus verification complements
jsdom; the assistive-technology/user-testing requirements of D17/D18 remain release gates.

Verification includes the full frontend regression and coverage gate, lint/format/type/message/transport
checks, production build, and locked repository checks. A bounded Chrome pass with intercepted local
fixtures covered German/light and English/dark at 1440, 800, 320, and 1080 CSS px: keyboard collapse and
reload, hover/focus tooltips, upward footer menus, modal focus trapping, Escape/backdrop dismissal,
trigger restoration, visible focus after a breakpoint change, no responsive preference writes, and
reduced motion. These browser fixtures did not modify persisted account or project data. Manual NVDA/
Firefox, VoiceOver/Safari, text-spacing overrides, and the D18 user round remain unverified here.

The first partial shell save also exposed misleading OpenAPI default metadata on
`UserPreferencesUpdate`: the backend already preserved omitted fields, but generation made two optional
fields required in TypeScript. The canonical PATCH schema now omits advertised replacement defaults;
regenerated transport permits a changed field plus `expected_revision`. Validation and runtime semantics
are unchanged, with focused contract/API coverage for the correction.

### Administrative branding settings — ADR-0040

**Status.** The administrative settings screen is delivered at `/admin/settings` for eligible global
administrators. Its principal-scoped administrative query is cancelled and removed on a principal or
eligibility change and on view unmount. The overview shows each permitted field's effective value,
deployment fallback, and server-authoritative override state, including explicit `null`/`[]` clearing and
overrides equal to the fallback. Derived logo URL and deployment-managed initiatives and legal entity remain
read-only.

The editor sends only a sparse `branding` object with its baseline `expected_revision`. Each field is
explicitly unchanged, set, or cleared; an equal set value remains an override instead of being silently
normalized away. Client validation mirrors the canonical six-field contract before a request, while the
server remains authoritative. Reset is a distinct selected-field operation: the form explains that it is
disabled while unsaved edits exist, and the confirmation names the fallback that will take effect and that
concurrent edits can conflict.

A mutation response replaces the private query's metadata and revision, including server-defined no-ops.
`409 settings_revision_conflict` loads the latest private snapshot but retains the draft and refuses another
write until the administrator explicitly reconciles or discards it. `503 settings_unavailable`, network
failure, and an uncertain post-submit outcome have distinct visible errors; none claim success, synthesize
fallback data, or automatically replay the write after reauthentication.

`useBranding` now reads the single shared public TanStack query. Successful administrative mutations cancel
stale public reads and refresh that query so already-mounted footer and legal-notice consumers update
without navigation. Private administrative settings and public branding remain separate caches. If that
follow-up read fails, saved administrative state remains confirmed, the public failure is visible, and Retry
performs only the public read.

**Manual verification pending.** Verify German and English light/dark, keyboard, and responsive editing;
an equal-valued pinned override after changing deployment fallback; dirty-form reset blocking; two tabs
conflicting then explicitly reconciling; `503` and lost-response messaging; and mounted footer and
legal notice updating after save without navigation. Runtime/browser suites were intentionally not run for
this delivery.

### M3 — Projects and import

**Goal.** The first write path, and the first real provenance surface.

**Work.**

- Project list and switcher from `GET /projects`, which returns only the caller's projects with the caller's
  role in each; project creation including `slug` and `description`, offered to global operators (D6).
  **Partly delivered.** `ProjectListView` lists and creates projects, cursor-paginated through the shell's
  first use of a query cache (`@tanstack/vue-query`, decision noted in `frontend/README.md`); a signed-out
  visitor is redirected to `/login` and a genuine server error gets its own state, matching the pattern
  from M2's exit criterion. Also delivered: the sidebar layout from `docs/25` (`AppSidebar`), previously
  outstanding from M2 and folded in here since M3 is what first needs cross-screen navigation. The project
  switcher was built in M9 (below), and the nested `/projects/:projectId/...` routes were added as their own
  screens landed.
- `ProjectOverviewView` (`/projects/:projectId/overview`). **Delivered**, folded together with the former
  Daten screen since (D23, 2026-09-30). One flat panel card with hairline-divided sections: project details
  (slug, role, team, creation date, description); the project's data state (`ProjectCurrentSnapshot.vue`:
  snapshot count, records and import date of the latest _ready_ snapshot, runs on it, and imports in progress
  or failed only when there are any, **plus** the newest snapshot overall — ready, still importing, or failed
  — shown as its own card, since that one, not necessarily the latest ready one, is the project's present
  state); the import toggle, in the page's own heading, for a project operator; and review progress for the
  project's working aggregation ([ADR-0035](decisions/ADR-0035-project-working-aggregation.md)). The review
  section reads `GET /aggregations/{id}/review-summary` once the aggregation has completed: people reviewed,
  the three workflow states with the confirmed/corrected split, the same "open of total" per evidence queue as
  the review workbench, and the final-label distribution. It never uses a confidence threshold. Snapshot and
  run counts read only the first page and show a lower bound (`n+`) when the server reports more. Each section
  fails and retries on its own, and the link to the snapshot history stays available if its figures do not
  load.
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
- Snapshot provenance: `source_sha256`, `parser_version`, per-member manifest entries. **Delivered.**
  `ProjectSnapshotsView` lists every snapshot (`GET /projects/{id}/snapshots`, newest first and
  cursor-paginated) with import time, lifecycle, record count and source format; since D23 it is a read-only
  history page, reachable only through the link Übersicht gives it, not a sidebar destination of its own.
  Each entry opens a snapshot detail with source files (name, media type, size and checksum), disclosed import
  configuration/parser/hash, and read-only raw person records once ready. Source records use the existing
  cursor and exact TEI-ID endpoints, independently of classification. Principal-scoped queries and
  project/snapshot checks prevent stale data appearing after account or route changes.

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

**Delivery status (2026-09-24).** M5 is delivered in three slices: **M5a** (queue and detail, read-only), **M5b**
(decisions) and **M5c** (bulk selection).

- **Keyboard model for the action bar (decided 2026-09-24).** The four labels are the single-key shortcuts `1`–`4`
  in the order of the vocabulary (`male`, `female`, `unknown`, `institution`), as docs/25 already asks. `verify` and
  `defer` get **no** letter shortcut: they are ordinary buttons reached with `Tab` and `Enter`. Letters would be
  English initials in a bilingual interface, and nobody had specified them. All shortcuts are suppressed while a text
  input has focus and are listed in the interface. (M5b.)
- **M5a: queue and detail. Delivered.** `/projects/:projectId/runs/:runId/aggregations/:aggregationId/review`
  (`ReviewView`), reached from a completed aggregation. Three entry points per D2: contested evidence (`low`,
  `contested`), thin evidence (`single`, `uncertain`) and all people; each is one `GET /review-items` query, so its
  order and cursor come from the server. The counts on the cards are summed from `review-summary`, never counted from
  loaded pages. Filters cover the whole server-side set (`q`, `sort`, `workflow_states`, `final_label`,
  `agreement_tiers`, `has_authority_conflict`, `has_prediction_error`, and `method_name` with `method_label` and
  `prediction_status`, which the server only accepts together with a method). The whole view state (queue, filters,
  selected person) is in the URL, so it can be bookmarked and shared. The list pages by cursor and the filter tuple is
  part of the query key, so a cursor is never reused across tuples. The detail shows the tiers (token untranslated
  beside a gloss, D3), `override_source` as a marked block, the authority conflict and prediction-error flags, every
  method's result in selection order with `abstain`, `error`, a stored `unknown` and a missing prediction kept
  apart, each `method_confidence` labelled as method-specific and shown to two places, the register entry, and the
  complete attributed annotation chain. Verified against the real API on the seeded aggregation (queues
  `demo-4, demo-3` / `demo-6, demo-5`, seven people in TEI order).
- **Detail navigation. Delivered (2026-09-26).** Compact previous/next arrows beside the person's name follow the
  server-ordered queue. `ArrowUp` and `ArrowDown` invoke those controls only while a navigation control has
  focus. At the final loaded entry, Next fetches the next cursor page before advancing;
  it never guesses a neighbour across a cursor. A deep-linked item outside the loaded queue has neither direction.
  Each move is the ordinary URL selection, so the shared draft-leave guard still asks before abandoning unsaved input;
  declining keeps the current person selected.
- **Deviations from the wireframe, deliberate.** No automatic save (append-only). No confidence threshold or
  "confidence ascending" order (D2). The action bar is the four real labels. No default review-state filter: the
  server's triage order deliberately ignores `workflow_state` (ADR-0022), so reviewed people stay in place and are
  filtered out on request with the review-state checkboxes.
- **M5b: decisions. Delivered.** The detail column has a decision block: confirm the machine label (`verify`, sent
  with exactly that label and disabled when the machine reached none), correct to one of the four labels, or defer,
  each with an optional comment. It is one radio group and a save button, so the keyboard model is as decided:
  `1`–`4` choose the label to correct to and move focus to the save button, then `Enter` saves; the keys stand down
  in text fields and selects and are shown next to the labels. Every write is `POST /annotations` with
  `aggregated_result_id` and the `expected_revision` read from a freshly fetched chain; saving stays disabled while
  that chain is being re-read and for a person the reviewer may not annotate (project role `reviewer` or up,
  ADR-0033). A success is announced in a status region and focus moves to it; the person's chain, every queue and the
  queue counts are refetched, so the final label changes in the list. The screen says nowhere that anything is saved
  automatically.
- **The `409 annotation_conflict` flow. Delivered.** Nothing is written, the chain is re-read, and a focused alert
  names who changed the person and what they decided. The stale choice cannot be saved while the alert is open:
  the reviewer either decides again on the current state (the comment is kept, the choice is not, and the next write
  uses the new revision) or discards the input. Somebody else's newer decision is therefore never overwritten unseen.
- **M5 exit check on the real stack (2026-09-24).** As the seeded reviewer, `demo-7` (no machine label, `no_data`)
  was corrected to `female`: the item's `final_label` went from `null` to `female`, its workflow state from
  `unreviewed` to `reviewed`, and the review summary gained a `correct` group, while the `AggregatedResult` and the
  persisted predictions were byte-identical before and after (compared by hash) and `machine_label` was still `null`.
  Repeating the write with the old revision answered `409` with `current_revision: 1`. The annotation stays in the
  development database (append-only); `demo-7` is therefore no longer unreviewed on the seed.
- **M5c: bulk selection. Delivered.** Reviewers (and operators) can tick people in the queue, or all loaded ones,
  and apply one decision to the selection: confirm each machine label, correct all to one label, or defer all, with
  an optional comment. There is no batch endpoint, so this is a **client-side sequence** (`useBulkDecision.ts`): one
  `POST /annotations` per person, one after the other in list order, each against that person's own
  `review_revision` from the list the reviewer was looking at. A confirmation step names the action, the count and the
  people first and says plainly that each person gets a permanent history entry; nothing is written before it. A
  conflict, a refusal or a failure for one person is that person's outcome only: it neither stops nor retries nor
  undoes the others. The result is an explicit per-person report (saved with revision, conflict with the current
  revision, skipped because there is no machine label to confirm, forbidden, failed, not attempted), announced in a
  status region and focused. A stop request finishes the person in flight and marks the rest "not attempted". People
  who were saved leave the selection; the others stay selected. The queues and counts are refetched once at the end,
  not per person. The selection is dropped when the queue or a filter changes, so it can never apply to people out of
  view. Verified against the real API: a write against the current revision saves (revision +1), a stale write to
  another person answers `409` and leaves that person unchanged, and the first write stays saved. (`demo-1` therefore
  carries an extra `defer` on the seed.)
- Not done: a pinned action bar (the compact choice bar and save button sit directly below the person's name,
  before the summary and method results; the optional comment remains below that evidence. The WCAG 2.4.11 focus
  check for a pinned bar does not arise yet).

**Exit criterion.** A reviewer corrects a machine result and the final-decision view changes without any
mutation of `Prediction` or `AggregatedResult` rows — the Phase 8 criterion from
[`15-implementation-plan.md`](15-implementation-plan.md), verified against a seeded snapshot.

### M6 — Person browser and audit view

**Goal.** Unrestricted register access and visible scholarly provenance.

**Work.**

- Reuse the workbench with `sort=tei_id` and the status/label filters, per decision D5.
- Detail rendering of the source-preserving fields: `name_forms`, `alt_names`, `events`, `external_ids`,
  `source_member_name`, `source_record_locator`.
- Annotation history view showing the superseding chain with reviewer attribution and timestamps in a native
  disclosure, collapsed until the reviewer requests it.

**Exit criterion.** Any person in the register is reachable by search, and every past decision on that
person is visible with its author.

**Delivery status (2026-09-24).** M6 is delivered.

- **Person browser. Delivered.** `/projects/:projectId/runs/:runId/aggregations/:aggregationId/people`
  (`PersonBrowserView`), reached from a completed aggregation. Per D5 it is the review workbench again, not a second
  implementation: the same list, detail, decision block and bulk selection, in a second mode (`ReviewWorkbench` with
  `mode="people"`) that always reads the whole register (`GET /review-items` without a certainty filter,
  `sort=tei_id`) and offers only the register's filters: search, order, review state and final label. It is a separate
  route component rather than a route flag on the review one, so moving between the two never reuses one instance for
  two purposes. The search box says what the server matches.
- **Search covers every way to name a person. Verified.** `q` is applied by the server to the TEI id, surname,
  forenames, other names and the external identifiers, so a person is found by any of them; checked on the real API on
  the seed (`demo-3`, `Okafor`, the authority id `1001-demo`, `Ada` each return exactly the right person). The
  wireframe's search box was disabled; `q` was always server-side.
- **Source-preserving detail. Delivered.** `PersonRecordDetails` renders what the source stored: every name form
  with its type and subtype, dated events with their notes, every authority identifier with its scheme, other names,
  dates, note, and the source file and record locator it came from.
- **Audit chain. Delivered.** The history shows the complete chain newest first: revision number, action, label,
  reviewer's display name, date and time, comment, whether it is the current decision and which revision it replaced.
  It is readable with the viewer role. On the seed, `demo-1` reads `verify` → `correct` → `defer` with authors and
  times. There is no project-wide activity or audit feed (no endpoint; recorded in docs/23), so the audit view is
  per person.
- Not done: a person browser over the raw register that is independent of any aggregation
  (`GET /snapshots/{id}/people`). Every person is in every completed aggregation of their snapshot, so nothing is
  unreachable; an aggregation-free entry would only matter before the first aggregation exists.

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

**Delivery status (2026-09-24).** M7 is delivered in the frontend, with one backend defect that blocks new
evaluations (below).

- **Evaluations as executions. Delivered.** `/projects/:projectId/runs/:runId/evaluations` lists a run's
  evaluations newest first (polled while one is live) and, for project operators, starts one:
  `POST /evaluations` over exact completed method executions, with an optional aggregation for the ensemble figures.
  A started evaluation is opened and polled to an end state; a failure shows `failure_class` and
  `failure_diagnostic`. `/projects/:projectId/runs/:runId/evaluations/:evaluationId` shows what produced it
  (definition, configuration hash, resolved configuration, the scored executions by method name and version, the
  aggregation) and offers the stored report as a JSON download. It reaches a run from the run screen.
- **The report, section by section. Delivered.** Benchmark composition; coverage per method with abstentions and
  technical errors counted apart; accuracy **and** effective accuracy; per-class recall with its Wilson interval and
  correct / class size; one confusion matrix per scored method (rows are the benchmark label, columns the label the
  method gave); the pairwise Cohen's κ matrix, shown in both directions with the co-answered count and "n/d" where κ is
  undefined; and the ensemble tier distributions with the review and correction counts. Numbers keep the three places
  the report stores.
- **Correct labelling of what each metric measures.** Accuracy divides by the answered entries, effective accuracy by
  the whole benchmark so an abstention counts against the method (the published study's definition; from
  `evaluation/metrics.py`). κ is Cohen's κ **between methods**, restricted to entries both answered, and the screen
  says it is not agreement between human annotators. There is no cross-method confidence column (D2), no "Fleiss'
  κ", and no review-time figure, because the backend computes none of them (docs/23).
- **The report is read defensively.** `GET /evaluations/{id}/report` is an untyped `200` in OpenAPI, so the shape is
  declared in `features/evaluation/reportSchema.ts` from `models/evaluation.py` and checked at run time; a body of
  another shape is an error message, never a half-rendered table. The real report of the seeded evaluation is stored
  as a contract fixture (`tests/features/evaluation/fixtures/seed-report.json`) and parsed in the tests.
- **Gap (backend contract): the report is not in OpenAPI.** The response should carry the `EvaluationReport` schema so
  the client can be generated (AGENTS.md rule 17).
- **Gap (backend contract): the definition's required method set is not exposed.** `gnd_benchmark_v1` accepts
  exactly the benchmark method, the seven scored methods and `hivoto_xgboost` (so **not**
  `parenthetical_qualifier`), each once; anything else is a `409`. The form starts from the selection the server
  accepted for the run's latest evaluation, or from every completed execution when there is none, and explains the
  `409`.
- **Defect (backend): new evaluations never run. Closed (2026-09-24).** The worker did not register
  `execute_evaluation` (the task module was missing from the `include` list in `tasks/celery_app.py`), so a new
  evaluation stayed `queued`. The backend now registers it. Verified on the real stack: an evaluation created with the
  selection the form pre-selects (every execution except `parenthetical_qualifier`) completed within seconds, and its
  report is byte-identical to the seeded evaluation's (7,777 bytes), so the run is reproducible from its persisted
  configuration.
- **Exit criterion.** The screens display every table of the report from a stored run, verified on the seeded
  evaluation. Two limits: the seed is seven synthetic people, so its numbers are not the published study's; comparing
  those needs the real corpus run through a stack whose worker registers the evaluation task. The definitions and the
  labelling above are what such a comparison relies on. A new evaluation now also runs to completion on the
  development stack (above).

### M8 — Export

**Goal.** Reproducible, provenanced output.

**Work.**

- Format selection including JSON, `label_source_policy`, `tei_profile`, and `human_resp_id`.
- Asynchronous export lifecycle and download.
- Manifest display: output checksums and the source snapshot hash.

**Exit criterion.** An operator produces a TEI export with human overrides applied and can verify its
checksum against the manifest.

**Delivery status (2026-09-24).** M8 is delivered in the frontend. The two backend problems found while building it
(a worker that did not register the export task and no way to read the manifest of a single-output export) are both
closed; what is still open is one limit of the development seed (below).

- **Exports as executions. Delivered.** `/projects/:projectId/runs/:runId/exports` lists a run's exports newest first
  (polled while one is live) and, for project operators, starts one: `POST /exports` over one completed aggregation
  with the format (`tei`, `json`, `csv`), the `label_source_policy` (`machine_aggregation`, the server's default, or
  `human_overrides`; both stated as only choosing which decision is written out, never changing a stored result),
  and, for TEI only, the profile (`tei_p5_gender_v1`) and `human_resp_id` (the TEI `@resp`, validated as the server
  does: `#` and no whitespace). TEI is refused up front, with the reason, when the run's snapshot is not TEI files
  imported as a single file or as loose files (docs/08). A started export is opened and polled to an end state; a
  failure shows `failure_class` and `failure_diagnostic`. The run and the aggregation screens link to it.
- **Manifest and download verification. Delivered.** `/projects/:projectId/runs/:runId/exports/:exportId` shows the
  persisted manifest of every completed export (`GET /exports/{id}/manifest`, typed `ExportManifest`: the source
  snapshot's SHA-256 and one checksummed descriptor per output), before anything is downloaded. Downloading hashes
  exactly the bytes that arrived (Web Crypto SHA-256) and compares them with the manifest's output, both checksum and
  byte size: the reader is told the file matches, or that it does NOT match and must not be used. An export with several
  outputs downloads as the manifest itself, so there is nothing to compare and the screen says so. Pasting a checksum
  from elsewhere (for a copy that was sent on) stays available as a second, independent check. A manifest that cannot
  be loaded is an error with a retry, never a blank screen; no manifest is requested before the export completes.
- **Verified on the real stack (2026-09-24).** A JSON export with `human_overrides` was created through the API and
  completed on the worker; its manifest names `export.json` with `sha256` `bf587f22…` and 2,323 bytes; the download
  carries `Content-Disposition: attachment; filename="export.json"` and `X-Checksum-SHA256`, and the hash of the
  received bytes is that same value. The manifest of the seeded export is still kept as a contract fixture
  (`tests/features/export/fixtures/seed-manifest.json`).
- **Closed (backend): the manifest is readable for every export.** `GET /exports/{id}/manifest` and the
  `Content-Disposition` / `X-Checksum-SHA256` download headers now exist (docs/08).
- **Closed (backend): new exports run.** The worker registers `execute_export` and listens on the `export` queue.
- **Limit of the development seed: a TEI export cannot be produced from it.** The seeded snapshots point at a
  placeholder source artifact (`local-sha256:aaaa…`, one byte) that is not in artifact storage, so a TEI export of the
  seed fails on the worker with `ArtifactStorageError: stored artifact is unavailable`, which the screen shows as the
  failure diagnostic. JSON and CSV need no source file and work. A TEI export needs a snapshot imported from real TEI
  files (M3) and a run over it; this stays to be exercised on such a project.
- **Gap (backend contract): the request type makes `human_resp_id` required** although the model defaults it to
  `#editor`, so the client always sends one (the default outside TEI). The download is untyped in OpenAPI.
- **Not built.** "Als Commit ins Repository schreiben" (no backend; a v1 exclusion with GitLab) and the wireframe's
  "only reviewed cases" item, which `label_source_policy=human_overrides` covers.
- **Exit criterion.** The screens let an operator start an export with human overrides and verify its checksum against
  the manifest's. Verified on the real stack for a JSON export (above), and for the form, request, polling and every
  manifest state against a mock. Not verified: a freshly produced TEI export (the seed limit above).

### M9 — Optional paths and production build

**Goal.** Ship.

**Work.**

- **Spielmodus. Delivered (2026-09-26).** It uses the ordinary annotation contract and server-side ordering:
  open decisions use review triage, while the entire-dataset pool uses stable source-ID order. A separate round
  resource owns validated scoring and the per-project leaderboard. Neither the score nor game progress
  reorders either pool or changes the regular review queue.
- ~~Einstellungen reduced to whatever persistence exists, or read-only deployment facts~~ — covered by the
  existing administration screens for now, see the Einstellungen bullet below.
- SPA routing fallback in the frontend image (D13), production build, same-origin smoke test through the
  gateway in both themes.
- Accessibility pass: keyboard paths, focus order, contrast against the token palette, screen-reader labels
  for the agreement indicators.

**Exit criterion.** The production Compose profile serves the built client through the gateway, deep links
resolve, and the review path works end to end behind a real session.

**Delivery status (2026-09-24).**

- **Sidebar navigation and icons. Delivered**, since updated three times more (D23, D24, D25; see below).
  `AppSidebar` carries the groups of the wireframe
  ([`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md)): Projekte; Aktuelles Projekt (Übersicht,
  Klassifikation, Redigieren); Auswertung (Statistik & Methoden, Export); Admin. Daten has no entry of its own
  (D23) and Redigieren/Manuell annotieren are one entry, always the same destination (D24, then D25). The
  private navigation and project switcher wait for a resolved, signed-in, password-current session,
  including completion of login's session-flags request. The project group appears only after the current
  project's effective `current_user_role` is resolved successfully. Viewers see Overview and
  available Classification, Statistics and existing Exports; reviewers additionally see the merged
  Redigieren entry. Operators can import from Übersicht and create runs, aggregations and
  exports in their respective screens. Global operator status never substitutes
  for project membership; administrators use the effective operator role returned by the backend.
  Users, Teams and Branding settings require a global administrator. Project query caches are scoped
  to the signed-in principal so a different account cannot inherit cached project roles or names.
  Missing roles, loading and failed project reads hide the project group. Classification and Redigieren
  open independent project-level pickers (2026-09-26). Redigieren's picker opens a per-dataset fast path
  one click from the exact right task, and its own dataset list is how an older dataset is loaded, each one
  choosing its own workbench-or-annotation path rather than one choice for the whole project (D25).
  Availability comes from the canonical project data summary: ready snapshots enable Classification and
  Redigieren for reviewers and operators; completed aggregations additionally enable Spielmodus for those
  roles.
  Genuinely unavailable tasks and empty groups are hidden. Loading/error checks show status and retry,
  including on the icon rail. The snapshot history retains read-only inspection for viewers; existing exact
  result links also preserve read-only access. Statistics and Export require an explicitly selected,
  validated run and never borrow the working result when entering from Members or Overview.
  The working pointer marks recommendations in the picker; it neither selects a result automatically
  nor changes on task entry. Explicit resource links validate project/snapshot/run relationships and
  require a completed aggregation before opening an evidence workbench.
  Desktop collapse, the medium-width rail, and the mobile drawer follow the contextual sidebar
  specification above; labels stay available to assistive technology. Icons are Phosphor (`@phosphor-icons/vue`,
  MIT, named imports so unused icons are tree-shaken), decorative and `aria-hidden`. Spielmodus appears in a
  separate optional group for reviewers and operators only when the project enables it and has a completed
  aggregation (D22).
  Tailwind is not used (D21): styling stays on the semantic tokens of
  [`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md).
- **Project switcher. Delivered.** `ProjectSwitcher`, above project destinations in the sidebar, lists the
  caller's projects (first page of `GET /projects`, server order) and names/marks the current one. The
  Projects destination directly above it opens the full list; the quick menu has no duplicate link.
  Shown only with a resolved, password-current session. The wireframe's completion percentages and
  its "new project" action are not part of it: no backend data exists for the former, and creating a
  project stays on the project list.
- **Personal settings. Delivered as the ADR-0043 frontend increment.** The lazy `/settings` page and
  translated header account-menu item expose only account locale, theme, and explicit desktop-sidebar collapse,
  with explicit saving and conflict recovery. They are available to every password-current account.
  The wireframe's other settings remain unsupported
  ([`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md)). The six branding fields of ADR-0040
  remain separate at `/admin/settings` (sidebar: Admin, "Einstellungen" / "Settings"). A read-only page of
  deployment facts would still require its own explicit endpoint contract and ADR.
- **Accessibility pass, automated part. Delivered.** `tests/accessibility/screens.spec.ts` mounts every screen
  (projects, overview, import, runs, run, aggregation, review, people, evaluations, evaluation, exports, export) in
  both locales against one in-memory API (`tests/accessibility/mockApi.ts`, layered on the review fixture) and asserts
  exactly one page title and no axe-core violation. It also covers the states that add or move content: a decision
  chosen with the bulk form and its confirmation open, a decision that meets a `409` conflict, a finished bulk
  report, and the read-only variants for a viewer. All pass. Colour contrast is not computed by jsdom and stays
  asserted against the tokens (`tests/styles/tokens.spec.ts`); focus movement and announcements are tested where the
  interaction lives (review, decision, bulk). What this cannot show remains the manual pass of D17: real screen
  readers, keyboard-only use of the running application, contrast in the rendered pages, and the user round of D18.
- **Production profile through the gateway. Verified (2026-09-24).** The client image builds from
  `deploy/docker/frontend.Dockerfile` (target `production`, about 2.5 minutes) and runs behind the gateway
  (`compose.yaml`, `frontend` and `gateway`). Checked over HTTP: every application route, and an unknown path,
  answers `200` with the shell (the D13 history fallback); `/api/v1/` reaches the API, including its JSON `404`;
  content-hashed assets carry `Cache-Control: public, max-age=31536000, immutable` while `index.html`,
  `theme-init.js` and the fallback are `no-cache`; the built bundle contains no absolute host of its own.
- **Real-browser smoke test. Delivered** (`frontend/scripts/production-smoke.mjs`, `npm run smoke:production`).
  A headless Chrome over the DevTools Protocol, against the production profile with the development seed: a deep link
  without a session goes to `/login` and returns after signing in; the session cookie is `HttpOnly` and `Secure`
  and the CSRF cookie is readable by the client; the review deep link shows the queue with its counts and the first
  person; **key 2 then Enter records a decision** and the person's revision advances; the run, aggregation, people,
  evaluation and exports screens load without scrolling sideways; a hard reload on a deep link keeps the session;
  and no request failed and nothing was thrown (14 of 14, including the manifest of a completed export). It appends one annotation to the seed by design, so it
  is for the development stack only.
- **What the browser found that the component tests could not.** Three defects, all fixed, each with a test that
  fails without the fix: (1) the eight screens added from M4 on lacked the page padding every earlier screen sets on
  its own `<main>` (the shell does not pad), so they sat flush against the sidebar and the window edge
  (`tests/tooling/view-layout.spec.ts`); (2) the review filters ran a token and its gloss together
  ("unreviewednoch nicht geprüft"), on screen and for a screen reader, because two spans had no whitespace between
  them (`review.spec.ts`); (3) screens asked the API for the project and the upload limits before the session was
  known, a burst of requests that could only fail for a visitor about to be sent to `/login`
  (`tests/app/signed-out-requests.spec.ts`, every screen).
- **Observation (not a documented requirement): the gateway sets no security headers.** No `Content-Security-Policy`,
  `X-Frame-Options` / `frame-ancestors`, `X-Content-Type-Options` or `Referrer-Policy` on the entry document, and no
  HSTS (no TLS is configured in `deploy/proxy/nginx.conf`). Nothing in docs/13 or the ADRs asks for them, so this
  is a hardening recommendation for a public deployment, best decided with an ADR; the client itself loads nothing
  from another origin and uses no inline script beyond `theme-init.js`, so a strict CSP should be feasible.

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
percentage threshold has no counterpart in the published method and is not implementable: _"The per-method
confidence values are recorded but do not influence the vote."_ Aggregation is an unweighted majority vote
under a fixed authority priority chain, and decision quality is expressed categorically.

The UI adopts the paper's vocabulary verbatim. Certainty tiers:

| Tier        | Condition                                                                                                              |
| ----------- | ---------------------------------------------------------------------------------------------------------------------- |
| `high`      | at least two methods voted and at least three quarters agreed, or an authority signal fired in agreement with the vote |
| `low`       | at least two voted and a majority of half or more agreed                                                               |
| `contested` | at least two voted but agreement fell below half                                                                       |
| `single`    | only the LLM had usable output, with self-reported `high` confidence                                                   |
| `uncertain` | only the LLM had usable output, with `low` or `uncertain` self-reported confidence                                     |
| `no_data`   | no method could vote                                                                                                   |

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
  methods cannot agree _"concentrates exactly the cases where editorial attention is most warranted."_

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
  conflating them: `uncertain` _"identifies entries where only the LLM responded and did so with low
  confidence, not a vote-level output category."_ The wireframe's fourth action button is therefore
  relabelled `unknown`.
- The action bar becomes `male` / `female` / `unknown` / `institution`, matching the vote alphabet exactly.
- Locale coverage belongs in the test strategy (D11): a missing-translation check, and at least one
  end-to-end path per locale.

Recorded as [ADR-0030](decisions/ADR-0030-bilingual-client-with-untranslated-canonical-vocabulary.md), since it
fixes a durable client-boundary rule alongside [ADR-0006](decisions/ADR-0006-vue-browser-client-boundary.md).
[ADR-0043](decisions/ADR-0043-account-level-user-preferences.md) partially supersedes only the browser-only
locale restriction for authenticated local accounts; browser-default locale stays unresolved in storage
and all canonical-vocabulary rules remain unchanged. ADR-0030 itself remains immutable.

### D4 — Aggregation is created automatically, with an explicit advanced path

**Resolved as recommended.** When an operator opens run detail for a run in a terminal successful state,
the client creates a default
`reference_v1` aggregation over all completed method executions. Explicit aggregation — choosing a strategy
and an exact subset of executions — remains available as an advanced action.

This is a run-detail client command when no viable aggregation exists, not backend automatic execution
on run completion. Opening the upcoming read-only task picker must not trigger that command.

**Consequences.**

- The route keeps the aggregation identifier
  (`/runs/:runId/aggregations/:aggregationId/...`). The model stays visible and shareable; only the common
  path is shortened.
- Re-aggregation is a first-class action, not a hidden one. The paper treats it as a design benefit:
  methods are kept independent so _"slow methods need only run once before being re-aggregated freely."_
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

### D5 — Manual annotation has independent snapshot entry

**Implemented, 2026-09-26.** “Manuell annotieren” starts from a ready snapshot and permits decisions
before classification. The shared picker optionally adds a run and its exact completed aggregation.
“Redigieren” lists completed reviewable results directly. Sidebar entry always opens the project-level
picker; the working result is marked as recommended without automatic selection or writes. Presentation
names follow the [interface terminology](../PRODUCT.md#interface-terminology).

| Destination             | Entry and outcome                                                                                                                         |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Automatische Vorschläge | Choose a ready dataset, inspect its existing runs, or generate suggestions. Open a run to inspect progress, methods and its results.      |
| Redigieren              | List completed reviewable results directly. Each card opens its exact result and shows the owning dataset and run.                        |
| Manuell annotieren      | Step 1 chooses a ready snapshot. Step 2 starts annotation immediately or adds a run and completed result as optional supporting evidence. |

**Entry and selection.** Entry surfaces are inline, not modals. Headings, the selected context and
Change dataset/Change run actions provide orientation; there is no visual stepper. Redigieren reads the
paginated `GET /projects/{project_id}/review-results` collection, so the browser does not crawl
snapshots and runs to find eligible results; each card still shows its dataset/run provenance. Snapshot
options show import time, available record count and source context. Run options show creation time,
methods and status. Where evidence is optional, selecting a run reveals its completed results, each with
an explicit Open action. Never infer a default from recency or from an incomplete cursor page.

The exact working snapshot/run/result is marked as the project's recommended selection. Choosing a
different result for a task does not change the project's working pointer. A picker never changes that
pointer, starts classification, or creates an aggregation merely by opening. After entry, a compact
context row shows the snapshot and optional run/result plus a Change selection action. URL selection,
refresh, browser history, existing exact deep links and draft-leave protection remain meaningful.
Existing direct workbench links open their named resources directly; sidebar task links always lead to
the project-level picker.

**Automatic suggestions composition.**

- Match the other project pages' width, heading row, gutters, cards and ghost actions. Use one page
  heading and the shared breadcrumb instead of redundant local back links.
- Put dataset selection above the run list. Existing runs are the primary content; Generate suggestions
  is a heading-row action for operators and opens a collapsed inline form spanning the list width.
- The form exposes method selection first. Method-specific JSON configuration and execution policy
  belong in clearly labelled advanced disclosures. Preserve the real API configuration and validation.
- Each run has a clear Open run action, date, methods and lifecycle state. Show progress or failure
  where relevant; move configuration hashes and other provenance into detail disclosures.
- Run detail orders status/progress, method outcomes and available results before technical provenance.
  A completed result offers explicit actions to review or annotate using that exact context. Preserve
  multiple aggregations, partial method failures and the distinction between a finished run and usable
  aggregated results. Any change to the run-detail default-aggregation command must be specified
  explicitly, not made as an incidental picker side effect.

**Availability.** An unselected snapshot/run is normal picker state, not a reason to disable or hide an
otherwise usable project task. Hide a destination when its project prerequisites or permissions are
absent, and hide groups with no visible entries:

- Automatic suggestions needs a ready snapshot; only operators can start a run.
- Manual annotation needs a ready snapshot and annotation permission, regardless of run availability.
- Redigieren needs a completed aggregation and review permission.
- Management-only access continues to expose Members without scientific data. Viewers keep read-only
  access to records/results with an accurate label, rather than an advertised manual write capability.
- Statistics and Export use their own valid source prerequisites. Their sidebar links must not borrow
  an unrelated run because the user visited Members.

Availability is server-authoritative: `GET /projects/{project_id}/data-availability` returns the
canonical `ProjectDataAvailability` fields `project_id`, `has_ready_snapshots`, and
`has_completed_aggregations`. Its project-scoped existence queries cover the full stored collection,
require viewer access, and expose no page-specific navigation rules. Picker collections are filtered and
cursor-paginated; filters apply before pagination and cursors bind to the complete query. A null working
pointer, a failed request or the absence of matches on the first page proves nothing about other eligible
data. Loading and failed availability checks need explicit recovery; they must not claim the project has
no results. Refresh availability after import, run and aggregation lifecycle changes, and isolate it by
principal/project as with other private queries.

Raw manual browsing uses `GET /snapshots/{snapshot_id}/annotation-items`, a canonical projection of
person identity and the current human decision/revision. Search, workflow-state and human-label filters
are server-side and cursor-bound. Exact person reads and snapshot/person URLs support reloads beyond
the loaded page. The existing `POST /annotations` accepts the selected snapshot/person without result
evidence; history provides revision zero for unannotated records and the full append-only chain.
Source details remain available through the raw person endpoint. No machine labels, certainty, agreement
or verification action are fabricated when classification is absent; lack of classification is not a
machine `unknown`, `abstain` or `error` outcome.

With real result evidence, the existing `GET /review-items` workbench remains the source for machine
outcomes, final decisions, evidence filters and uncertainty ordering. Exact run/aggregation links remain
valid. Both workbenches expose Change selection and preserve draft-leave protection. Decisions share
snapshot/person history across runs; a new import never inherits it. Saves and revision conflicts refresh
raw annotation projections and all affected cached aggregation review projections. Drafts and selections
are scoped to snapshot and person, not TEI ID alone, so identical identifiers in two imports cannot share
edits.

The Data area remains dedicated to import and read-only source inspection. Viewers can inspect raw data,
completed results and read-only decisions; sidebar labels do not advertise annotation writes to them.
Picker reads do not create default aggregations, move the working pointer, or infer eligibility from a
partial page. ADR-0035's explicit working pointer remains the source for summaries and recommendations.
This decision changes client entry paths only; any change to scientific annotation or evaluation
semantics requires its own design update and ADR.

Verification covers projects with no import, only a ready snapshot, running/failed classification, one
completed result, several results per run and several snapshots. It includes eligible results outside the
first page, working pointers absent or pointing elsewhere, account/role changes, stale responses,
annotation conflicts, draft cancellation and refresh/back/deep-link behavior, in both locales, with
keyboard use, mobile reflow and accessible picker announcements. Direct navigation from Members must
behave like navigation from Overview or Data. Automated results and the pending live browser review are
recorded in the [improvement plan](27-frontend-improvement-plan.md).

### D6 — Project visibility and role scope

**Resolved and implemented: project-scoped membership roles.** Recorded as
[ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md). Viewer, reviewer, and operator are
explicit project roles; only `operator`, which may create projects, and `admin`, which has effective operator
access everywhere, are global roles.

**Accepted target, partially delivered:** [ADR-0041](decisions/ADR-0041-admin-managed-teams-and-delegated-project-membership.md)
partially amends D6. The global-administrator team/roster UI is delivered: direct teams establish eligibility
rather than automatic access, and the global account directory remains unavailable to managers. Every project
will use one team and one manager, distinct from project `operator`; project creation, manager membership,
and manager-transfer UI remain pending. When delivered, the client must use
`current_user_can_manage_members` rather than inferring that capability from `current_user_role`.

**Current consequences.**

- `GET /projects` lists only the projects where the caller has a role, cursor-paginated in slug order. Every
  project representation carries `current_user_role`, the caller's effective role, which the shell uses to
  scope controls for the current project.
- A resource in a project the caller does not belong to returns `404`, exactly like one that does not exist;
  a member below a route's least role receives `403`. The client treats both as it already treats missing
  resources and forbidden actions.
- Delegated roster, candidate, role-mutation, manager-transfer, and management-only project-discovery
  contracts are delivered. The frontend management UI remains pending; it must keep a management-only entry
  distinct from ordinary readable projects and must not use the account directory for candidate discovery.
- Project creation requires a team. The transport is regenerated; the existing creation UI remains pending
  until it supplies a valid `team_id` and the applicable initial-manager selection.

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
CI installs with `npm ci`, and the existing `backend_lockfile` and
`backend_dependency_audit` jobs extend to cover it.
Node 26 replaced the original Node 22 pin: Node 22 is in maintenance and reaches end of life in April 2027,
while Node 26 enters LTS in October 2026 and is supported until April 2029. Every locked dependency supports
it.

**D13 — History-mode routing.** The SPA fallback is added to the frontend nginx image. Hash routing is
rejected because scholarly URLs are shared and cited.

**D14 — The game mode ships in v1, without scoring.** _(Superseded by D20 and then D22.)_ Its lasting
constraint is that it remains a presentation layer over the same annotation contract and never influences
which records are shown for review.

**D20 — The game mode is deferred out of v1.** _(Superseded by D22.)_ Decided 2026-09-24 when no route,
screen, or scoring contract existed.

**D21 — No Tailwind; styling stays on the design tokens.** Decided 2026-09-24. The client keeps the semantic,
theme-scoped tokens in `src/styles/tokens.css` with scoped component CSS, as
[`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md) defines. Icons are the exception that
was asked for: Phosphor (`@phosphor-icons/vue`).

**D22 — The game mode ships with server-owned scoring.** Decided 2026-09-26. Reviewers choose rounds of 10,
20, or 50 records from either open decisions or the entire aggregation. Open decisions retain
`review_triage_v1`; the entire-dataset pool removes the workflow-state filter, includes previously reviewed
records, and uses stable `tei_id` order so new annotation revisions do not disrupt cursor progression. Direct
labels write ordinary `verify` or `correct` annotations; skips write no annotation.
`POST /projects/{project_id}/game-rounds` validates those annotation identifiers and computes a fixed ten
points per accepted annotation. Timing, skips, and streaks remain local session feedback.
`GET /projects/{project_id}/game-leaderboard` exposes each reviewer's best round for one target size. The
leaderboard is persistent engagement metadata and cannot affect annotation
semantics, queue order, exports, or evaluation. New projects default to disabled; an operator opts in from the
project overview. Turning it off hides the optional sidebar group and blocks direct game API access while
retaining completed rounds.

**D23 — Übersicht and Daten are one screen; the snapshot history is unlisted.** Decided 2026-09-30. The
sidebar's separate Daten entry is removed. `ProjectOverviewView` imports new snapshots (the toggle moves from
`ProjectSnapshotsView`'s heading to its own) and always shows the newest snapshot, whatever its status: a
still-importing or failed newest snapshot is the project's present state and is never hidden behind an older,
ready one. The existing figures (snapshot count, the latest _ready_ snapshot's records/import date, its run
count, in-progress/failed counts) are unchanged, since they answer "is there workable data", a different
question from "what is current". `ProjectSnapshotsView` keeps the full, newest-first list for every earlier
snapshot, reachable only through the link Übersicht gives it, never through the sidebar.

**D24 — Redigieren and Manuell annotieren are one sidebar entry.** Decided 2026-09-30. The two task-entry
pickers of `ProjectTaskView` (`mode: 'review'`, gated on a completed aggregation; `mode: 'annotation'`, gated
on a ready snapshot) keep existing as separate routes and components, but the sidebar offers only one entry,
labelled Redigieren, whenever the project has a ready snapshot: it resolves to the `review` picker (results
across every aggregation, the common case) once a classification exists, and to the `annotation` picker (pick
a snapshot, annotate with or without a run's evidence) while none does — active depending on whether the
project had an automatic classification, never two destinations for the reviewer to choose between. Choosing
a result from the `annotation` picker's evidence path now opens the same full Redigieren workbench
(`review` route) as the `review` picker does, rather than the simpler register (`people` route,
`PersonBrowserView`): the workbench's own "Alle Personen" queue already covers plain browsing, so a second,
simplified screen for the identical case in the identical picker is nothing but a fork of the same task.
`PersonBrowserView` and the `people` route are **not** removed: `ProjectReviewStats` (Übersicht) and
`AggregationDetailView` still link to it directly, as a deliberately simpler register view for someone who
already knows which aggregation they mean and does not want the triage framing.

**D25 — Redigieren decides per dataset, not per project; it always has one destination and a fast path.**
Decided 2026-09-30, superseding D24's project-wide branch. A project can hold both a classified and an
unclassified dataset at once; D24's single `has_completed_aggregations` branch then sent every reviewer to
whichever picker matched the _other_ dataset, with no way to reach the right one for both. The sidebar's one
Redigieren entry now always opens `projectAnnotation`; `projectReview`'s flat cross-dataset results list stays
as a working, unlinked route (like `projectImport`), not deleted. The picker itself gained a fast path: an
"Aktueller Datenstand" card above the existing dataset list, one click to the exact right task — the workbench
if the project's working aggregation ([ADR-0035](decisions/ADR-0035-project-working-aggregation.md)) names a
completed one, otherwise direct manual annotation of the newest ready dataset, never the with/without-evidence
choice for that click. The dataset list below is unchanged and remains how an older dataset is loaded, per
dataset, choosing its own correct path exactly as the fast path does for the current one. The task-entry
heading itself now reads Redigieren (`nav.review`) instead of Personen, since the screen no longer only leads
to the plain register.

**D26 — A guided and an advanced presentation, chosen per account, not per project.** Decided 2026-10-13,
following direct review feedback that the full navigation overwhelms a first-time user. Account preferences
(ADR-0043) gain `interface_mode` (ADR-0050: `"guided"` or `"advanced"`, defaulting both existing and new
accounts to `"guided"`). The choice is a personal, project-independent presentation setting with a single
control on the personal settings page — an immediate-save radio pair in the same interaction style as
`ProjectGameModeSetting.vue` (pending/saved/error status, no separate confirm step) — not a sidebar-footer
duplicate, since switching presentation is rare compared to switching projects.

Both presentations drop the persistent "Projekte" sidebar tab in favor of a signed-in home page
(`SignedInHomeView`-equivalent) that hosts the project list, "Projekt anlegen", and per-project "Mitglieder
verwalten" (mirroring `ProjectListView.vue`'s existing card action, gated the same way by
`current_user_can_manage_members`) directly on each project's card. Per-project sidebar tabs appear only once
a project is open; a "Projekte" tab pointing at the home page is shown in its place otherwise, so the sidebar
never shows both at once. The account-scoped "Mitglieder" project-sidebar entry is removed entirely in both
presentations — relocated to the home page's project cards — since its visibility already depends on a
narrower, per-project condition (project manager or admin) unrelated to project role, and sat ungrouped among
role-gated tabs it does not share a visibility axis with. In the advanced presentation, "Export" moves to
directly after "Redigieren", ahead of "Statistik & Methoden" (today's `nav.evaluations`); every other advanced
tab and its destination route is unchanged from D23–D25.

`AppBreadcrumbs.vue`'s project-context chain gains a leading crumb back to the home page before the project
name, on every project-scoped route including `projectOverview` itself (today's single, unlinked
project-name crumb there is the one place the chain has no way back). Browser-language and theme behavior,
and every underlying scientific route and capability, are unaffected; this is presentation only.

**D27 — The guided presentation's project page is three steps that become four.** Decided 2026-10-13. The
guided presentation's per-project landing tab ("Gender taggen") replaces `projectOverview`, `projectImport`,
`projectClassification`, and the per-dataset entry into Redigieren with one sequential page: "Daten
importieren", "Automatische Vorschläge generieren", "Prüfen", and — once generation completes — "Export".
"Generieren" preselects every available method (`useMethodList`/`useCreateRun`, the same mechanism
`NewRunForm.vue` already uses, with empty per-method configuration) rather than exposing per-method selection.
Immediately after the resulting aggregation completes, the guided flow calls the existing
`PUT /projects/{project_id}/working-aggregation` endpoint to set it as the project's working aggregation —
ADR-0035 does not do this automatically, and without it neither "Prüfen" nor "Export" would have anything to
point to. "Export" opens inline on the same page (no separate route): it exports the project's working
aggregation directly, offering only the format choice (TEI, JSON, or CSV, matching
`NewExportForm.vue`'s real options — not XLSX, which is an import, not an export, format). The aggregation
picker and the advanced label-source/TEI-profile/responsible-person fields remain advanced-presentation-only,
reached through the unchanged `exports`/`NewExportForm.vue` route. Export creation is asynchronous like a run;
the guided page reuses the same create-then-poll presentation as "Generieren" rather than implying an instant
download. The guided presentation has no entry point for manual annotation without a classification — a
deliberate removal, not an oversight — while D25's fallback to plain annotation remains exactly as it is in
the advanced presentation.

**D28 — The advanced presentation's Übersicht adopts Automatische-Vorschläge's shape, and "Stand der Prüfung"
only ever describes the current dataset.** Decided 2026-10-13. The advanced "Übersicht" tab becomes a landing
page of three cards — Projektübersicht (today's `projectOverview` facts), Aktueller Datenstand, and Anderen
Datenstand wählen — replacing today's merged Übersicht/Daten screen (D-2026-09-30, see above) with a shape
consistent with the per-project task entries. Opening a dataset, current or historical, leads to one detail
page that now also carries "Stand der Prüfung" (`ProjectReviewStats`'s content), folded in from Übersicht.
Because ADR-0035's working-aggregation pointer is one per project, not one per dataset snapshot, that section
only renders when the opened dataset is the one currently backing the pointer; any other dataset's detail page
shows a plain note that it is not the active working dataset, with a link to the one that is, rather than a
wrong, stale, or guessed review summary. Browsing to an unrelated dataset's own historical runs and
aggregations remains possible exactly as today, through the existing run/aggregation detail routes — this
decision only changes what the new merged detail page itself shows inline.

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

| Layer           | Scope                                                                                           |
| --------------- | ----------------------------------------------------------------------------------------------- |
| Automated       | `axe-core` in component tests; linter accessibility ruleset; contrast assertions in both themes |
| Keyboard        | Full pass on every screen, both themes, both locales — no pointer used                          |
| Screen reader   | NVDA with Firefox, and VoiceOver with Safari                                                    |
| Zoom and reflow | 400 % zoom / 320 CSS px width; text-spacing overrides applied                                   |

JAWS with Chrome is added only if the institutional user base requires it; that is a question for the
accessibility owner once the user base is known. Automated coverage alone is explicitly not a test strategy.

**D18 — One named owner, and users involved once.** A single named person owns accessibility for the client:
they maintain the test protocol, sign off the per-milestone criteria, and hold the evidence that the
declaration would rest on. The person is still to be appointed — see
[Outstanding assignments](#outstanding-assignments).

At least one round of testing with people with disabilities takes place before M9. With no external audit
(D16), this is the only point at which the assessment is exposed to users who are not its authors, so it is
scheduled rather than left to goodwill.

**D19 — The game-mode timer is switchable off.** The control is reachable **before the first timed round
begins**, and its per-account browser choice persists. The timer is a personal pacing aid, imposes no time
limit, and contributes nothing to the official score. Disabling it does not change records, actions, or writes.

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
- Project settings and personal settings beyond the presentation fields accepted in ADR-0043 and
  ADR-0050; the personal settings UI exposes only those fields
- A bulk annotation endpoint
- Per-case review-time telemetry

## Risks

| Risk                                                          | Impact                                                                                | Mitigation                                                                                                         |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| No real authentication provider                               | Client cannot ship regardless of its completeness                                     | Resolved by D1: the local account backend (ADR-0031) is implemented and is the default                             |
| Aggregation is invisible in the accepted design               | Users expect review immediately after classification                                  | Resolved by D4: auto-create the default aggregation, keep the step legible in the route and the UI                 |
| D6 left open while `GET /projects` is implemented             | Narrowing the response later is a breaking contract change                            | Resolved by D6: `GET /projects` shipped with its final visibility rule (ADR-0033)                                  |
| The membership upgrade removes non-admin access               | Users see no projects until an administrator assigns memberships                      | Plan membership assignment with `gendertagger projects add-member` as part of each deployment's upgrade            |
| Tier vocabulary is unfamiliar to reviewers                    | Six certainty tiers replace one intuitive percentage                                  | Glosses per D3, and two clearly separated queue entry points rather than six raw filters                           |
| Wireframe promises unbuilt features                           | Stakeholder expectation gap at delivery                                               | Confirm the scope exclusions in writing at M0                                                                      |
| Frontend dependency tree meets a provenance-strict repository | SBOM and licence review friction late in delivery                                     | Resolved: D9 sets the dependency budget at one library, `@headlessui/vue` (MIT), justified in `frontend/README.md` |
| No UI-level acceptance coverage                               | Scientific fixtures pass while the review path is broken                              | Define the seeded-snapshot acceptance test as part of D11                                                          |
| Accessibility deferred to a closing phase                     | Legal exposure plus structural rework; the wireframe's controls are unusable as drawn | Per-milestone criteria above; automated checks from M1                                                             |
| Internal-only assessment misses defects (D16)                 | No external check before release                                                      | The D17 matrix is mandatory, not advisory, and the D18 user round is scheduled rather than optional                |
| Game-mode timer conflicts with WCAG 2.2.1                     | A shipped feature that cannot be made conformant                                      | Resolved by D19: the timer is switchable off before the first round                                                |
| Unconfirmed legal notice goes public                          | Wrong provider, representative, or tax details in a legally binding statement         | Its confirmation is an outstanding assignment that gates public deployment, and production promotion stays manual  |

## Immediate next steps

1. Confirm the v1 scope exclusions with the stakeholders who reviewed the wireframe, and confirm with them
   that the threshold control is removed rather than redesigned (D2) — this is the most visible change
   against the accepted wireframe.
2. Appoint the accessibility owner and confirm whether an accessibility statement is legally required.
   Both are organisational, both gate M0, and neither is resolvable from inside the repository.
3. Continue improvements to the delivered client using
   [`27-frontend-improvement-plan.md`](27-frontend-improvement-plan.md). Begin with the global header's
   purpose/content brief and shared accessibility/responsive foundations. The accepted header and sidebar
   project-switcher move are now implemented; improve individual views next and refine the remaining
   sidebar last. Recheck dated findings against current
   code and keep the verification still pending in each delivered increment explicit.

### D26–D28 implementation checklist

Tracks the guided/advanced dual presentation (D26), the guided project page (D27), and the advanced
Übersicht/Datenstand merge (D28) from decision to delivered code. Update the checkbox in the same change
that completes a step; do not mark one done without its tests passing against the real stack.

- [x] Backend: `interface_mode` preference field, migration, ADR-0050, OpenAPI snapshot and frontend
      transport types regenerated. Committed (`d3b6754`).
- [x] Frontend: `interface_mode` wired into `useUserPreferences` (no change needed, generic over the
      generated type) and into `UserSettingsView.vue` as a fourth field in the existing single-form,
      explicit-save pattern (not a separate immediate-save control — the account preferences page already
      has one save model, confirmed against the real file rather than the earlier mockup's assumption).
      Locale strings added in `de.json`/`en.json`. Existing and new tests pass; `vue-tsc --noEmit` and
      `eslint` are clean.
- [x] Frontend: fold `ProjectListView.vue`'s full capability (paginated list, "Projekt anlegen", per-card
      "Mitglieder verwalten", the managed-projects section) into `SignedInHomeView.vue`, so the signed-in
      home page is a complete project entry point rather than a four-item preview. `ProjectListView.vue`
      and the `projects` route are not deleted — `AppBreadcrumbs.vue`'s membership crumb still targets it —
      only the sidebar stops linking to it. The now-redundant "view and create projects" workspace link is
      removed along with its dead `home.signedIn.projects.*` locale keys. New coverage in
      `tests/features/home/signed-in-home.spec.ts`; `tests/features/projects/project-list.spec.ts` still
      passes unchanged. Typecheck, lint, `i18n:check`, and `unused:check` are clean.
- [x] Frontend: `useSidebarNavigation.ts` — the `projects` item points at `home` instead of `projects` and
      is shown only while `project.value === null`; the per-project `projectMembers` item is removed
      (relocated to the home page's project cards); `exports` moves to directly after `review` in the
      project group. This structural change applies to both presentations and is independent of
      `interface_mode`. Updated or removed the now-inapplicable coverage across
      `useSidebarNavigation.spec.ts`, `sidebar-visibility.spec.ts`, `MobileNavigationDrawer.spec.ts`,
      `AppSidebar.spec.ts`, `AppSidebarPreferences.spec.ts`, and `ProjectSwitcher.spec.ts` (several tests
      asserted the "Projekte" tab stays visible alongside an open project's own tabs, or exercised the
      now-removed `projectMembers` sidebar item — both intentionally gone under D26), plus one incidental
      assertion in `tests/features/projects/project-membership.spec.ts`. All affected test files,
      `vue-tsc --noEmit`, and `eslint` are clean; a full `vitest run` found only this and a pre-existing,
      unrelated Windows symlink-permission failure in `tests/tooling/unused-code.spec.ts`.
- [x] Frontend: branch the project group on `interface_mode` between today's full set and the guided set
      (Gender taggen, Statistik & Methoden, Export inline). `useSidebarNavigation.ts`: a guided-only
      `needsWorkingAggregationFallback` reads `useProject` + `useAggregation` to derive an "effective
      runId" for Statistik & Methoden from the project's `working_aggregation_execution_id` (ADR-0035)
      when the URL carries none (guided's one route never does); `useProjectDataAvailability` is only
      enabled in advanced mode; the project-group `items` construction branches on
      `interfaceMode.value === 'guided'` — guided pushes one `'genderTagging'` item, advanced keeps
      every existing line (overview, classification, review, game, exports) byte-for-byte;
      `OWNED_ROUTES.genderTagging` additionally claims `review`/`projectAnnotation`/
      `snapshotAnnotations`/`people`/`exports`/`exportDetail` so the one guided tab still highlights on
      the review workbench or the export hand-off page it navigated to. The loading/error fallback for
      the preference itself is `'advanced'`, not the account default of `'guided'` (ADR-0050) — advanced
      never hides capability over a transient gap, and this is what the whole existing test suite already
      assumes wherever it doesn't mock `/api/v1/me/preferences` explicitly. Found and fixed two real bugs
      along the way: (1) that loading-state default was originally `'guided'`, which broke most of
      `sidebar-visibility.spec.ts` and caused a genuine transient-state leak, not just a test-fixture gap;
      (2) `workingAggregation`'s `enabled` only checked "id is non-null", not the guided-mode gate itself
      — since `projectRecord` shares its query key with the project fetch `useProjectIdentity` already
      runs, its `working_aggregation_execution_id` could arrive from that shared cache even while
      `needsWorkingAggregationFallback` was false, firing an unwanted aggregation fetch in advanced mode.
      Added `nav.genderTagging` locale keys to `de.json`/`en.json`. Test fallout: added mocks for
      `useUserPreferences`/`useProject`/`useAggregation` plus 4 new guided-mode cases to
      `useSidebarNavigation.spec.ts`; added `/api/v1/me/preferences` (returning `DEFAULT_PREFERENCES`,
      now including `interface_mode: 'advanced'`) to all 5 `apiClientWithRoutes` route maps and 8 of the
      9 raw `createApiClient` dispatchers in `sidebar-visibility.spec.ts` (the 9th deliberately asserts
      zero requests during a required password change, where the preferences query is disabled anyway).
      The other 5 sidebar-adjacent files (`AppSidebar.spec.ts`, `MobileNavigationDrawer.spec.ts`,
      `AppSidebarPreferences.spec.ts`, `ProjectSwitcher.spec.ts`,
      `tests/features/projects/project-membership.spec.ts`) needed no changes once the loading-state
      default was fixed to `'advanced'`. Full suite (1763 passed, 2 pre-existing unrelated Windows
      symlink failures in `tests/tooling/unused-code.spec.ts`), `typecheck`, `lint`, `i18n:check`, and
      `unused:check` all verified clean. Not yet committed as of writing this line — do that next
      (`git fetch origin` / compare before committing and before pushing).
- [x] Frontend: `AppBreadcrumbs.vue` gains a leading crumb back to `home` on every project-scoped route,
      including `projectOverview` itself (previously a dead-end crumb with no way back up). The
      `labels` map also gained `projectGenderTagging: t('nav.genderTagging')`, which had no breadcrumb
      label at all before and silently fell back to "not found". Updated all 9 affected cases in
      `AppBreadcrumbs.spec.ts` for the shifted link indices/counts; the membership and permission-loss
      cases needed scoped selectors (`.app-breadcrumb-error a`, `findAll('a')[1]`) since a second,
      unrelated link now exists alongside the leading home crumb. Full suite (1763 passed, same 2
      pre-existing Windows symlink failures), `typecheck`, `lint`, `i18n:check`, `unused:check` all
      clean. Also visually verified against the real stack (Docker dev profile, seeded
      "Frontend demonstration" project): confirmed the home crumb links correctly on both
      `projectOverview` and the guided `projectGenderTagging` page, and confirmed the guided sidebar
      (previous checklist item) renders correctly end-to-end for an account with a stored
      `interface_mode: 'guided'` preference. Found and fixed an unrelated environment issue along the
      way: this long-running dev-stack database predated the `interface_mode` migration (commit
      `d3b6754`), so `/api/v1/me/preferences` 500'd until `docker compose ... run --rm -v
      ".../backend/migrations:/app/migrations" migrate` was re-run — exactly the documented fix, not a
      new bug, but it did validate that the sidebar's advanced-mode fallback degrades gracefully under
      a genuinely failing preferences endpoint, not just in mocked tests.
- [x] Frontend: the guided "Gender taggen" page (D27) — `GenderTaggingView.vue` at the new
      `projectGenderTagging` route (`/projects/:projectId/gender-tagging`). Import reuses
      `SnapshotImportForm.vue`; generate preselects every method from `useMethodList` through
      `useCreateRun`, then replicates D4's auto-create-aggregation watch (not `AggregationSection.vue`
      itself, which also renders its own advanced manual-selection UI the guided page does not want) and
      calls the new `useSetWorkingAggregation` once the created aggregation completes. "Fertig" is read
      from the project's own `working_aggregation_execution_id` (ADR-0035), not local session state, so
      it survives a reload; an in-flight generation does not. Export is a format-only inline form
      (TEI/JSON/CSV, matching `NewExportForm.vue`'s real options) that creates the export via the
      existing `useCreateExport` and hands off to the existing, already-polling `exportDetail` route for
      status and download, rather than reimplementing that polling. New coverage in
      `tests/features/projects/gender-tagging.spec.ts` (facts, the full generate-to-review-and-export
      unlock cycle, and the export submission). Full `vitest run` (1753 tests), `vue-tsc --noEmit`,
      `eslint`, `i18n:check`, and `unused:check` are clean.
- [x] Frontend: the advanced Übersicht three-card layout and the merged Datenstand-detail page with
      current-dataset-gated "Stand der Prüfung" (D28). `ProjectOverviewView.vue`'s one sectioned card
      split into three separate `app-card app-card--sectioned` cards: "Projektübersicht" (the facts
      section, now titled, plus `ProjectGameModeSetting`), "Aktueller Datenstand"
      (`ProjectCurrentSnapshot.vue`, stripped of its own "view history" link), and a new
      "Anderen Datenstand wählen" card (`ProjectOtherSnapshots.vue`) that counts the project's other
      snapshots and links to the existing, unlisted `projectSnapshots` history page — the one way into
      it, promoted out of the card above into its own. `ProjectReviewStats` (Stand der Prüfung) moved
      entirely off Übersicht and onto `SnapshotDetailView.vue`, which now resolves the project's working
      aggregation (ADR-0035) through its run to that run's `dataset_snapshot_id` and compares it with the
      open route's own snapshot id — three chained, gated reads (`useProject` → `useAggregation` →
      `useRun`), enabled only once the snapshot itself is `ready`. Four states: nothing shown when the
      project has no working aggregation at all; the full stats when this is that dataset; a loading
      placeholder or a retryable error while resolving; and, for every other dataset, a plain note plus a
      link to the one that is current — never guessed or stale figures. Removed the now-dead
      `data.viewHistory` locale key (both languages) along with its only remaining use.
      Test fallout: `project-overview.spec.ts` lost its five review-stats tests (moved, not deleted) and
      its single-card structural test became a three-card one; those tests, plus four new ones covering
      the four detail-page states above, moved to/landed in `snapshot-detail.spec.ts`, reusing the same
      fixtures. `tests/accessibility/screens.spec.ts`'s `overview` readiness selector was pointed at the
      new card's own link class, since the one it watched before no longer exists. Full suite (1761
      passed, the same 2 pre-existing Windows symlink failures), `typecheck`, `lint`, `i18n:check`, and
      `unused:check` all clean. Also visually verified against the real stack: the three cards render
      with a visible gap between them (not three hairline-divided sections inside one card), and "Stand
      der Prüfung" correctly renders on the snapshot detail page for the project's one (and therefore
      current) dataset. That check caught that the Dockerized dev frontend container does not hot-reload
      host-side file edits (a Windows bind-mount file-watching gap, not a code bug) — a
      `docker compose restart frontend` was needed before the browser reflected any of this session's
      changes; worth remembering for any future real-stack visual check in this environment.
- [x] Tests for every step above, verified against the real stack (Postgres, Redis where applicable) before
      it is checked off; new D-numbered decisions in this file as behavior is finalized; ADR only if
      scientific/export semantics change beyond presentation. (No new ADR for D26–D28: all three are
      frontend-presentation-only, unlike D26's backend `interface_mode` field, which ADR-0050 already
      covers.)
- [x] Final `git fetch`/compare, commit, and push once the whole increment is verified end to end.
      D26, D27, and D28 are all implemented, tested, and on `origin/main` (commits `d3b6754`,
      `d06328a`, `beb6999`, `4a8e471`, `2c1be11`, `6fa2100`).

### Post-review fixes (2026-10-14)

Direct user feedback after using the real stack surfaced four gaps the checklist above didn't catch;
all four are fixed, tested, and visually verified against the real stack.

- **D28's Übersicht visually read as a different design language than Redigieren/Automatische
  Vorschläge (ProjectTaskView).** "Aktueller Datenstand" and "Anderen Datenstand wählen" were each
  their own `app-card app-card--sectioned` box; `ProjectTaskView`'s equivalent sections are plain,
  unboxed `<section><h2>`s, with only the pickable *items* inside them (`app-resource-card`) bordered.
  `ProjectCurrentSnapshot.vue` and `ProjectOtherSnapshots.vue` no longer use `ProjectOverviewSection`
  (a hairline-divided card section) for their own heading; "Projektübersicht" (facts + Spielmodus)
  keeps its card, since it reads as a static info panel, not a pick-one list, and was not what the
  feedback called out. The page header also gained a description line under the title
  (`projects.overview.pageHint`), matching `ProjectTaskView`'s own `app-page-heading__description` —
  Übersicht had none before.
- **Guided mode leaked advanced-only navigation.** The project switcher dropdown (`ProjectSwitcher.vue`,
  in the sidebar) opened every project at `projectOverview`, a page guided accounts should never
  reach — D28's full dataset history and "Anderen Datenstand wählen" are advanced-only concepts. Fixed
  three places: `AppSidebar.vue` hides the switcher entirely when `interface_mode: 'guided'` (nothing
  useful to switch into); `AppBreadcrumbs.vue`'s project crumb now points at `projectGenderTagging`
  instead of `projectOverview` for guided accounts; `SignedInHomeView.vue`'s "Projekt öffnen" links and
  its post-creation redirect do the same. All three read the preference directly via
  `useUserPreferences()` rather than through `useSidebarNavigation()`'s own internal copy, matching the
  existing pattern of independent per-component reads (e.g. `ReviewWorkbench.vue` below) over a shared,
  wider interface.
- **Guided mode's review workbench ("Prüfen") was a dead end back to Export.** D27 made Export live
  inline on the Gender-taggen page with no route of its own, reachable only from there — but once a
  guided user followed "Prüfen" into the real (unchanged) review workbench, nothing led back. Added a
  "Zum Export" button next to the filter toggle in `ReviewWorkbench.vue`'s heading, shown only in
  guided mode (`genderTagging.review.goToExport`), linking to `projectGenderTagging`.
- **The guided project page's four boxes had no explicit step numbers.** `ProjectOverviewSection`
  gained an optional `eyebrow` prop (a small label above the title) and `GenderTaggingView.vue` passes
  "Schritt 1"–"Schritt 4" (`genderTagging.step`) to each of its four sections. Advanced-presentation
  callers never pass it.

### Second round of post-review fixes (2026-10-14)

Further direct feedback, same day, on top of the round above.

- **The exportDetail breadcrumb still led back to the advanced-only exports list in guided mode.**
  The parent-crumb branch for `exportDetail`/`evaluationDetail` was unconditional; split it so
  `exportDetail`'s "exports" parent crumb only appears when `!guided` (evaluations is its own guided
  sidebar tab, unlike the exports list, so `evaluationDetail` keeps its parent crumb in both modes).
- **Guided mode's "Prüfen" had no way back to the overview, only to Export.** Added a second button,
  "Zurück zur Übersicht" (`genderTagging.review.goToOverview`, ghost variant), next to "Zum Export" in
  `ReviewWorkbench.vue`'s heading — both guided-only, both linking to `projectGenderTagging`.
- **Advanced mode had three further gaps found by direct use of the real stack:**
  - A run's detail page (Automatische Vorschläge → Lauf) had "Auswahl ändern" but no direct way into
    Redigieren for that exact dataset. Added a "Redigieren" button (`nav.review`, reviewer role and
    up) linking to `projectAnnotation` with `?snapshot={id}` — D25's per-dataset decision then applies
    exactly as it would from the sidebar's own Redigieren entry.
  - Redigieren's own heading said "Prüfen" while its sidebar tab and breadcrumb said "Redigieren"
    (`nav.review`) — a German-only mismatch (English already had both as "Review"). Changed
    `review.title`'s German value to "Redigieren"; `AppBreadcrumbs.vue`'s `review`/`projectReview`
    labels share the same key, so they stayed in sync automatically.
  - Redigieren had no direct, prominent way to Export either — only the sidebar's own Export tab, one
    navigation away. Added an unconditional (`!isGuided`), solid/green "Export" button
    (`nav.exports`) next to the filter toggle, linking to `{name: 'exports', params: {projectId,
    runId}}`.
- **The project switcher dropdown was removed entirely, from both presentations** — not just hidden in
  guided mode as the first round did. Project switching is now exclusively a home-page action, in both
  modes; `ProjectSwitcher.vue` and its dedicated test file are deleted, along with the now-orphaned
  `projectSwitcher.*` locale keys. `AppSidebar.vue` no longer reads `interface_mode` or
  `useProjectIdentity().project` for this purpose at all. Three tests in `MobileNavigationDrawer.spec.ts`
  that exercised the switcher's own mobile/keyboard/draft-protection behavior were removed — the
  underlying draft-navigation guard they also covered is still tested directly in
  `useDraftNavigation.spec.ts` and the review feature tests, independent of how a navigation is
  triggered. One test in `sidebar-visibility.spec.ts` covering the switcher's own account-switch
  caching was removed outright for the same reason (the behavior it tested no longer exists).
- **Added "Zurück zur Startseite" at the top of the advanced Übersicht page** (`projects.overview.backToHome`,
  linking to `home`), so leaving a project no longer depends on the (now-removed) switcher or the small
  breadcrumb link alone.

Full suite (1741 passed, same 2 pre-existing Windows symlink failures; the count dropped from 1773
because the three switcher-only tests were removed, not because something stopped being tested),
`typecheck`, `lint`, `i18n:check` (1377 keys, down from 1381 after removing `projectSwitcher.*`), and
`unused:check` all clean. Visually verified against the real stack in both presentations.

### Third round of post-review fixes (2026-10-14/15)

Further direct feedback, continuing the two rounds above.

- **A third wording/navigation pass on the guided flow:** the top-of-page link on Export said "Zurück
  zu den Exporten" even in guided mode; Redigieren's own "Zurück zur Übersicht" was a button, not a
  plain link like Export's; "Redigieren" reverted to "Prüfen" in guided mode specifically (advanced
  mode's own tab name stays "Redigieren" — the two presentations are allowed to name the same workbench
  differently); Schritt 4 is now called "Exportieren" (`genderTagging.export.title`, German only —
  English's "Export" already doubled as both a noun and the step name); and Export's own "Aggregation
  öffnen" fact-list row — a link into the advanced-only aggregation detail page — is hidden in guided
  mode. `ExportDetailView.vue` and `ReviewWorkbench.vue` both read `interface_mode` directly, matching
  the established per-component pattern.
- **"Statistik & Methoden" is a gender-ratio pie chart in guided mode, not the Auswertungen list**
  (decided after discussion: an evaluation is a separate, manually-created benchmark comparison that
  rarely exists this soon after Schritt 2, so a direct link to "the" evaluation of the current run would
  often show nothing). New `GenderStatisticsView.vue`/`projectGenderStatistics` route resolves the
  project's own working aggregation (ADR-0035) and renders an accessible SVG donut (the CSS-Tricks
  dasharray/dashoffset technique, `aria-hidden`) plus a `<dl>` legend carrying the real counts for
  assistive technology — reusing `reviewProgress()`/`useReviewSummary` exactly as the advanced
  dataset-detail page already does, so no new backend endpoint was needed. Guided mode's sidebar now
  points its "Statistik & Methoden" entry here instead of at `evaluations`; letting this route resolve
  its own aggregation (rather than reading a `runId` out of the URL) let `useSidebarNavigation.ts` drop
  the working-aggregation-fallback machinery (`useAggregation`/`useProject` reads and the
  `needsWorkingAggregationFallback` computed) it had grown for the old evaluations link — a net
  simplification, not just an addition. Advanced mode's Auswertungen feature is untouched.
- **Importing a new dataset in guided mode left Schritt 2 permanently blocked.** Root cause: the
  project's snapshot list (`useSnapshotList`, the source of Schritt 1's "latest ready" dataset) was
  invalidated exactly once, at upload time, while the new snapshot was still `pending` — nothing ever
  told it the import had since finished. `useSnapshotStatus` (`useSnapshotImport.ts`) now invalidates
  the project's snapshot list itself the moment its own poll sees a terminal status, so Schritt 2 picks
  up the newly ready dataset without a reload.
- **A working aggregation can outlive the dataset it was built from.** Once a newer snapshot finishes
  importing, the project's working aggregation still reflects the *previous* one — `isDone` must go back
  to false in that case, the same as if nothing had been generated yet, resetting Schritt 2's
  hint/button and re-locking Prüfen/Export. `GenderTaggingView.vue` now also reads the working
  aggregation's own run (`useRun`) and compares its `dataset_snapshot_id` against the latest ready
  snapshot; a mismatch counts as not-done. This was discussed as one of three options for handling a
  second uploaded dataset in guided mode (give it its own picker; choose a dataset at generate time; or
  always operate on the newest dataset and treat older ones as superseded) — the third was chosen, as
  the only one that keeps the guided flow a single sequential page with no new decision for the user to
  make, and the dataset-history/"Anderen Datenstand wählen" picker already exists as an advanced-only
  concept for anyone who does need it.
- **`SnapshotImportForm.vue`'s own post-success actions ("Daten anzeigen", "weiteres Register
  importieren") are hidden in guided mode.** Both lead to, or duplicate, advanced-only navigation —
  "Daten anzeigen" opens the advanced Datenstand detail page, and Schritt 1's own hint text already
  shows the done state. `GenderTaggingView.vue` remounts the form (an incrementing key) each time
  Schritt 1's own toggle is reopened, so guided mode still has a way to start a second import without
  that button.
- **The inline sign-in on the signed-out home page landed on the now-orphaned `/projects` page,
  duplicating the signed-in home dashboard at `/`.** `GuestHomeView.vue`'s own post-login redirect
  predates D26, from when `/projects` was still the project list a visitor landed on; D26 moved that
  list onto the signed-in home page itself. Changed the hardcoded target from `/projects` to `/`,
  matching `LoginView.vue`'s own default (which already went to `/`, just not this inline form).
- **A nested `.app-card` lost its padding inside a `--sectioned` one.** `.app-card--sectioned` sets
  `--app-card-padding: 0` so it can delegate inset to its own full-width child sections — a CSS custom
  property, which inherits to *any* descendant, including an unrelated plain `.app-card` nested inside
  it (`SnapshotImportForm.vue`, embedded in `GenderTaggingView.vue`'s own sectioned card). Reinstated
  `--app-card-padding: var(--space-4)` on `.snapshot-import-form` itself so it keeps its own inset
  regardless of where it's mounted.
- **Schritt 2 ("Automatische Vorschläge generieren") failed outright, every time, found via direct use
  of the real stack.** Root cause: 7 of the 10 registered methods need real per-method configuration
  (most are lookup methods needing a `lookup_sha256` for a compiled local authority/reference snapshot
  that doesn't exist in this deployment yet; `local_llm` needs configuration too) — the server rejects
  the whole run at creation (`422`) naming exactly one offending method, before any execution is even
  dispatched. Guided mode has no configuration step of its own (D27: one sequential flow, no decisions)
  and previously just sent every registered method with an empty config. `startGenerate()` now retries
  without the one method the server just named, repeating until the run is accepted or no method is
  left — converging on whatever subset this deployment can actually run, with no user-visible decision
  and no backend contract change. (Confirmed by replaying the exact request against the real API with
  curl: only `gender_guesser`, `nomquamgender`, and `parenthetical_qualifier` currently succeed with an
  empty config; the other 7 fail individually.) Advanced mode's own `NewRunForm.vue` already lets a
  user deselect methods and paste per-method JSON config by hand, so it was never broken the same way —
  only guided mode's "select everything automatically" premise was.
- **Even after the retry fix above, generate still looked broken on a reload mid-run.** Found by
  checking the database directly: two runs for the same dataset had both completed successfully in the
  background, with method executions all `completed`, yet no aggregation was ever created for either
  — `GenderTaggingView.vue` only ever tracked an in-flight run (`activeRunId`) as a local ref, so a page
  reload (or, in this real-stack testing session, a dev-container restart) while a run was still going
  silently forgot it; the button went back to offering to start again over a dataset that, moments
  later, actually had results with nothing watching for them. Added a one-shot resume: once the
  project, the working aggregation (if any), and its run have all settled, a `useRunList` query for the
  current dataset's own most recent run adopts it into `activeRunId` if it isn't already reflected by
  the working aggregation — the same auto-create-aggregation and set-working-aggregation watchers that
  already existed then just run as if this page had been there to see it live. Gated on full settlement
  (not just "loaded") specifically to avoid re-adopting an already-aggregated run into a second,
  duplicate aggregation while `isDone` is still momentarily unsettled right after a reload.

Full suite, `typecheck`, `lint`, `i18n:check`, and `unused:check` all clean (same 2 pre-existing Windows
symlink failures as every prior round). Visually verified against the real stack.
