# Classification and independent review entry

## Status and purpose

Accepted direction prepared on 2026-09-25; implemented on 2026-09-26 after the preparation fixes.
It develops V3, the entry flow for V1, and the necessary sidebar changes
from the [frontend improvement plan](27-frontend-improvement-plan.md).

This is an Operate surface for project operators and editorial reviewers. Users should understand
which imported data they are working on, choose the evidence deliberately, and start their task without
visiting Automatic suggestions as a prerequisite. Preserve the existing Annotated Archive design and the
recent project/data/user-management patterns.

Confirmed by the user:

- Manually annotating a ready snapshot must work before any classification has run.
- Sidebar entry to Redigieren and Manuell annotieren opens a picker. Mark the project's working result
  as recommended; do not open it automatically.
- Hide unavailable sidebar destinations instead of rendering disabled entries. Availability must
  describe what the project supports, independently of the page the user came from.

## Problem addressed

`useProjectNavigation` previously used the project's working aggregation whenever the URL has no
snapshot or run. Members and Overview therefore acquired a run and aggregation without a user choice.
An explicit snapshot or run suppressed this fallback, making the same review links disabled again.
This is the documented former behavior, rather than evidence of a role bypass.

The former review and person workbenches both required a completed aggregation. Selecting a run alone
does not identify its results: a run can have several aggregations. The working pointer identifies an explicitly chosen
result, not necessarily the most recent result or the only available one.

## Accepted task structure

The user approved the presentation terms on 2026-09-26: **Datenstand** / **Dataset** for an imported
collection, **Automatische Vorschläge** / **Automatic suggestions** for the classification destination,
and **Vorschläge erstellen** / **Generate suggestions** for its creation action. An individual record
remains a Personendatensatz or Registereintrag. The [product terminology](../PRODUCT.md#interface-terminology)
distinguishes interface names from unchanged API/domain contracts and scientific labels. Refer to
methods collectively; not every method is a model. Lauf, Aggregation and Redigieren are unchanged.

| Destination             | Entry and outcome                                                                                                                         |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Automatische Vorschläge | Choose a ready dataset, inspect its existing runs, or generate suggestions. Open a run to inspect progress, methods and its results.      |
| Redigieren              | List completed reviewable results directly. Each card opens its exact result and shows the owning dataset and run.                        |
| Manuell annotieren      | Step 1 chooses a ready snapshot. Step 2 starts annotation immediately or adds a run and completed result as optional supporting evidence. |

Use inline entry surfaces, not modals. Redigieren uses a project-level paginated result collection,
so the user opens the reviewable object directly while still seeing its dataset/run provenance on the
card. Manual annotation keeps the staged dataset and optional run/result evidence picker. Snapshot
options show import time, available record count and source context. Run options show creation time,
methods and status. Run/result selection stays explicit where evidence is optional: selecting a run
reveals its completed results, each with an explicit Open action. Never infer a default from recency
or from an incomplete cursor page.

The visual stepper was removed at the user's request on 2026-09-26. Headings, the selected context
and Change dataset/Change run actions provide orientation through the existing selection flow.

Redigieren now opens from result cards instead of the shared snapshot/run/result picker. The backend
provides `GET /projects/{project_id}/review-results` so the browser does not crawl snapshots and runs
to find eligible results.

Mark the exact working snapshot/run/result as the project's recommended selection. Choosing a different
result for a task does not change the project's working pointer. Do not change that pointer from a
picker, auto-start classification, or create an aggregation merely by opening a selection screen.

After entry, show a compact context row with the snapshot and optional run/result plus a Change
selection action. URL selection, refresh, browser history, existing exact deep links and draft-leave
protection remain meaningful. Existing direct workbench links may open their named resources directly;
sidebar task links always lead to the project-level picker.

## Automatic suggestions composition

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
  aggregated results. Any change to the current run-detail default-aggregation command must be specified
  explicitly, not made as an incidental picker side effect.

## Availability and access

An unselected snapshot/run is normal picker state, not a reason to disable or hide an otherwise usable
project task. Hide a destination when its project prerequisites or permissions are absent, and hide
groups with no visible entries. In particular:

- Automatic suggestions needs a ready snapshot; only operators can start a run.
- Manual annotation needs a ready snapshot and annotation permission, regardless of run availability.
- Redigieren needs a completed aggregation and review permission.
- Management-only access continues to expose Members without scientific data. Preserve viewer access
  to read-only records/results with an accurate label or existing read destinations, rather than
  advertising a manual write capability the viewer lacks.
- Apply the same principle to Statistics and Export using their own valid source prerequisites. Their
  sidebar links must not borrow an unrelated run because the user visited Members.

Use server-authoritative project availability and filtered, cursor-paginated picker collections.
The list endpoints keep their unfiltered defaults and now support lifecycle/result-availability filters.
The preparation added
`GET /projects/{project_id}/data-availability` with canonical `ProjectDataAvailability` fields
`project_id`, `has_ready_snapshots`, and `has_completed_aggregations`. Project-scoped existence queries
cover the full stored collection, require viewer access, and expose no page-specific navigation rules.
Filters apply before pagination and cursors bind to the complete query. A null
working pointer, a failed request or the absence of matches on the first page proves nothing about
other eligible data. Do not crawl every snapshot/run/aggregation in the browser to decide visibility.
Loading and failed availability checks need explicit recovery; they must not claim the project has no
results. Refresh availability after import, run and aggregation lifecycle changes, and isolate it by
principal/project as with other private queries.

## Manual annotation contract

The canonical annotation command already accepts a null `aggregated_result_id`. Annotation history
already supplies the current review revision for a snapshot/person, including revision zero before
the first decision. Reuse these contracts, permissions, append-only history and conflict protection.

The present aggregation-backed `ReviewItem` requires result IDs and certainty/agreement fields; do not
fabricate those for raw people. The canonical `SnapshotAnnotationItem` list/read model provides
current human decisions, server-side search/filtering and cursor pagination for the register.
Keep the source record, decision and history available when no classification evidence is selected.
Machine-specific filters, confidence, verification actions and certainty indicators require actual
supporting results; lack of classification is not a machine `unknown`, `abstain` or `error` outcome.
Annotations remain scoped to snapshot/person, so switching runs within that snapshot does not create
separate annotation histories. A new import remains a different snapshot with no implicit inheritance.
After saving, refresh affected snapshot lists/history and the relevant aggregation queues/summaries;
refreshing only the optional evidence aggregation leaves other views stale. Scope drafts and selections
to snapshot and person, not TEI ID alone, so identical identifiers in two imports cannot share edits.

The delivery plan's D5 now records this accepted replacement for aggregation-only entry. Keep
ADR-0035's explicit working pointer for summaries and recommendations. Project task routes now replace
the former sidebar working-pointer fallback. Destinations use
project-wide availability, while explicit evidence workbenches still validate all selected resources.
Any proposed change to scientific annotation or evaluation semantics requires its own design update
and ADR; this proposal does not change them.

## Delivered sequence and acceptance

0. Prepare the canonical project availability read contract and generated transport; correct navigation
   resource scope/completion checks, annotation command context, draft identity, and cache refreshes
   shared by aggregations of the same snapshot. Update the governing specifications. This preparation
   does not deliver independent pickers or snapshot-only annotation screens.
1. Specify canonical filtered collections and generate frontend transport types.
   Build the shared project-level picker and stable sidebar entry routes, preserving exact deep links.
2. Align the classification list, creation form and run detail with the existing view patterns; connect
   its result actions and independent Redigieren entry to the shared selection model.
3. Specify the canonical snapshot-level annotation read model, then deliver snapshot-only manual
   annotation and optional classification evidence. Finish project-wide
   hiding rules for unavailable destinations and integrate navigation across Members, Data and all
   task entries.

Verify projects with no import, only a ready snapshot, running/failed classification, one completed
result, several results per run and several snapshots. Cover eligible results outside the first page,
working pointers absent or pointing elsewhere, account/role changes, stale responses, annotation
conflicts, draft cancellation and refresh/back/deep-link behavior. Check both locales, keyboard use,
mobile/reflow and accessible picker announcements. Direct navigation from Members must behave like
navigation from Overview or Data. Automated implementation checks are recorded in the improvement
plan; live browser review remains pending.
