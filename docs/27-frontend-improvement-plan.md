# Frontend improvement plan

## Purpose and status

This is the improvement roadmap for the existing Phase 8 client, prepared on 2026-09-25.
It separates shared foundations, the global header, individual views, and the sidebar. Following the
user's accepted header decisions, H1 proceeds after shared implementation and before the view pass.
Its bounded sidebar move places project switching above project destinations; broader sidebar work
comes last, once the views' navigation needs are settled.

The [implementation plan](15-implementation-plan.md) remains authoritative for scope and exit criteria.
The [delivery plan](24-frontend-delivery-plan.md) records capabilities and accepted decisions;
the [design guidelines](25-frontend-design-guidelines.md) govern presentation and accessibility.
The package sequence below remains the roadmap; implementation evidence and pending work are recorded
separately below.

Inputs are the local `audit.md` and saved frontend critique
`.impeccable/critique/2026-09-25T12-21-09Z__frontend-src.md`, checked against source at `d24f541`.
Their findings are summarized below so execution does not depend on local report artifacts.
The critique predates the latest sidebar and landing-page changes. The audit sampled six routes;
it does not establish that every other route is either sound or defective.

The first three increment records below preserve their validation at delivery; the later H1 record
supersedes their header placement/proposal status and the original ordering.

## First increment — 2026-09-25

**G1 first batch implemented; live verification pending.** The shell now has a localized first-focus
skip link that focuses a stable routed-content wrapper without changing route/query state or adding a
nested main landmark. Review keyboard hints announce the localized key text without invalid `kbd` ARIA.
Canonical product spelling is lowercase in both catalogues and the browser title.

Critical foregrounds now use a separate `--critical-text` token. Its contrast on page/panel/raised
surfaces is 4.98/5.62/5.47 in light and 6.18/5.59/5.03 in dark. Critical fills and borders keep their
existing values; destructive-button inverse text remains verified in both themes. The design guidelines
and token tests record the actual pairings.

The frontend regression suite passes all 1,066 tests with 82.7% branch coverage. Lint, formatting,
type checking, locale completeness, generated-transport drift, and the production build pass. Focused
regressions cover skip-link focus across routes and the prohibited-ARIA rule, including incomplete axe
results. Locked backend policy checks, Ruff, mypy/Pyright, Import Linter, package build/distribution,
and 1,343 fast tests also pass (71.79% coverage, above the separate 70% fast-suite floor). Service
integration suites and the combined coverage gate were not rerun for this frontend-only change.
Live keyboard/scroll/focus and desktop/mobile visual checks remain pending: this session had no connected
browser and could not open Chrome. These automated results do not close the live checks.

**H0 proposal drafted for review.** The [header content proposal](frontend-header-proposal.md) provides
a recommended purpose, ownership/source tables, route/state matrix, desktop/mobile compositions, and
open decisions. It proposes explicit project identity/switching on project routes, stable session
access, and page-owned scientific/task context. No header composition or sidebar relocation is approved
or implemented by that proposal.

The responsive containment/control-sizing follow-up is recorded below. V view improvements, H1 header
implementation, and S1 sidebar work remain pending.

## Second shared increment — 2026-09-25

**G1 responsive containment and control sizing implemented; live verification pending.** Shared buttons,
fields, and listbox controls now use a 2rem minimum, rising to 2.75rem below 720 CSS px or with a coarse
pointer. Native single-line controls follow the same sizing, and fieldsets/legends can shrink and wrap.
Narrow gutters, shrinkable children, and wrapping identifiers are applied to representative review,
person-record, and account-administration surfaces.

Review columns now depend on the available workbench width after sidebar/padding, stacking below 57rem.
Evidence and person-record facts share a label/value layout that stacks below a 24rem container width.
`AppScrollRegion` contains review-method, account-directory, and branding tables with a localized name,
conditional keyboard tab stop, and visible associated scroll hint. It remeasures viewport and slotted
content changes and cleans up resize observations. Table minimum widths preserve readable columns;
V1 still owns a possible stacked evidence presentation and separate mobile list/detail navigation.
The existing project menu is bounded by the header, and preference-menu minimum widths are capped for
enlarged text. These are containment repairs to existing controls, with no H0 content decisions applied.

The complete frontend suite passes 1,072 tests across 69 files with 82.66% branch coverage. The six new
scroll-region regressions cover both locales, fitting/overflowing content, focus, resize/async updates,
cleanup, and axe semantics. Lint, formatting, type checks, 947-key catalogue parity, generated-transport
checks, and production build pass. Final menu bounds also receive the existing shell/menu regression
checks. The unchanged backend retains the first increment's validation evidence above.

Live 320/390px and enlarged-text geometry, menu placement, keyboard scrolling, and focus visibility
remain unverified because no browser is connected in this session. jsdom dimension stubs test the scroll
component's behavior; they do not prove rendered containment. The audit's review/account overflow findings
therefore remain open for live confirmation. The following increment addresses route-transition focus
and reusable feedback/convention work; the entire G1 package still needs live verification.

## Third shared increment — 2026-09-25

**G1 focus, feedback, and page conventions implemented; live verification pending.** The shell now owns
one focus transfer to the stable routed-content wrapper after a confirmed pathname change, including
resource-parameter changes and redirects. Initial router resolution, failed/duplicate navigation,
background updates, and ordinary query/hash changes preserve focus. A local control used before a
scheduled transfer keeps focus; automatic query hydration from the shell still permits page entry.
Active modal dialogs retain focus ownership. Superseded callbacks and the router hook are cleaned up.
The mobile drawer's ordinary dismissal still restores its trigger; successful page navigation settles
on content after the drawer closes. Async headings/data never trigger a second focus transfer.

`AppFeedback` provides common inline message/action layout with explicit static, polite, or assertive
announcements and an independent critical-text tone. Recovery controls sit outside the live message.
Representative consumers cover project loading/retry, persistent personal-settings status/error/conflict
feedback, review permission/error explanations, and bulk progress/summary. Existing mutation handlers,
revision checks, conflict focus, saved-decision focus, and per-person partial results remain intact.

The design and coding guidelines now specify page-entry focus, live-region ownership, one route H1 with
subordinate headings, task-local actions, and content width appropriate to forms, reading, or comparison.
Views that omit H1 during pending/error states and remaining adoptions of shared feedback belong to
their V-family improvements; those views are not marked redesigned by this shared batch.

The complete frontend suite passes 1,091 tests across 71 files with 82.79% branch coverage. New coverage
includes 13 route-focus regressions and six bilingual feedback regressions, plus real drawer-navigation
focus assertions. Lint, formatting, type checks, catalogue parity, generated-transport checks, production
build, documentation policy, and patch whitespace checks pass. The backend is unchanged and retains the
first increment's validation evidence.

A fresh browser inventory still has no connected browser, so live keyboard/focus visibility,
screen-reader announcements, and mobile/enlarged-text visual checks remain open. The shared implementation
is ready for that verification; G1 acceptance is not closed solely on automated tests.

## Header increment — 2026-09-25

**H1 implemented; live verification pending.** The [accepted header brief](frontend-header-proposal.md)
replaces the earlier proposal. Short, authorized breadcrumbs identify project/location without fetching
scientific ancestry solely for the shell. The account name opens Personal settings and Sign out.
Project switching now sits above project destinations in the sidebar; the collapsed rail has a named
control and tooltip, and mobile uses the same control inside the drawer. Language/theme remain below.

Both shell locations share the existing principal-scoped project query. Pending/error/access-loss states
clear old identity and provide an appropriate route out or retry. Account/session failures remain
truthful; delayed logout responses cannot clear a replacement session or redirect its user.

A shared leave dialog consults view-owned draft registrations before pathname/resource changes and
sign-out. Stay, failed navigation and failed sign-out preserve input. Successful navigation/logout
clears discarded input; successful saves reset baselines, with later edits preserved. Registrations
cover review/bulk, import, project/run/aggregation/evaluation/export creation, personal/branding
settings, account create/edit and team create/rename. Query/hash state retains existing behavior;
same-person review filter refreshes now preserve the mounted detail. Submitted work remains persisted;
leaving bulk review stops later people after its current submission. Broader view redesign is pending.

The complete frontend suite passes **1,203 tests across 75 files**, with **83.6% branch coverage**.
Lint, formatting, type checks, 960-key catalogue parity, generated-transport drift, production build,
documentation policy and patch whitespace checks pass. Bilingual integration regressions verify real
review-draft switching through the mobile drawer and cancelled account-menu navigation, including
menu closure, preserved input and restored/destination focus. Project query observation avoids a late
extra refetch when the switcher appears. Menu links explicitly close before router navigation.

A single Impeccable static scan reports only the pre-existing sidebar width transition, already assigned
to S1; no additional shell finding was reported. The backend is unchanged and retains the first
increment's validation evidence. A fresh browser inventory has no connected browser. Live menu geometry,
mobile/enlarged text, keyboard visibility and assistive-technology checks remain pending. Automated
checks alone do not close H1 or G1 acceptance.

## Project-menu visibility follow-up — 2026-09-25

A user reported that the expanded desktop project menu was not visible. Its fixed popup was still
inside the sticky sidebar's stacking context, and positioning began with a zero-height cap. Desktop now
renders the popup through a body portal and measures the actual Headless UI menu element after opening,
with a usable initial height cap. Mobile keeps the popup inside its dialog. Switching into mobile or
opening session recovery removes the desktop popup; a hidden trigger does not retain keyboard focus.

All 104 focused navigation tests and 56 account/focus/draft-navigation regressions pass, along with
formatting, lint, type checking, production build, documentation policy and whitespace checks. Added
coverage checks portal placement, bounded positioning with viewport-edge fixtures, cleanup, breakpoint
focus, recovery and existing mobile draft departures. No browser is connected for rendered verification.

## Compact public shell — 2026-09-25

Signed-out users no longer see an empty sidebar or mobile navigation drawer. The compact header has a
home brand, sign-in/session controls and the existing language/theme controls with downward menus.
The controls share a row beneath the brand/account at phone widths. Loading, failed-session and
password-change-required states use the same public layout until private navigation is eligible.
Login restores the working sidebar; logout removes it and closes any drawer. Anonymous preference
storage, temporary choices and canonical account preferences retain their existing ownership.

The complete frontend suite passes **1,235 tests across 75 files**, with **83.78% branch coverage**.
Lint, formatting, type checking, 960-key locale parity, transport drift, production build,
documentation and whitespace checks pass. Coverage includes session loading, sign-in/out transitions,
anonymous header controls, mobile drawer teardown and ignored late preference saves after logout.
The project-list button import was also restored after validation exposed unresolved component
warnings. The backend is unchanged. A fresh browser inventory remains empty, so rendered desktop/mobile
and enlarged-text verification is still pending.

## Workstreams and ownership

| Workstream | Owns | Deliverable |
|---|---|---|
| G — Shared foundations | Accessibility, responsive primitives, tokens, focus, control sizing, common feedback and content conventions | Reusable rules and components applied across the application |
| V — Individual views | The user's task, information hierarchy, local actions, forms, evidence, and view-specific states | A reviewed and improved version of every existing route family |
| H — Global header | Its purpose, contents, global context, account/session controls, and mobile navigation entry | A content brief followed by an implemented header |
| S — Sidebar | Navigation hierarchy, route ownership, context prerequisites, expanded/rail/drawer behavior, and footer utilities | A coherent navigation surface implemented after H and V |

Accessibility and mobile behavior remain acceptance criteria for every workstream. G establishes shared
solutions; it cannot certify layouts that V, H, and S have not yet changed. Assign a defect once:
G owns the error-text token, for example, while each view verifies its actual usage.

Preserve the existing Annotated Archive visual language and generated `/api/v1` contracts. Filtering,
sorting, pagination, permissions, and resource lifecycles remain server-authoritative. Scientific labels,
method confidence, authority behavior, review revisions, provenance, and append-only annotations retain
their current semantics. A proposal changing those semantics requires the governing design-document
update and an ADR before implementation.

## Delivery sequence

Sizes express relative scope, not time estimates. Each package can contain multiple narrow changes;
individual view families should remain independently reviewable.

| Order | Package | Size | Dependency and completion evidence |
|---|---|---|---|
| 0 | Baseline and header content brief (H0) | M | Recheck dated findings; inventory routes and shell content; record header/page/sidebar responsibilities and unresolved decisions |
| 1 | Shared foundations (G1) | M | Can proceed alongside H0; confirmed accessibility and containment defects fixed using shared patterns |
| 2 | Global header implementation (H1) | M | Accepted breadcrumbs/account-menu model, sidebar project switching, and view-owned draft protection; live verification remains |
| 3 | View improvements (V1–V7) | L | Use G1 and H1 responsibilities; complete each family with its own state and responsive checks |
| 4 | Sidebar implementation (S1) | M | H1 and view navigation needs settled; implement navigation and utility organization last |
| 5 | Integrated verification and closeout (Q1) | M | Verify assembled workflows, close findings with evidence, and update status documentation |

H0 established responsibilities before composition. The user selected breadcrumbs and a header account
menu, with project switching in the sidebar, and brought H1 before the view pass. These bounded moves
are part of H1; broader S1 hierarchy and animation work stays last. The header is not sticky.
Urgent shared defects in the shell remain G1 work.

## Baseline and finding register

Use three evidence states: **reported** (observed by a supplied review), **recheck** (later changes may
have resolved it), and **inspect/design** (a planned review or product decision, not a proven defect).
Reproduce a reported issue in the current target state before changing it. Record closure with route,
locale/theme, viewport or interaction, and verification result; aggregate scores are not acceptance.

| Finding | Evidence | Owner | Planned response |
|---|---|---|---|
| A11Y-01: no skip navigation | Reported; absent in current `App.vue` | G1 | First-focus skip link, stable focus target, preserve route main landmarks |
| A11Y-02: critical text on page is 4.254:1 in light theme | Reported by both reviews | G1 | Readable critical text; verify actual page/panel and destructive-button pairs in both themes |
| RESP-01: review document expands to 470px at 320/390px, worse with enlarged text | Reported by both reviews | G1 + V1 | Shared containment pattern, then review-specific evidence and task layout |
| A11Y-03: accessible names directly on four `kbd` elements | Reported | G1 | Correct markup while retaining understandable shortcut announcements |
| RESP-02: account directory overflows at 200% text | Reported | V6 | Remove inflexible mobile minimums and verify enlarged-text forms/actions |
| RESP-03: small mobile controls | Reported | G1, consumed by V/H1/S1 | Establish target sizing centrally and verify actual controls |
| PERF-01: sidebar width transition | Reported | S1 | Remove layout-property animation or use suitable inner-element motion |
| INT-01: uppercase product spelling | Reported by both reviews | G1 | Canonical `gendertagger` in metadata, locales, and accessible text |
| INT-02: one accent border represents different evidence states | Reported | V1 | Explicitly labelled authority/conflict/error treatments |
| Critique P1: preference failure and untranslated collapse label | Recheck after sidebar update | H0 baseline, then G/V7/S as appropriate | Reproduce request/retry states; the translation already exists in current catalogues |
| Critique P1/P2: filters/list separate case, evidence, and decision | Reported | V1 | Design task continuity and advanced-filter disclosure |
| Critique P2: branding values and editing controls are duplicated | Reported | V6 | Bring effective value, fallback, override, and editing together per field |
| Header purpose and contents | User-requested design work | H0/H1 | Decide responsibilities before composition |
| Remaining routes | Inspect/design | V2–V7 | Inspect and define specific changes per view before implementation |

Baseline work also records documentation inconsistencies relevant to the next slice. Examples include
older pending-project/membership claims despite implemented forms, and conflicting descriptions of
keyboard access to disabled navigation. Resolve the applicable specification before changing behavior;
do not interpret stale descriptions as requests to rebuild delivered features.

## G1 — Shared foundations

- Establish skip navigation and route-transition focus behavior without nested main landmarks or
  repeated focus changes during background refreshes.
- Correct semantic critical-text pairings and test the backgrounds actually used. Preserve inverse text
  contrast on destructive filled buttons.
- Define responsive containment once: shrinkable flex/grid children, wrapping identifiers and long
  translations, stacked label/value groups, and labelled keyboard-scrollable regions for genuinely
  two-dimensional tables. Never hide page overflow to conceal inaccessible content.
- Establish control sizing centrally. Aim for 44px standalone mobile targets; retain the documented
  24px accessibility minimum and assess exceptions deliberately. Compact vocabulary badges are not
  buttons and should not be enlarged because of false-positive detector warnings.
- Standardize loading, retry, saved, conflict, permission, and partial-failure presentation where common
  components help. Preserve each resource's distinct state and mutation semantics.
- Correct shortcut semantics, canonical product spelling, and bilingual accessible labels.
- Define page-heading, local-action, and content-width conventions; preserve one H1 per view and keep
  route-specific operations out of shared shell code.

**Exit:** keyboard users can bypass the shell; critical text meets the documented contrast target;
shared controls and containment work in both themes/locales and at narrow/enlarged-text sizes.
Representative review and administration screens consume these patterns before the rest of V proceeds.

## V — Individual view improvements

Each view gets a short brief before editing: primary task, essential information, primary action,
secondary controls, desktop/mobile order, states, and interaction with the shell. Reuse G1 rather than
adding route-specific versions of the same primitive. For views without established findings, the
following defines inspection and design scope, not a claim that their current UI is broken.

| Order | Views and route names | Work to resolve | Acceptance specific to the view |
|---|---|---|---|
| V1 | Review (`review`) | Keep selected person, evidence, decision, and history connected. Reduce initially exposed filters; include active count and reset. Resolve mobile list/detail navigation, evidence table versus stacked records, and save/continue behavior. | No clipped method outcome or confidence; returning to queue preserves context; save, defer, bulk partial results, and revision conflicts remain explicit; sticky controls never obscure focus |
| V1 | Person browser (`people`) | Apply shared record/evidence improvements while preserving the browser's different browse/history task and default query behavior. | Source, predictions, final decision, and append-only history remain reachable with stable person identity; no silent filter/sort changes |
| V2 | Projects (`projects`) and overview (`projectOverview`) | Review reopening existing work versus creation; clarify project/snapshot/run relationships, readable versus management-only projects, and next available actions. | Existing work is easy to reopen; creation remains discoverable; empty/populated projects, eligible-team/manager selection, unavailable stages, and long names remain understandable |
| V3 | Import (`projectImport`) | Review format/profile/configuration grouping, file selection, validation, persisted progress, and recovery. | Users understand what will be imported, can fix errors, and can resume monitoring a persisted import; format/file limits stay visible |
| V3 | Runs and aggregation (`snapshotRuns`, `runDetail`, `aggregationDetail`) | Review method selection, advanced configuration, provenance disclosure, progress/partial errors, aggregation selection, and next actions. | Pending/running/terminal states remain distinct; users understand selected snapshot/methods and execution versus aggregation; navigation retains resource context |
| V4 | Evaluation (`evaluations`, `evaluationDetail`) | Review creation versus history, metric explanations, comparison hierarchy, table density, and narrow-screen matrices. | Definitions and denominators remain correct; chart alternatives and full matrices remain accessible; no invented cross-method confidence score |
| V4 | Export (`exports`, `exportDetail`) | Review format choices, source/review context, lifecycle, manifest/provenance access, and download feedback. | Export source is unambiguous; incomplete/failed exports cannot appear downloadable; completed artifacts remain inspectable and downloadable |
| V5 | Home (`home`), legal notice (`legalNotice`), footer, not-found (`notFound`) | Recheck recently changed home; distinguish public explanation from signed-in entry, validate publication hierarchy and recovery links. | Public information remains accessible signed out; configured/missing/unavailable branding stays truthful; no invented institutional facts |
| V6 | Accounts (`adminUsers`) | Fix enlarged-text overflow; review directory versus selected-account actions, creation/editing, role controls, security actions, and confirmations. | Account/action scope stays obvious; errors preserve recoverable inputs; narrow controls and contained table scrolling remain usable |
| V6 | Teams and membership (`adminTeams`, `projectMembers`) | Review team/list/roster relationships, candidates, project-role changes, and manager transfer as existing capabilities. | Admin/manager/member boundaries are clear; access loss clears stale context; transfer/removal consequences remain visible |
| V6 | Branding (`adminSettings`) | Unify each field's effective value, fallback, override status, and edit disclosure; group Save/Discard with a changed-field summary. | Set, clear, unchanged, and reset remain distinct; equal-valued overrides, dirty drafts, conflicts, uncertain outcomes, and public-refresh failure are preserved |
| V7 | Personal settings (`userSettings`) | Recheck preferences after shell changes; distinguish saved values, local drafts, defaults, and failure/reload states. | Locale/theme/collapse use existing revision checks; account switching and anonymous choices remain isolated |
| V7 | Authentication (`login`, `changePassword`, shared session-recovery dialog) | Review field/error hierarchy, return destination, forced password change, and preservation of interrupted work. | Keyboard/autofill/password-manager paths work; recovery retains eligible drafts and never silently replays protected mutations |

V1 is first because it is both the core task and the strongest overlap between the reports; review and
people share `ReviewWorkbench`. V2–V4 follow the operator workflow. V5–V7 complete route coverage.
Independent view work can run in parallel once G1 patterns and H0 responsibilities are stable.

For V1, resolve mobile task structure against the existing requirement for separate list/detail views
below 720px. The audit suggests a contained table; the critique suggests stacked method records and
reordered content. Choose a coherent presentation rather than automatically implementing both. Record
the selected interaction in the design guidelines before implementation. Summaries expose existing
evidence; they do not compute new scientific assessments. Next/previous or save-and-continue needs an
explicit decision about drafts, focus, filters, cursor order, and the last case; never silently advance.

## H0 and H1 — Global header

### H0: decide the job before the layout

At the H0 baseline, the header contained the mobile navigation trigger, project switcher, account
identity and sign-in/sign-out, plus session initialization failure/retry. Language and theme were in the
sidebar footer. The table below records the questions considered; the accepted brief supersedes the
initial placement and open choices. The user's priority was the header's **purpose and contents**.

Write a one-sentence purpose and a content-ownership table before making a visual proposal. A starting
hypothesis is stable working context and account/session access, while each page owns its task and
actions. This is a hypothesis, not an accepted final composition. For each candidate item record the
user need, scope, data source, permitted roles, states, and owner.

| Content or behavior | Current owner | Decision to resolve |
|---|---|---|
| Project identity and switching | Header | What context is essential on global/project routes? How does switching interact with drafts and management-only access? |
| Snapshot, run, aggregation, person context | URL and views | Which levels need persistent orientation, which belong with evidence, and how are names/identifiers disclosed narrowly? |
| Page title and primary action | View | Retain clear task ownership; decide whether context is duplicated, keeping one route H1 |
| Account identity, sign-in/out, recovery | Header and recovery dialog | What is always visible, which actions may use a menu, and where do recoverable session failures appear? |
| Mobile navigation trigger | Header | Preserve discovery, adequate target size, and focus return across header states |
| Language, theme, personal settings | Sidebar footer and settings page | Decide whether current placement serves the header purpose; preserve preference semantics if controls move |
| Application destinations | Sidebar | Keep one primary navigation surface under D7, without duplicating destinations in header tabs |
| Save, review, export, reset, lifecycle feedback | Relevant view/resource | Keep operations attributable to their resource; no ambiguous generic global Save |

Do not fill empty space with unsupported global search, notifications, job monitoring, or new backend
features. If required content is unavailable from existing public contracts, name that dependency
rather than inventing a frontend substitute. Older wireframe controls are not automatic requirements.

Compare content arrangements on public home, project overview, a selected review case, administration,
and personal settings. Include long German names, no project, loading/error/inaccessible context,
resolved and unresolved sessions, forced password change, and narrow viewports. Include both explicit
URL resource selection and project pages using the accepted working-aggregation fallback. Resolve
contents and priority before choosing alignment, density, sticky behavior, or menus.

**H0 deliverable:** purpose statement, included/excluded contents with reasons, header/page/sidebar
ownership, route/state matrix, and small desktop/mobile compositions. The accepted choices and updated
composition now live in the [header brief](frontend-header-proposal.md).

### H1: implement the resolved design

Use G1 primitives and the chosen content model. Resource resolution and mutations keep their existing
owners; the shell consumes context without becoming a second business layer. Avoid duplicate requests,
stale project identity, or leaked names during navigation and account changes. Current resource context
must agree with the URL; switching must not silently substitute newer data. Update relevant design and
delivery documentation when the approved composition changes current placement.

**Exit:** users can identify context and reach account/navigation controls across route families; long
names and failures reflow; header and page actions have unambiguous ownership; keyboard order, focus,
and any sticky behavior work at narrow widths and zoom. Verify switching with drafts and missing or
forbidden context, not just the populated happy path.

## S1 — Sidebar, after the header and views

The sidebar already has a shared role-aware navigation model, desktop collapse, medium-width rail,
mobile drawer, preference controls, tooltips, and H1's project-switcher placement. Assess it against settled H/V responsibilities rather
than treating these capabilities as missing.

- Review grouping and ordering of global, project, and administrator destinations against real tasks.
  Keep exact current-route ownership, including details and personal settings.
- Resolve utility/footer contents left by H1, without conflicting duplicate placement.
- Distinguish missing resource prerequisites from lack of permission. Explicit snapshot/run/aggregation
  context in the URL stays authoritative; a selected run or snapshot never borrows another aggregation.
  Only when none is selected may navigation use the project's explicit working aggregation and its
  run/snapshot, following ADR-0035. Never infer context from recency.
- Review expanded, rail, and drawer presentations together: long labels, accessible names, tooltips,
  footer reachability, short viewports, menus, and focus at breakpoint changes.
- Remove the width-animation finding and preserve reduced-motion behavior.
- Preserve canonical preferences and explicit revision/conflict recovery. Opening the drawer and
  resizing must not save a desktop-collapse preference.

**Exit:** destinations have clear places and correct current states; role/context transitions expose
only valid information; utilities remain reachable; drawer dismissal and focus restoration work;
no layout animation, clipped menu, or inaccessible rail-only control remains.

## Verification and completion

Each package records targeted verification before handoff. Q1 tests interactions among completed
packages rather than discovering accessibility for the first time.

- Exercise German and English, light and dark, 320/390px phones, 720/1080px shell transitions, and desktop.
  Include 200% text, 400% zoom/reflow, text-spacing overrides, reduced motion, and keyboard-only use.
  Wide data may scroll in a labelled local region; the document must not scroll horizontally.
- Cover initial loading, background refresh, empty data, long identifiers, read failure/retry, permission
  loss, partial results, successful/failed writes, and applicable revision conflicts. Screenshots alone
  do not prove focus, persistence, or request recovery.
- Validate reopening a project through review; inspecting evidence, annotating, and reading history;
  import through run/aggregation/evaluation/export; account preferences; public information; and
  administrative flows with appropriate roles. Preserve scientific distinctions throughout.
- Run applicable locked repository gates and frontend lint, format, type, message-catalogue,
  transport-drift, regression/coverage, and production-build checks from
  [CONTRIBUTING.md](../CONTRIBUTING.md). Add targeted tests for meaningful behavior and regression risks.
- Keep administrative settings/team runtime checks reserved for the user's manual testing stage as
  specified in the [implementation plan](15-implementation-plan.md). Record them as pending until
  evidence exists; component/static checks do not substitute for those runtime results.
- Keep the D17 assistive-technology matrix and D18 accessibility owner/user-testing requirements visible
  as release criteria. An automated scan or this roadmap does not complete them.

For each implementation slice, inspect desktop/mobile in one bounded pass, fix observed issues together,
then confirm once. Close findings with targeted evidence and document remaining gaps. Update this plan
and project status as packages complete, without marking a family done while required checks remain.

## Next executable package

Close **G1 and H1** with a connected-browser pass over shared foundations, breadcrumbs, account menu,
project switching and draft departures, including keyboard focus, announcements, mobile/enlarged-text
layout and both themes/locales. Then complete **V1 review and person browsing** as the first view slice:
selected-person/evidence/decision continuity, filter disclosure and mobile list/detail navigation.
Continue through V2–V7, then finish broader S1 sidebar refinement and integrated Q1 verification.
