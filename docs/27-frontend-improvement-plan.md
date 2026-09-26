# Frontend improvement plan

## Purpose and status

This is the improvement roadmap for the existing Phase 8 client, prepared on 2026-09-25.
It separates shared foundations, the global header, individual views, and the sidebar. Following the
user's accepted header decisions, H1 proceeds after shared implementation and before the view pass.
Its bounded sidebar move places project switching above project destinations; broader sidebar work
comes last, once the views' navigation needs are settled. The user has selected the all-projects page
from V2 as the first view increment; the individual project overview follows, with V1 still pending.

The [implementation plan](15-implementation-plan.md) remains authoritative for scope and exit criteria.
The [delivery plan](24-frontend-delivery-plan.md) records capabilities and accepted decisions;
the [design guidelines](25-frontend-design-guidelines.md) govern presentation and accessibility.
The package sequence below remains the roadmap; implementation evidence and pending work are recorded
separately below.

The delivered classification/navigation design is recorded in the
[classification and independent review proposal](frontend-classification-proposal.md). The user chose
explicit picker entry with the working result marked as recommended, and manual annotation before
classification. Preparation established a project-wide availability contract, navigation context
validation, and annotation draft/cache fixes. The independent picker views, snapshot-only annotation
workbench and availability-based sidebar are implemented in the 2026-09-26 increment below.

Inputs are the local `audit.md` and saved frontend critique
`.impeccable/critique/2026-09-25T12-21-09Z__frontend-src.md`, checked against source at `d24f541`.
Their findings are summarized below so execution does not depend on local report artifacts.
The critique predates the latest sidebar and landing-page changes. The audit sampled six routes;
it does not establish that every other route is either sound or defective.

The first three increment records below preserve their validation at delivery; the later H1 record
supersedes their header placement/proposal status and the original ordering.

## Editorial terminology — 2026-09-26

The user approved **Datenstand** for an imported collection and **Automatische Vorschläge** for the
classification destination, with **Vorschläge erstellen** as its action. English uses **Dataset**
(or **Imported dataset** where needed), **Automatic suggestions**, and **Generate suggestions**.
Individual records remain Personendatensätze or Registereinträge; the existing Lauf, Aggregation and
Redigieren terms are unchanged. Shared copy refers to methods, since not all methods are models.
The [product glossary](../PRODUCT.md#interface-terminology) records these presentation names;
API/domain identifiers, scientific labels and behavior remain unchanged.

The review entry's empty state now distinguishes missing completed results from missing imported
data and links to Automatic suggestions. Direct manual entry reads “Direkt annotieren” and explains
that automatic suggestions are optional.

Follow-up change: Redigieren now starts from a paginated list of completed result cards rather than
the shared staged picker. Each card opens the exact review result and shows its Datenstand and Lauf;
the new `GET /projects/{project_id}/review-results` API returns that composed context directly, so the
client does not crawl nested snapshot/run/aggregation collections.

Validation: all 1,499 frontend tests across 82 files pass, with 84.82% branch coverage. Lint,
formatting, type checking, locale parity, generated API drift, production build, documentation policy
and the scoped Impeccable detector pass. No new tests were added for the copy swap. Live visual review
of the updated wording remains pending.

## Classification and independent annotation — 2026-09-26

Classification, Review and Manual annotation now have stable project-level entry routes. Users choose
a ready snapshot for automatic suggestions and manual annotation; Review lists completed results as
openable cards, while Manual annotation can open the snapshot directly or add model evidence. The working result is visibly recommended without
automatic selection or writes. Filtered cursor collections find eligible data across the whole
project, including completed results from a parent run that later failed.

Classification uses the shared page heading, an inline creation form and readable run summaries.
The run detail prioritizes results and aggregation actions, with provenance disclosed on demand.
Manual annotation uses a dedicated, server-filtered snapshot person list, exact person lookup, source
details and attributed history. It reuses append-only decisions and revision conflict handling without
inventing a model result. Viewers retain read-only data and exact resource access.

Unavailable sidebar tasks and empty groups are hidden; availability failures have retry controls.
Statistics and Export require explicit validated run context. Every query is principal/resource
scoped, and saved decisions refresh snapshot and aggregation projections. Person changes guard drafts;
transient refresh failures retain them with saving blocked until recovery. Recovered sessions replay
annotation commands only for the principal that originally submitted them. Exact evidence deep links
use a server identity filter, including people beyond a fuzzy-search page. Viewer return links lead
to Data, and the picker transfers keyboard focus after asynchronous step loading. No persistence
migration or scientific behavior change is involved.

Backend validation passes 1,364 fast tests and 243 PostgreSQL integration tests using isolated
temporary databases. Combined coverage is 86.07% against the 85% floor; normalization, reference
aggregation, certainty assessment and TEI projection each retain 100% branch coverage. Locked
documentation, naming, initializer, dead-code, Ruff, mypy/Pyright, import-boundary and runner checks,
dependency audits, package build and distribution checks pass. Redis suites were not rerun.

The visual stepper was removed at the user's request on 2026-09-26. The snapshot/run/result selection
flow, its context headings, change-selection actions and asynchronous keyboard focus remain intact.
All 22 remaining picker tests pass after removal, including both locales and accessibility checks.

Before the stepper removal, the complete frontend suite passed 1,503 tests across 82 files with
84.94% branch coverage and no unhandled errors. Global lint, formatting, type checking, locale parity, generated API drift,
dependency audit and production build pass. The final run also updates stale navigation/home
assertions and cleans up export test mounts before their document is destroyed.

Live desktop/mobile, zoom and screen-reader review remains pending because no connected browser
was available in this session. Automated axe checks cover the new picker and snapshot annotation
surfaces.

## Classification and review preparation — 2026-09-25

The accepted [entry brief](frontend-classification-proposal.md) now replaces D5's aggregation-only
manual entry target. The first preparation batch adds `ProjectDataAvailability` through the ordinary
project service/repository and viewer-authorized API, with generated OpenAPI and frontend transport.
Its existence queries cover the whole project independently of cursor pages and the working pointer;
completed aggregation eligibility does not depend on the parent run being successful. No persistence
migration, dependency change or scientific semantics change is required.

Sidebar context now validates aggregation/run/snapshot/project relationships and exposes aggregation
workbench links only for completed results. Existing working-pointer fallback remains until the new
project task routes exist. Single annotation commands can take minimal snapshot/person identity with
optional result evidence. Saving or encountering a revision conflict refreshes all affected cached
aggregation review projections; missing cache ownership triggers conservative refresh. Drafts and
late responses are scoped to snapshot/person/evidence, and Save requires matching snapshot/person
history before using its revision. Bulk decisions use the same snapshot-wide refresh.
Shared navigation/detail snapshot reads reuse the active import's two-second polling interval, while
settled/error states and explicit invalidation still revalidate immediately.

Validation: 127 focused backend tests and 1,345 fast tests pass (71.77% coverage against the fast
70% floor), including PostgreSQL project isolation, role access, lifecycle states and eligible data
beyond the first page. Locked policy, Ruff, mypy/Pyright, Import Linter, package build/distribution and
dependency audit checks pass. Full PostgreSQL/Redis coverage combination was not rerun for this batch.
The 110 review tests and 163 navigation/snapshot tests pass, as do full frontend type checking,
generated transport, catalogue parity and production build. Scoped lint/format checks pass.

The full frontend run exposed nine failures in other workspace changes: password-change/header
expectations, the changed signed-in home heading and a Members style-policy violation. Its two polling
failures caused by this preparation were fixed and the affected suites passed again. Global lint also
reports unused admin translation keys, and global formatting reports the concurrently edited
`SignedInHomeView.vue`. Those unrelated changes were preserved; the full frontend gate is not green.
This batch adds no new visual composition; live review of the upcoming picker/views remains pending.

Next: filtered cursor collections and the shared explicit picker; classification list/form/detail
alignment and independent Redigieren entry; then the snapshot annotation read model, manual annotation
without classification and final availability-based sidebar visibility. Read-only picker entry must
not issue default-aggregation commands or change the working result.

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

| Workstream             | Owns                                                                                                              | Deliverable                                                    |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| G — Shared foundations | Accessibility, responsive primitives, tokens, focus, control sizing, common feedback and content conventions      | Reusable rules and components applied across the application   |
| V — Individual views   | The user's task, information hierarchy, local actions, forms, evidence, and view-specific states                  | A reviewed and improved version of every existing route family |
| H — Global header      | Its purpose, contents, global context, account/session controls, and mobile navigation entry                      | A content brief followed by an implemented header              |
| S — Sidebar            | Navigation hierarchy, route ownership, context prerequisites, expanded/rail/drawer behavior, and footer utilities | A coherent navigation surface implemented after H and V        |

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

| Order | Package                                   | Size | Dependency and completion evidence                                                                                               |
| ----- | ----------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------- |
| 0     | Baseline and header content brief (H0)    | M    | Recheck dated findings; inventory routes and shell content; record header/page/sidebar responsibilities and unresolved decisions |
| 1     | Shared foundations (G1)                   | M    | Can proceed alongside H0; confirmed accessibility and containment defects fixed using shared patterns                            |
| 2     | Global header implementation (H1)         | M    | Accepted breadcrumbs/account-menu model, sidebar project switching, and view-owned draft protection; live verification remains   |
| 3     | View improvements (V1–V7)                 | L    | Use G1 and H1 responsibilities; complete each family with its own state and responsive checks                                    |
| 4     | Sidebar implementation (S1)               | M    | H1 and view navigation needs settled; implement navigation and utility organization last                                         |
| 5     | Integrated verification and closeout (Q1) | M    | Verify assembled workflows, close findings with evidence, and update status documentation                                        |

H0 established responsibilities before composition. The user selected breadcrumbs and a header account
menu, with project switching in the sidebar, and brought H1 before the view pass. These bounded moves
are part of H1; broader S1 hierarchy and animation work stays last. The header is not sticky.
Urgent shared defects in the shell remain G1 work.

## Baseline and finding register

Use three evidence states: **reported** (observed by a supplied review), **recheck** (later changes may
have resolved it), and **inspect/design** (a planned review or product decision, not a proven defect).
Reproduce a reported issue in the current target state before changing it. Record closure with route,
locale/theme, viewport or interaction, and verification result; aggregate scores are not acceptance.

| Finding                                                                          | Evidence                              | Owner                                   | Planned response                                                                             |
| -------------------------------------------------------------------------------- | ------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------------------------- |
| A11Y-01: no skip navigation                                                      | Reported; absent in current `App.vue` | G1                                      | First-focus skip link, stable focus target, preserve route main landmarks                    |
| A11Y-02: critical text on page is 4.254:1 in light theme                         | Reported by both reviews              | G1                                      | Readable critical text; verify actual page/panel and destructive-button pairs in both themes |
| RESP-01: review document expands to 470px at 320/390px, worse with enlarged text | Reported by both reviews              | G1 + V1                                 | Shared containment pattern, then review-specific evidence and task layout                    |
| A11Y-03: accessible names directly on four `kbd` elements                        | Reported                              | G1                                      | Correct markup while retaining understandable shortcut announcements                         |
| RESP-02: account directory overflows at 200% text                                | Reported                              | V6                                      | Remove inflexible mobile minimums and verify enlarged-text forms/actions                     |
| RESP-03: small mobile controls                                                   | Reported                              | G1, consumed by V/H1/S1                 | Establish target sizing centrally and verify actual controls                                 |
| PERF-01: sidebar width transition                                                | Reported                              | S1                                      | Remove layout-property animation or use suitable inner-element motion                        |
| INT-01: uppercase product spelling                                               | Reported by both reviews              | G1                                      | Canonical `gendertagger` in metadata, locales, and accessible text                           |
| INT-02: one accent border represents different evidence states                   | Reported                              | V1                                      | Explicitly labelled authority/conflict/error treatments                                      |
| Critique P1: preference failure and untranslated collapse label                  | Recheck after sidebar update          | H0 baseline, then G/V7/S as appropriate | Reproduce request/retry states; the translation already exists in current catalogues         |
| Critique P1/P2: filters/list separate case, evidence, and decision               | Reported                              | V1                                      | Design task continuity and advanced-filter disclosure                                        |
| Critique P2: branding values and editing controls are duplicated                 | Reported                              | V6                                      | Bring effective value, fallback, override, and editing together per field                    |
| Header purpose and contents                                                      | User-requested design work            | H0/H1                                   | Decide responsibilities before composition                                                   |
| Remaining routes                                                                 | Inspect/design                        | V2–V7                                   | Inspect and define specific changes per view before implementation                           |

Baseline work also records documentation inconsistencies relevant to the next slice. Examples include
older pending-project/membership claims despite implemented forms, and conflicting descriptions of
keyboard access to disabled navigation. Resolve the applicable specification before changing behavior;
do not interpret stale descriptions as requests to rebuild delivered features.

## Accepted all-projects brief — 2026-09-25

- **Job (Operate):** help a signed-in user find and open existing projects. Keep the Annotated Archive
  visual language, compact cards and server-provided order; this is the `projects` route only.
- **Hierarchy:** one page heading with a secondary Create project button. Existing project cards show
  name, description when supplied, team and the caller's labelled role, with an explicit Open project
  action. Membership management appears as a button-styled link on each applicable card using the API
  capability flag. The shared project sidebar has a separate Members destination for authorized users;
  its route never highlights Overview, and management authority alone exposes no scientific destinations.
- **Creation:** the heading-row button reveals an inline form, collapsed initially. It announces its
  expanded state and keeps normal keyboard order. Collapsing preserves the mounted draft and existing
  leave protection; account changes clear it. The form uses the available width with responsive columns.
  Team assignment uses the native team dropdown with cursor pagination, without a separate search field.
  Slug constraints sit in a hover/focus/touch help tooltip and remain available as an input description.
  The project-manager label explains membership administration. Selection, validation and pending writes keep
  their existing contracts, with recoverable discovery and pagination states.
- **Access and collections:** management summaries that are not already represented by loaded readable
  cards retain a secondary membership-management entry. A summary alone never implies a project role or
  fetches scientific details. Both collections keep server cursor order, loading/retry/load-more states
  and loaded records after later-page failure. Do not infer a total, progress, recency or client-side
  search from partially loaded collections.
- **Reflow and verification:** card metadata and actions wrap in DOM order; use shared controls,
  feedback, focus and narrow gutters. Verify both locales, empty/error/loading states, long content,
  permission-specific actions, pagination recovery and hidden-draft preservation. The single-project
  overview, broader sidebar work and live visual/assistive-technology checks remain separate.

## Accepted imported-data brief — 2026-09-25

- **Job (Operate):** inspect immutable imported snapshots and their source records before classification.
  Add `projectSnapshots` at `/projects/:projectId/snapshots` and `snapshotDetail` at
  `/projects/:projectId/snapshots/:snapshotId`, following the existing project-card visual language.
- **Navigation:** Data replaces Import in the project sidebar for all readable project roles. The list's
  heading row offers Import data only to project operators and reveals a full-width inline form. The
  existing import route remains a direct-entry wrapper around the same form and belongs to the Data
  destination. Project overview links to the dedicated list rather than repeating it.
- **Upload:** use one file-first dropzone with a keyboard/touch Browse files button. Recognized,
  case-insensitive filename suffixes select the valid source-format/packaging pair and the form shows
  that pair before submission; the API still receives both fields explicitly. One XML/TEI file, several
  .xml files, ZIP/TAR.GZ, CSV, XLSX and JSON are the supported combinations. Selected files expose their
  names and sizes plus remove/clear actions; later compatible XML selections append to the queue. Reject
  unsupported or mixed additions locally without discarding the current selection; retain
  removable rows for empty files, duplicate names, count/size violations and CSV-header errors. Keep
  upload limits visible and disclose the applicable tabular/JSON profile compactly.
- **List and detail:** identify snapshots by import date/time, status and available record count. Each
  card offers Open snapshot. Detail shows lifecycle and failure first, then Source files and Import
  details as compact collapsed cards above the person records. An opened card spans the available width.
  Ready snapshots expose the existing classification route; successful import links to its specific
  snapshot. Do not invent a snapshot name, a total across loaded pages or completeness metrics.
- **Raw records:** when ready, show a cursor-paginated table in server TEI-ID order with Name, TEI
  `xml:id` and an explicit details action whose full label does not collapse. The same action changes to
  Close while open; there is no second close control. On wide screens, selection expands a read-only
  detail row beneath its record without repeating the row's name and ID. On narrow screens, the selected
  row and its toggle remain above the focused detail. Keep selection in the reloadable `person` query
  parameter so normal browser history restores it. If an exact deep link is outside the loaded cursor
  pages, show that record in a standalone detail panel without inserting it into the ordered table. There
  is no name search, client filtering, editing or annotation on this surface. Aggregation-backed person
  browsing and review keep their existing meaning and routes.
- **Integrity and states:** validate snapshot/project identity before rendering child data or links;
  scope caches to the current principal and ignore stale route/account responses. Pending/importing
  snapshots poll until terminal and do not request raw people; failed snapshots retain diagnostic/provenance.
  Lists retain loaded entries after pagination failure. Source-file metadata has no download endpoint.
  Retain server-side authorization, generated transport, bilingual copy and the shared accessibility rules.

## Project and imported-data increment — 2026-09-25

**All-projects and Data views implemented; live verification pending.** The accepted briefs above are
implemented with explicit project entry/management actions, heading-row creation, a full-width inline
form, team assignment, and accessible slug help. Members has its own permission-based sidebar leaf;
management-only access does not expose scientific routes. Transferring management preserves a retained
ordinary project role, while authoritative revocation clears it.

Data now owns the snapshots list, inline import entry and snapshot detail. The import form uses one
accessible browse/drop surface, infers only supported filename-based combinations, shows the explicit
format/delivery it will submit, and keeps selected files individually removable. Ready snapshots expose
raw person records before classification, including deep-linked selection, cursor pagination and a
responsive inline detail controlled by its table-row action. Import completion links directly to the
resulting snapshot. Compact top cards preserve source files, parser, checksum and import configuration
without crowding the primary records task. Records remain immutable.

Focused verification covers both locales, role/context changes, draft retention, pagination recovery,
snapshot/project identity, account isolation, loading/failure/ready states, and automated accessibility.
The slug-help suite passes 16 tests; snapshot detail passes 19, including retention after transient
refresh errors, evidence removal after access failures, stable placement for off-page deep links, and
focus recovery when responsive reflow hides a row or pagination control. Navigation/router/import/list
checks pass 263 tests. Source review's material findings were fixed and verified; the bounded static
design scan reports no findings. The extension uses the existing design tokens and patterns and requires
no durable visual-system change.

The final complete frontend suite passes 1,384 tests across 78 files with 84.00% branch coverage.
Targeted snapshot-detail lint, formatting, type checks, bilingual catalogue parity (1,079 keys),
generated transport, production build, documentation policy and patch whitespace checks pass. Separate
sign-in changes landed during this session; the final suite includes their updated tests without
replacing that work.

The unchanged backend retains this session's passing locked policy, lint/type/import checks, package
build/distribution and 1,343 fast-test results (71.79% coverage). Service integration and combined
coverage were not rerun for this frontend increment. No connected browser is available: rendered
desktop/mobile geometry, tooltip placement, keyboard visibility, zoom/reflow and assistive-technology
checks remain open. The single-project overview design and remaining V packages are not closed by this
increment.

## Project overview and Users increment — 2026-09-25

**Overview card and Users panel implemented; live verification pending.**

Accepted project-overview brief:

- **Job (Operate):** show where one project stands and lead to the next task. One page heading sits over
  one flat panel card: hairline border, card radius, no shadow and no nested cards. Sections are divided by
  hairlines. The page uses the width and gutter of the other project pages (60rem).
- **Content:** details (slug, role, team, creation date, description), imported data, and review
  progress. Facts stack label above value once they sit in columns, so one long value cannot wrap alone.
  Imported data shows the snapshot count, records and import date of the latest ready snapshot, and the
  runs on it; imports in progress or failed appear only when there are any. Review progress reads the
  project's working aggregation ([ADR-0035](decisions/ADR-0035-project-working-aggregation.md)): people
  reviewed against the total with a native progress element; the three workflow states as controlled
  vocabulary tokens without gloss, with the confirmed/corrected split; "open of total" for the contested
  and thin evidence queues, computed by the function the review workbench uses; the final-label
  distribution (latest human decision, otherwise the machine label); and the last review activity. People
  without any final label are counted apart and never folded into `unknown`.
- **Truthfulness:** no confidence threshold, automatic-decision share or invented total. Member counts are
  omitted because the members endpoint is manager-only. Snapshot and run counts read only the first page
  and become a lower bound (`n+`) when the server reports more. Review figures need a completed working
  aggregation; otherwise the section says why.
- **States and actions:** each section loads, fails and retries on its own. Actions are ghost buttons like
  the project cards', right-aligned in their section, with the arrow on the forward action only; the
  button to Data never waits for the figures.

Accepted Users brief:

- **Naming:** the sidebar entries and the breadcrumb are Users (Benutzer*innen) and Settings
  (Einstellungen), replacing Administration and Branding settings; the users page heading follows. The
  Teams and branding-settings pages keep their headings until they are aligned.
- **Layout:** the same 60rem width as the project pages. The heading row holds the title, its
  description, Refresh directory, and an Add user ghost button with plus/minus icon that announces its
  expanded state.
- **Creation:** an inline card, collapsed initially and mounted on first use, like project creation.
  Hiding it preserves a draft and a one-time temporary password; an administrator or access change clears
  them. Focus moves to the username field on opening. Username and display name sit side by side when the
  card has room, and the global-role checkboxes share one wrapping row.
- **Editing:** the form expands in a row directly beneath its account, tinted with it as one unit; one
  at a time, and the same button closes it. Focus moves into the form and returns to that row's button on
  closing. The form stays as wide as the visible table region, so a sideways-scrolling table never cuts it
  off. A modal was rejected: the account should stay in view, and deactivation already needs the page's
  only modal, which must not nest in another.
- **Row actions and states:** edit, reset password (or the link to the own-password change) and end
  sessions are ghost buttons stacked in the actions column. Account and password states are plain coloured
  text; the words carry the meaning. The current-account marker keeps its pill.
- **Heading order:** disclosures inside rows are level-two headings, since the collapsed creation card no
  longer precedes them under the page heading. The automated axe check caught this.

**Verification.** The overview specs cover both locales (32 tests) and the derivation helpers have unit
tests. The existing account specs were updated to open the collapsed creation form first, and the
users, header and navigation suites pass. The complete frontend suite passes 1,382 tests across 78 files;
lint, formatting, type checks, bilingual catalogue parity (1,075 keys) and the documentation policy pass.
The overview was rendered in headless Chrome against a mock API on desktop and mobile in both themes, in
German and light English (not English dark). The Users page was clicked through over the DevTools protocol
against a mock API, in German only, on desktop (light) and mobile (dark): focus moved to the opened form
and back, the form fit a 390px viewport beside the scrolling table, and the layout defects it exposed
(header word breaks, a stranded checkbox) were fixed and rechecked. The Teams page then received the
same treatment (60rem width, an Add team toggle for the creation card, a teams table like the accounts
table with a Manage team button per row, the selected team's detail in a row beneath it or below the table
when that team is not loaded, ghost buttons). It passed the existing suites and one desktop render against
a mock API; narrow screens were not inspected.

**Open.** Behaviour tests for the Users page (collapsed creation form, inline edit row, focus movement,
button actions) are deferred. Nothing ran against the real API, a connected browser or assistive
technology; enlarged-text and zoom checks (RESP-02) remain open, and English dark theme was not viewed for
Users. On narrow screens the stacked action buttons make rows tall. Teams needs a narrow-screen check, and
the branding-settings page is not yet aligned with these patterns.

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

| Order | Views and route names                                                       | Work to resolve                                                                                                                                                                                                                              | Acceptance specific to the view                                                                                                                                                               |
| ----- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| V1    | Review (`review`)                                                           | Keep selected person, evidence, decision, and history connected. Reduce initially exposed filters; include active count and reset. Resolve mobile list/detail navigation, evidence table versus stacked records, and save/continue behavior. | No clipped method outcome or confidence; returning to queue preserves context; save, defer, bulk partial results, and revision conflicts remain explicit; sticky controls never obscure focus |
| V1    | Person browser (`people`)                                                   | Apply shared record/evidence improvements while preserving the browser's different browse/history task and default query behavior.                                                                                                           | Source, predictions, final decision, and append-only history remain reachable with stable person identity; no silent filter/sort changes                                                      |
| V2    | Projects (`projects`) and overview (`projectOverview`)                      | Review reopening existing work versus creation; clarify project/snapshot/run relationships, readable versus management-only projects, and next available actions.                                                                            | Existing work is easy to reopen; creation remains discoverable; empty/populated projects, eligible-team/manager selection, unavailable stages, and long names remain understandable           |
| V3    | Import (`projectImport`)                                                    | Review format/profile/configuration grouping, file selection, validation, persisted progress, and recovery.                                                                                                                                  | Users understand what will be imported, can fix errors, and can resume monitoring a persisted import; format/file limits stay visible                                                         |
| V3    | Runs and aggregation (`snapshotRuns`, `runDetail`, `aggregationDetail`)     | Review method selection, advanced configuration, provenance disclosure, progress/partial errors, aggregation selection, and next actions.                                                                                                    | Pending/running/terminal states remain distinct; users understand selected snapshot/methods and execution versus aggregation; navigation retains resource context                             |
| V4    | Evaluation (`evaluations`, `evaluationDetail`)                              | Review creation versus history, metric explanations, comparison hierarchy, table density, and narrow-screen matrices.                                                                                                                        | Definitions and denominators remain correct; chart alternatives and full matrices remain accessible; no invented cross-method confidence score                                                |
| V4    | Export (`exports`, `exportDetail`)                                          | Review format choices, source/review context, lifecycle, manifest/provenance access, and download feedback.                                                                                                                                  | Export source is unambiguous; incomplete/failed exports cannot appear downloadable; completed artifacts remain inspectable and downloadable                                                   |
| V5    | Home (`home`), legal notice (`legalNotice`), footer, not-found (`notFound`) | Recheck recently changed home; distinguish public explanation from signed-in entry, validate publication hierarchy and recovery links.                                                                                                       | Public information remains accessible signed out; configured/missing/unavailable branding stays truthful; no invented institutional facts                                                     |
| V6    | Accounts (`adminUsers`)                                                     | Fix enlarged-text overflow; review directory versus selected-account actions, creation/editing, role controls, security actions, and confirmations.                                                                                          | Account/action scope stays obvious; errors preserve recoverable inputs; narrow controls and contained table scrolling remain usable                                                           |
| V6    | Teams and membership (`adminTeams`, `projectMembers`)                       | Review team/list/roster relationships, candidates, project-role changes, and manager transfer as existing capabilities.                                                                                                                      | Admin/manager/member boundaries are clear; access loss clears stale context; transfer/removal consequences remain visible                                                                     |
| V6    | Branding (`adminSettings`)                                                  | Unify each field's effective value, fallback, override status, and edit disclosure; group Save/Discard with a changed-field summary.                                                                                                         | Set, clear, unchanged, and reset remain distinct; equal-valued overrides, dirty drafts, conflicts, uncertain outcomes, and public-refresh failure are preserved                               |
| V7    | Personal settings (`userSettings`)                                          | Recheck preferences after shell changes; distinguish saved values, local drafts, defaults, and failure/reload states.                                                                                                                        | Locale/theme/collapse use existing revision checks; account switching and anonymous choices remain isolated                                                                                   |
| V7    | Authentication (`login`, `changePassword`, shared session-recovery dialog)  | Review field/error hierarchy, return destination, forced password change, and preservation of interrupted work.                                                                                                                              | Keyboard/autofill/password-manager paths work; recovery retains eligible drafts and never silently replays protected mutations                                                                |

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

| Content or behavior                             | Current owner                    | Decision to resolve                                                                                                     |
| ----------------------------------------------- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Project identity and switching                  | Header                           | What context is essential on global/project routes? How does switching interact with drafts and management-only access? |
| Snapshot, run, aggregation, person context      | URL and views                    | Which levels need persistent orientation, which belong with evidence, and how are names/identifiers disclosed narrowly? |
| Page title and primary action                   | View                             | Retain clear task ownership; decide whether context is duplicated, keeping one route H1                                 |
| Account identity, sign-in/out, recovery         | Header and recovery dialog       | What is always visible, which actions may use a menu, and where do recoverable session failures appear?                 |
| Mobile navigation trigger                       | Header                           | Preserve discovery, adequate target size, and focus return across header states                                         |
| Language, theme, personal settings              | Sidebar footer and settings page | Decide whether current placement serves the header purpose; preserve preference semantics if controls move              |
| Application destinations                        | Sidebar                          | Keep one primary navigation surface under D7, without duplicating destinations in header tabs                           |
| Save, review, export, reset, lifecycle feedback | Relevant view/resource           | Keep operations attributable to their resource; no ambiguous generic global Save                                        |

Do not fill empty space with unsupported global search, notifications, job monitoring, or new backend
features. If required content is unavailable from existing public contracts, name that dependency
rather than inventing a frontend substitute. Older wireframe controls are not automatic requirements.

Compare content arrangements on public home, project overview, a selected review case, administration,
and personal settings. Include long German names, no project, loading/error/inaccessible context,
resolved and unresolved sessions, forced password change, and narrow viewports. Include both explicit
URL resource selection and project task pickers marking the working result as recommended. Resolve
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
  Task entry opens the independent picker and can mark the project's explicit working aggregation
  as recommended, following ADR-0035; it never selects it automatically. Never infer context from recency.
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

Complete the connected-browser checks for **G1, H1 and the delivered V2 project/data views**, including
keyboard focus, announcements, mobile/enlarged-text layout and both themes/locales. The individual project
overview and the Users panel now follow the patterns above: static, mocked-API and headless-Chrome checks
pass, but connected-browser and assistive-technology checks remain open, as does a run against the real
API. Next render-check the Teams page and align the branding-settings page. Then continue through the
remaining V packages, broader S1 sidebar refinement and integrated Q1 verification. V1 review and
aggregation-backed person browsing remain pending; the new raw-record inspection view does not replace
them.
