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

The brand continues to link to the publication home page. Projects remains the permanent global entry
point. Current-project groups appear only with a `projectId`. Administrative navigation appears only to a
password-current global administrator.

Export is not a permanent sidebar destination because it requires a particular run and aggregation.
Project membership management likewise belongs to a project-specific administrative action. Do not
recreate the wireframe's unsupported project Settings screen; Publication settings is the separate global
administrative branding surface accepted by ADR-0040.

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
accessible name, visible focus, and `aria-expanded`. Rail destinations use consistent internal SVG icons,
retain accessible names, and expose translated labels through the repository's in-house WAI-ARIA tooltip
pattern. Do not use bare Unicode symbols, flags for language, or color alone.

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
/projects/:projectId/runs/:runId/aggregations/:aggregationId/game
/projects/:projectId/statistics
/admin/settings
```

Suggested names are `aggregationReview`, `aggregationPeople`, `aggregationGame`,
`projectStatistics`, and `adminSettings`. Use explicitly named feature views so placeholders can later be
replaced without route changes: `ReviewQueueView`, `PersonBrowserView`, `GameModeView`,
`StatisticsView`, and `AdminSettingsView`. They may share a small presentational `PlannedView`.

Each placeholder contains only a localized title, a short workflow description, an explicit unavailable
state, safely available context, prerequisites, and a route to the nearest implemented parent. Do not add
mock counts, fabricated charts, fake results, or controls that appear to submit work.

Derive availability from route parameters:

| Destination | Required context |
|---|---|
| Overview and Import | `projectId` |
| Classification | `projectId`, `snapshotId` |
| Review, People and audit, Game mode | `projectId`, `runId`, `aggregationId` |
| Statistics and methods | `projectId`; the future view selects a run/evaluation |
| Publication settings | Eligible global administrator |

When a contextual group is visible but an identifier is missing, render a non-interactive item with a
concise prerequisite. Never invent a partial URL or silently select the newest resource. Use exact
route-name sets for active styling so exactly one leaf item carries `aria-current="page"`.

### Game mode as an administrative setting

Game mode is a deployment-wide feature controlled by a global administrator, not a personal preference or
project setting. The recommended default is disabled until an administrator explicitly enables it.

When disabled:

- non-administrators do not see its navigation item;
- direct navigation fails closed with a clear unavailable state and performs no annotation write;
- review ordering and record selection remain unchanged; and
- existing annotations retain their ordinary append-only meaning.

When enabled, only project members with the role required to annotate may see and enter it. Game mode
remains a presentation layer over the normal review and annotation contracts. Enabling it adds no scores,
streaks, leaderboard, alternative queue, or influence on which records are selected. Its timer remains
independently switchable off as required by frontend decision D19.

ADR-0040 permits exactly six branding overrides and must not be silently expanded. Before implementation:

1. Add a separate ADR defining administrative feature settings, defaults, ownership, authorization,
   persistence, concurrency, read visibility, and failure behavior.
2. Define closed Pydantic contracts with an explicit `game_mode_enabled` boolean rather than an arbitrary
   string-keyed feature-flag map.
3. Decide whether the revisioned administrative resource gains a separate `features` section or whether a
   dedicated feature-settings resource is cleaner. Preserve ADR-0040's branding semantics.
4. Provide a read projection through which ordinary project members can determine availability without
   receiving administrative metadata.
5. Protect mutations with the existing session and CSRF behavior, and reject stale writes with
   `409 Conflict` using a revision.
6. Record who changed the setting and when without logging person data or review content.
7. Regenerate the OpenAPI snapshot and frontend transport from the FastAPI contract.

The Admin settings placeholder may mention the planned option, but it must not show a working toggle before
the ADR, persistence, API, authorization, and generated client exist.

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
People and audit, and Statistics. Reviewers additionally receive Review and, when administratively enabled,
Game mode. Operators additionally receive Import and future Evaluation/Export creation. Global
administrators receive effective operator access plus Administration. These checks improve presentation;
the backend remains authoritative.

### Styling, accessibility, and tests

Add semantic tokens for expanded width, rail width, header height, and transition duration. Use the existing
spacing, colors, radii, typography, and motion tokens. Keep navigation independently scrollable while the
header and preference footer remain reachable. Preserve `min-width: 0` in the content region and prevent
horizontal page scrolling. Width transitions honor `prefers-reduced-motion`.

Automated coverage should include:

- stored, missing, invalid, and unavailable-storage collapse states;
- responsive mode not mutating the desktop preference;
- group/item visibility for every role and resource context;
- unavailable explanations for missing identifiers;
- exactly one current item on every route;
- locale/theme behavior in expanded, rail, and drawer presentations;
- administrator-only Users and Publication settings;
- Game mode hidden and unavailable when disabled;
- Game mode visible only to eligible annotators when enabled;
- drawer focus trap, dismissal, and focus restoration;
- placeholder route resolution and lazy loading; and
- both locales, both themes, reduced motion, and `axe-core`.

Manual verification follows D17: keyboard-only use in both themes and locales, NVDA with Firefox,
VoiceOver with Safari, text-spacing overrides, 400% zoom, and 320 CSS px reflow. Include long German labels,
long display names, footer menus near the viewport edge, and transitions among all responsive presentations.

### Delivery sequence

1. Update the frontend design/delivery documents and accept the Game mode settings ADR.
2. Add shell state, the typed navigation model, exact active matching, icons, and tooltip primitive.
3. Refactor the sidebar into semantic groups and implement expanded/rail behavior.
4. Move locale/theme controls and their tests out of the title bar.
5. Add the medium rail and Dialog-based mobile drawer.
6. Register the five named routes and honest feature-owned placeholders.
7. Deliver Game mode configuration separately: persistence and API first, then regenerated transport,
   administrative control, availability consumption, navigation gating, and tests.
8. Run frontend and repository quality gates plus bounded desktop/mobile visual and accessibility reviews.

Keep these in separate reviewable commits. Do not mix the Game mode backend contract and migration into the
purely presentational sidebar refactor.

### Acceptance criteria

- Desktop collapse works by keyboard and pointer and survives reloads.
- Responsive layout never overwrites the saved desktop choice.
- Language and theme work in expanded, rail, and drawer presentations and leave the title bar.
- Account and session behavior in the title bar is unchanged.
- Every item has a valid target, a clear unavailable state, or correct role/feature-based hiding.
- Review, People and audit, Game mode, Statistics and methods, and Publication settings have stable named
  placeholders without mock data.
- Export remains contextual and the obsolete project Settings view is absent.
- Game mode is disabled by default, enabled only by a global administrator through a revisioned canonical
  API, and never changes review selection or scientific results.
- Exactly one navigation item is current, and the shell passes bilingual, theme, keyboard, screen-reader,
  zoom, reflow, reduced-motion, and automated accessibility checks.
- The sidebar-only increment causes no API drift; the later Game mode setting changes contracts only through
  its accepted ADR and generated transport.

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
