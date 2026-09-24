# Ideas

- Import registers from a Git URL.
- Train a classifier on GND data, bracketed by century and using each person's date of birth.
- Re-run the combined test suite when Docker is healthy, verify coverage of
  `db/repositories/aggregation_repository.py`, and add focused tests if material branches remain uncovered.

## Collapsible contextual sidebar and planned-view placeholders

Replace the current two-link sidebar with the application's durable navigation shell after the active
administrative-panel increment is complete. This is a future implementation strategy, not an approved or
delivered design. Before implementation, reconcile it with `docs/23-wireframe-ui-inventory.md`,
`docs/24-frontend-delivery-plan.md`, and `docs/25-frontend-design-guidelines.md`.

### Goals and navigation model

- Give global, project, evaluation, and administrative destinations a stable hierarchy.
- Tie every private navigation item to the resolved session, global roles, active-project role, required
  resource identifiers, and deployment feature availability.
- Make the sidebar user-collapsible on desktop without conflating the saved preference with responsive
  layout constraints.
- Move language and theme controls from the title bar into the sidebar footer.
- Keep account identity, session errors, sign-in, and sign-out in the title bar.
- Add honest placeholders for accepted but unfinished views, without mock data or fake controls.
- Keep route parameters authoritative for project, snapshot, run, and aggregation context.
- Meet WCAG 2.2 AA in expanded, collapsed, and mobile presentations.

Use this information architecture:

```text
GenderTagger
[Collapse sidebar]

Projects

Current project
  Overview
  Import
  Classification
  Review
  People and audit

Additional (optional and administrator-controlled)
  Game mode

Evaluation
  Statistics and methods

Administration
  Users
  Publication settings

Language
Theme
```

The brand continues to link to the publication home page. Brand, language, and theme remain available
without a session. Projects appears only after the session is ready, the user is signed in, and no forced
password change is pending. Current-project groups additionally require a `projectId` and the resolved
project role. Administrative navigation requires a password-current global administrator.

Export is not a permanent sidebar destination because it requires a particular run and aggregation.
Project membership management likewise belongs to a project-specific administrative action. Do not
recreate the wireframe's unsupported project Settings screen; Publication settings is the separate global
administrative branding surface accepted by ADR-0040.

### Authentication and role visibility

Treat navigation visibility as a derived presentation of authenticated capabilities, not as authorization.
The backend remains authoritative for every request and direct URL.

| Session or role state | Visible navigation |
|---|---|
| Session idle/loading | Brand and preferences; no private links, preventing unauthorized flashes |
| Session error | Brand and preferences; the title bar presents the recoverable session error |
| Signed out | Brand and preferences only; sign-in remains in the title bar |
| Forced password change | Brand and preferences only; private navigation remains suppressed |
| Signed in with current password | Projects, even when the accessible-project list is empty |
| Global operator | Projects; project creation remains an action in the Projects view |
| Global administrator | Projects and Administration; effective operator access inside every project |
| Project viewer | Overview, Classification, People and audit, and Statistics |
| Project reviewer | Viewer items plus Review |
| Project operator | Reviewer items plus Import and future Evaluation/Export creation |

All private navigation waits for
`session.status === "ready" && session.isSignedIn && !session.mustChangePassword`. The global
`operator` role grants project creation but no access to an existing project; project navigation must use
`AccessibleProject.current_user_role`. A global administrator receives the backend-defined effective
project role of operator.

Hide destinations for which the user lacks a role. Show an unavailable item only when the user has the
required role but necessary route context is missing. For example, a viewer never sees Import, whereas a
reviewer may see Review unavailable until an aggregation is selected.

Direct routes must mirror these states: signed-out users go to login with the intended URL preserved,
forced-password-change users go to the password-change flow, known insufficient roles receive a clear
forbidden state or safe parent route, inaccessible resources retain backend-authoritative `403`/`404`
handling.

### Responsive and collapsed behavior

Use three shell presentations:

| Viewport | Presentation |
|---|---|
| At least 1080 CSS px | Persistent sidebar using the user's expanded/collapsed preference |
| 720–1079 CSS px | Compact icon rail, independent of that stored desktop preference |
| Below 720 CSS px | No persistent rail; a title-bar button opens a modal navigation drawer |

Persist only the explicit desktop choice under a namespaced local-storage key such as
`gendertagger.sidebar.collapsed`. Missing, invalid, or inaccessible storage falls back to expanded.
Responsive changes never rewrite it, so returning to a wide viewport restores the user's choice.

Prefer CSS media queries for layout. JavaScript owns only the explicit desktop preference and ephemeral
mobile drawer. Build the drawer with the existing Headless UI Dialog behavior: trap focus, close on Escape,
backdrop activation, or successful navigation, prevent background interaction, and restore focus to the
title-bar trigger.

The collapse control remains visible in both desktop states. It is a native button with a translated
accessible name, visible focus, and `aria-expanded`. Rail destinations use consistent Phosphor icons,
retain accessible names, and expose translated labels through the repository's in-house WAI-ARIA tooltip
pattern. Do not use bare Unicode symbols, flags for language, or color alone.

### Phosphor icon system

Introduce the official `@phosphor-icons/vue` package as the shared application icon source. Import each icon
as a named ESM component at its call site; do not register the complete package globally. This preserves
Vite tree-shaking and avoids shipping unused icon components.

Define one reviewed mapping from navigation/action semantics to Phosphor components. Prefer the regular
weight, `currentColor`, and a token-compatible `em`/`rem` size unless a documented component state needs
another weight. Do not change weight merely for decoration or mix unrelated icon styles within the shell.

Icons accompanying visible text are decorative and use `aria-hidden="true"`. Icon-only buttons retain
their accessible name on the button; the SVG is not the accessible label. Tooltips supplement rather than
replace that name. Never infer state, role, or scientific meaning from an icon alone.

Adding the package requires updating `frontend/package.json` and `frontend/package-lock.json`, recording
its licence in the existing dependency review/SBOM path, and verifying the production bundle. Update the
frontend dependency-budget decisions in `docs/24-frontend-delivery-plan.md` and
`docs/26-frontend-coding-guidelines.md`: Phosphor is a presentational icon dependency and does not replace
or expand the single behavioral overlay dependency established by D9.

### Language and theme controls

Reuse `useLocale`, `useTheme`, and `AppListbox`. Move their rendered controls from `AppHeader` into a
sidebar footer:

- expanded sidebar and mobile drawer: labeled Language and Theme listboxes;
- compact rail: accessible icon triggers that open the same choices;
- option panels near the viewport bottom open upward and are not clipped; and
- system, light, and dark remain the theme choices.

Keep existing preference state and storage keys. Remove only their header presentation. Header tests then
cover session behavior, while sidebar tests own locale and theme interaction.

### Routes and placeholders

Retain the implemented project, import, run, and aggregation routes. Add named routes and thin placeholder
views for:

```text
/projects/:projectId/runs/:runId/aggregations/:aggregationId/review
/projects/:projectId/runs/:runId/aggregations/:aggregationId/people
/projects/:projectId/statistics
/admin/settings
```

Suggested route names are `aggregationReview`, `aggregationPeople`, `projectStatistics`, and
`adminSettings`. Use explicitly named feature views so placeholders can later be replaced without route
changes: `ReviewQueueView`, `PersonBrowserView`, `StatisticsView`, and `AdminSettingsView`. They may
share a small presentational `PlannedView`.

Each placeholder contains only a localized title, a short workflow description, an explicit unavailable
state, safely available context, prerequisites, and a route to the nearest implemented parent. Do not add
mock counts, fabricated charts, fake results, or controls that appear to submit work.

Derive availability from route parameters:

| Destination | Required context |
|---|---|
| Overview and Import | `projectId` |
| Classification | `projectId`, `snapshotId` |
| Review and People and audit | `projectId`, `runId`, `aggregationId` |
| Statistics and methods | `projectId`; the future view selects a run/evaluation |
| Publication settings | Eligible global administrator |

When a contextual group is visible but an identifier is missing, render a non-interactive item with a
concise prerequisite. Never invent a partial URL or silently select the newest resource. Use exact
route-name sets for active styling so exactly one leaf item carries `aria-current="page"`.

### State, roles, and component ownership

Use a small shell-level Pinia store for `isDesktopSidebarCollapsed` and
`isMobileNavigationOpen`. Persist only the first value. Server state, project roles, and feature
availability remain in the query cache; route parameters remain the resource-context authority.

Build one typed navigation model from route context, session state, current-project role, feature
availability, and translations. Share it between the persistent sidebar and mobile drawer. Each item records
its label, icon, valid target or unavailable state, visibility, explanation, and exact active route names.

A practical component split is:

```text
AppSidebar
  SidebarHeader
  SidebarNavigation
    SidebarGroup
    SidebarItem
  SidebarPreferences
  SidebarTooltip

MobileNavigationDrawer
  shared sidebar content
```

Centralize role comparisons in a presentation helper. Viewer destinations are Overview, Classification,
People and audit, and Statistics. Reviewers additionally receive Review. Operators additionally receive
Import and future Evaluation/Export creation. Global administrators receive effective operator access plus
Administration. These checks improve presentation; the backend remains authoritative.

### Styling, accessibility, and tests

Add semantic tokens for expanded width, rail width, header height, and transition duration. Use the existing
spacing, colors, radii, typography, and motion tokens. Keep navigation independently scrollable while the
header and preference footer remain reachable. Preserve `min-width: 0` in the content region and prevent
horizontal page scrolling. Width transitions honor `prefers-reduced-motion`.

Automated coverage should include:

- stored, missing, invalid, and unavailable-storage collapse states;
- no private navigation during session loading, session failure, signed-out, or forced-password-change
  states;
- global navigation derived from global roles and project navigation derived from
  `AccessibleProject.current_user_role`;
- responsive mode not mutating the desktop preference;
- group/item visibility for every role and resource context;
- unavailable explanations for missing identifiers;
- exactly one current item on every route;
- locale/theme behavior in expanded, rail, and drawer presentations;
- administrator-only Users and Publication settings;
- drawer focus trap, dismissal, and focus restoration;
- placeholder route resolution and lazy loading; and
- both locales, both themes, reduced motion, and `axe-core`.

Manual verification follows D17: keyboard-only use in both themes and locales, NVDA with Firefox,
VoiceOver with Safari, text-spacing overrides, 400% zoom, and 320 CSS px reflow. Include long German labels,
long display names, footer menus near the viewport edge, and transitions among all responsive presentations.

### Delivery sequence

1. Update the frontend design/delivery documents and confirm the sidebar route and visibility model.
2. Add shell state, the typed navigation model, exact active matching, named Phosphor imports, and the
   tooltip primitive; update and lock the frontend dependency.
3. Refactor the sidebar into semantic groups and implement expanded/rail behavior.
4. Move locale/theme controls and their tests out of the title bar.
5. Add the medium rail and Dialog-based mobile drawer.
6. Register the four named sidebar-plan routes and honest feature-owned placeholders.
7. Run frontend and repository quality gates plus bounded desktop/mobile visual and accessibility reviews.

Keep these steps in separate reviewable commits. The separate Game mode plan below owns its backend
contract, persistence, route, placeholder, administrative control, and feature-specific verification.

### Acceptance criteria

- Signed-out, loading, error, and forced-password-change states expose no private navigation.
- Global and project navigation visibility follows global roles and the active project's effective role,
  while backend authorization remains authoritative.
- Desktop collapse works by keyboard and pointer and survives reloads.
- Responsive layout never overwrites the saved desktop choice.
- Language and theme work in expanded, rail, and drawer presentations and leave the title bar.
- Account and session behavior in the title bar is unchanged.
- Every item has a valid target, a clear unavailable state, or correct role/feature-based hiding.
- Review, People and audit, Statistics and methods, and Publication settings have stable named placeholders
  without mock data. Game mode follows its separate plan.
- Export remains contextual and the obsolete project Settings view is absent.
- Phosphor icons are directly imported, tree-shaken, decorative to assistive technology where labels exist,
  and never used as the only indication of state or permission.
- Exactly one navigation item is current, and the shell passes bilingual, theme, keyboard, screen-reader,
  zoom, reflow, reduced-motion, and automated accessibility checks.
- The sidebar-only increment causes no backend or generated-contract drift.

## Administrator-controlled Game mode

Treat Game mode as a separate future increment whose only coupling to the sidebar is a feature-dependent
navigation item. It is a deployment-wide capability controlled by a global administrator, not a personal
preference or project setting. The recommended default is disabled until an administrator explicitly
enables it.

### Product and scientific boundaries

When disabled:

- non-administrators do not see its navigation item;
- direct navigation fails closed with a clear unavailable state and performs no annotation write;
- review ordering and record selection remain unchanged; and
- existing annotations retain their ordinary append-only meaning.

When enabled, only project members with at least the reviewer role may see and enter it. A global
administrator has the backend-defined effective project role of operator. Game mode remains a presentation
layer over the normal review and annotation contracts. Enabling it adds no scores, streaks, leaderboard,
alternative queue, or influence on which records are selected. Its timer remains independently switchable
off as required by frontend decision D19.

### Administrative setting and API prerequisites

ADR-0040 permits exactly six branding overrides and must not be silently expanded. Before implementation:

1. Add a separate ADR defining administrative feature settings, defaults, ownership, authorization,
   persistence, concurrency, read visibility, and failure behavior.
2. Define closed Pydantic contracts with an explicit `game_mode_enabled` boolean rather than an arbitrary
   string-keyed feature-flag map.
3. Decide whether the revisioned administrative resource gains a separate `features` section or whether a
   dedicated feature-settings resource is cleaner. Preserve ADR-0040's branding semantics.
4. Provide a read projection through which ordinary project members can determine availability without
   receiving administrative metadata. Do not infer availability from a missing sidebar item.
5. Protect mutations with the existing session and CSRF behavior, and reject stale writes with
   `409 Conflict` using a revision.
6. Record who changed the setting and when without logging person data or review content.
7. Regenerate the OpenAPI snapshot and frontend transport from the FastAPI contract.

The Admin settings view may name Game mode as planned, but it must not show a working toggle before the ADR,
persistence, API, authorization, and generated client are delivered.

### Route, placeholder, and sidebar integration

Reserve this named route for the future presentation:

```text
/projects/:projectId/runs/:runId/aggregations/:aggregationId/game
```

Use the route name `aggregationGame` and an explicitly owned `GameModeView`. Before the actual experience
is implemented, the view may use the shared `PlannedView` presentation with a localized title, an explicit
not-yet-available state, its aggregation context, prerequisites, and a route back to the aggregation.

The sidebar renders Game mode only when all of these are true:

- the session is ready, signed in, and not subject to forced password change;
- the deployment setting is enabled;
- the active project role is reviewer or operator, including an administrator's effective operator role;
- `projectId`, `runId`, and `aggregationId` are present; and
- the selected aggregation is a valid accessible resource.

If the role and feature are available but aggregation context is missing, the project navigation may show
a non-interactive item explaining that an aggregation must be selected. When the feature is disabled or the
user lacks the reviewer role, hide the item. Direct access still relies on backend authorization and the
feature-availability contract.

### Delivery sequence

1. Accept the feature-settings ADR and update the implementation and frontend delivery plans.
2. Add persistence, repository/service behavior, revisioned Pydantic commands and reads, authorization,
   CSRF handling, audit attribution, migrations, and API tests.
3. Publish the authenticated availability projection, update the OpenAPI snapshot, and regenerate the
   frontend transport.
4. Add the administrator control with effective/default state, stale-write recovery, storage-failure
   handling, and mounted-consumer refresh.
5. Add `aggregationGame`, its feature-owned placeholder, and direct-route disabled/forbidden states.
6. Integrate the feature and role checks into the typed sidebar navigation model.
7. Implement the annotation presentation without scoring or alternate record selection; keep the timer
   switchable off before the first timed round.
8. Run backend, contract, frontend, end-to-end, and accessibility verification as separate reviewable
   changes.

Do not mix the backend setting and migration into the presentational sidebar refactor.

### Verification and acceptance

Automated and integration coverage must verify:

- disabled is the persisted/default behavior for a fresh deployment;
- only a global administrator can change the setting;
- CSRF, validation, revision conflicts, storage failures, and attribution follow established contracts;
- ordinary eligible project members can read availability without administrative metadata;
- disabled Game mode is hidden and direct access performs no annotation request;
- enabled Game mode is visible only to reviewers, operators, and administrators with project access;
- missing aggregation context produces an explanatory unavailable state rather than a partial URL;
- enabling or disabling the feature refreshes mounted sidebar and route consumers;
- annotations use the existing append-only contract and concurrency behavior;
- Game mode does not change queue ordering or record selection; and
- disabling the timer preserves the same annotation path and writes.

The increment is complete when Game mode is disabled by default, can be enabled only by a global
administrator through a revisioned canonical API, is exposed only to eligible project annotators, and
cannot influence scientific results, review ordering, or record selection.

## Streamlined deployment and data/model provisioning

Make deployment and provisioning of required data and models simpler and more user-friendly. Aim for
a clear path from a fresh installation to a ready-to-use instance, with fewer manual commands and less
knowledge of internal services or filesystem layouts required.

Potential improvements:

- Provide a guided setup workflow and one coherent guide for installation, updates, and provisioning.
- Explain which datasets and models each method needs, which are optional, and their storage and
  hardware requirements.
- Simplify downloading or importing assets, validating them, and making them available to the relevant
  services, while preserving version/checksum provenance and respecting licensing requirements.
- Show what is ready, missing, or misconfigured, with actionable next steps and safe retries.

Keep local/private and offline provisioning supported. This is a future improvement idea, not an
approved implementation design.

## Publication checklist

### Release identity and archival

- [ ] Keep the development version at `0.0.0`; set `0.1.0` for the first public, citable release.
- [ ] Create and verify an annotated `v0.1.0` tag from the exact reviewed commit.
- [ ] Add release notes covering supported workflows, limitations, deferred features, breaking changes, and migration policy.
- [ ] Provide citation metadata and an archival release/DOI for scholarly software publication.
- [ ] Record the release commit, image digests, lockfile checksums, and SBOMs with release artefacts.

### Database and deployment

- [ ] Decide the migration cutoff before squashing; no deployed database currently needs a compatibility path.
- [ ] Create a fresh-install migration baseline and test it against an empty PostgreSQL database.
- [ ] Rehearse upgrade, backup, restore, and rollback/recovery before the first shared deployment.
- [ ] Verify a clean checkout can install, provision assets, build images, migrate, and start the documented stack.

### Verification and security

- [ ] Run the complete CI-equivalent matrix: fast, PostgreSQL, Redis, frontend, package-build, contract, and deployment checks.
- [ ] Exercise one supported end-to-end workflow using sample data: import → run → aggregation → review → export.
- [ ] Run locked dependency and image vulnerability scans; resolve or document accepted findings.
- [ ] Run secret and sensitive-content checks; confirm no credentials, private corpora, personal data, databases, model weights, or unintended build artefacts are tracked.
- [ ] Verify the OpenAPI snapshot and generated frontend transport are current.

### Documentation and language

- [ ] Review `PLAN.md`, milestone statuses, README, deployment guide, and deferred-scope statements for accurate current status.
- [ ] Apply the English-language policy to technical documentation, identifiers, diagnostics, and release notes; retain original-language quotations only where necessary.
- [ ] Publish a concise quickstart with prerequisites, local/private deployment, asset provisioning, first workflow, and troubleshooting.
- [ ] Document method and data-model limitations, uncertainty semantics, evaluation boundaries, and non-goals.
- [ ] Review legal notice, privacy wording, accessibility statement and feedback ownership, licence text, and third-party attribution.

### Sample data and reproducibility

- [ ] Provide a small, licensed, synthetic or explicitly cleared sample dataset; never ship unapproved editorial or personal data.
- [ ] Include a documented expected workflow and deterministic expected outputs/checksums.
- [ ] State sample provenance, licences, generation process, and applied transformations.
- [ ] Ensure sample data exercises supported input formats and the intended offline demonstration path without external services or models.
- [ ] Record exact method assets, model revisions, authority snapshots, and checksums needed to reproduce published results.

### Repository polish

- [ ] Remove abandoned scaffolding, stale documentation branches, dead code, obsolete fixtures, and generated artefacts not intended for release.
- [ ] Review `.gitignore`, distribution manifests, Docker contexts, and package contents so only intended artefacts ship.
- [ ] Consolidate duplicated instructions and make one command or document authoritative for each operational task.
- [ ] Verify licences for code, dependencies, datasets, models, authority snapshots, and bundled assets.

**Migration risk.** Squashing is safe now because no external environment depends on the development-only
chain. Once the baseline is committed, preserve it and provide a documented upgrade or rebuild procedure
before any shared deployment.
