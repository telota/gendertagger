# Wireframe UI inventory and Vue transfer specification

## Purpose

This document inventories everything the accepted low/mid-fidelity wireframe
[`frontend/gendertagger.html`](../frontend/gendertagger.html) contains — design tokens, layout shell,
components, screens, and interaction behavior — and binds each item to the delivered `/api/v1` contract.
It is the working specification for porting the wireframe into the Vue 3 + TypeScript + Vite application
described in [`17-frontend-integration.md`](17-frontend-integration.md).

Three kinds of statement appear throughout:

- **Backed** — the wireframe element maps onto a delivered endpoint and contract.
- **Gap (frontend)** — the backend capability exists and the wireframe does not use it.
- **Gap (backend)** — the wireframe element has no server-side equivalent and needs a decision.

## Source material and its status

The wireframe is a single self-contained HTML file: 1016 lines, inline `<style>` and `<script>`, no build
step, no network access, no dependencies. Every number, name, list row, progress bar, and chart bar is
hardcoded. There is no `fetch` call and no data layer.

It is therefore a **layout and interaction reference**, not a prototype to be incrementally wired up. The
Vue application reimplements it against generated OpenAPI transport types; the HTML file remains the visual
reference and is not carried into the application.

The footer states the file is `Variante C — Hybrid, ausgebaut` and explicitly "nicht die finale visuelle
Gestaltung". Visual polish is out of scope for the transfer; structure, information architecture, and
interaction model are in scope.

## Design tokens

The wireframe declares its full palette on `:root` and uses no other colors. These become the token layer of
the Vue application (CSS custom properties or a design-token module).

| Group         | Tokens                                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| Surfaces      | `--surface-1: #fcfcfb`, `--page: #f2f1ee`, `--panel: #ffffff`                                                |
| Text          | `--text-primary: #0b0b0b`, `--text-secondary: #52514e`, `--muted: #898781`                                   |
| Lines         | `--grid: #e1e0d9`, `--border: rgba(11,11,11,0.12)`                                                           |
| Label — solid | `--male: #2a78d6`, `--female: #eb6834`, `--institution: #1baf7a`, `--uncertain: #eda100`                     |
| Label — text  | `--male-text: #1f5aa0`, `--female-text: #b04e27`, `--institution-text: #127a55`, `--uncertain-text: #7a5900` |
| Label — tint  | `--male-tint: #e9f1fa`, `--female-tint: #fdefea`, `--institution-tint: #e8f7f1`, `--uncertain-tint: #fdf5e5` |
| Status        | `--good: #0ca30c`, `--warning: #fab219`, `--critical: #d03b3b`                                               |
| Brand         | `--accent: #4a3aa7` (navigation/primary), `--accent-b: #0f7a63` (action/confirm)                             |
| Focus         | `--focus-ring: #1f5aa0`                                                                                      |

Typography is a single system stack (`system-ui, -apple-system, "Segoe UI", sans-serif`) with a monospace
stack (`ui-monospace, monospace`) for TEI snippets, file names, and repository identifiers. Sizes range
10–34 px with no scale abstraction; the Vue port should introduce a named scale.

`color-scheme: light` is declared and there is no dark palette. Decision D8 ships dark mode, so the tokens
become semantic and theme-scoped rather than a single palette; the verified dark values are in
[`25-frontend-design-guidelines.md`](25-frontend-design-guidelines.md).

The label palette carries scientific meaning and must be defined once, centrally. Note the naming conflict
recorded under [Semantic conflicts](#semantic-conflicts-to-resolve-before-implementation): the token is
called `uncertain` but the canonical label it renders is `unknown`.

## Application shell

The shell is present on every screen and is the first thing to build.

### Sidebar

Fixed 224 px panel, collapsing to a 60 px icon rail below 1080 px. Contains a brand block that navigates to
the project list, a variant tag, and grouped navigation:

| Group                 | Items                                                             |
| --------------------- | ----------------------------------------------------------------- |
| (ungrouped)           | Projekte                                                          |
| Aktuelles Projekt     | Übersicht, Import, Klassifikation, Redigieren, Manuell annotieren |
| Zusätzlich (optional) | Spielmodus                                                        |
| Auswertung            | Statistik & Methoden                                              |
| Admin                 | Einstellungen                                                     |

The "optional" styling of the Spielmodus item (amber, `.opt-pill` badge) is a deliberate
information-architecture decision from [`09-annotation-and-review.md`](09-annotation-and-review.md): the game
path must never read as the primary workflow. Preserve it.

### Topbar

Left: project switcher button opening a dropdown of projects with completion percentages, a separator, and
two actions ("+ Neues Projekt anlegen", "Alle Projekte ansehen"). Right: save-state block, "Jetzt speichern"
button, export dropdown, notification bell with count badge, user name and avatar.

### Screen tabs

A second, redundant navigation row duplicating the sidebar targets. In the wireframe both drive the same
`goto()` function. Decision D7 drops it: the Vue client has one navigation surface, the sidebar.

### Navigation behavior

`goto(targetId)` sets `.active` on the matching `.nav-item`, `.stab`, and `.screen`, updates `aria-current`
and `aria-selected`, and resets scroll. In Vue this becomes `vue-router` with nested routes; the
accessibility attributes come from router-link state.

A global `keydown` handler turns Enter and Space on `[role="button"]` into clicks. This shim exists only
because the wireframe uses `<div role="button">` throughout. **The Vue port must use real `<button>` and
`<a>` elements and delete the shim.**

## Shared component inventory

Every CSS class used in the markup, grouped into proposed components. "Backend binding" names the contract
that supplies the component's data.

### Layout and navigation

| Wireframe classes                                                                    | Proposed component      | Backend binding                               |
| ------------------------------------------------------------------------------------ | ----------------------- | --------------------------------------------- |
| `.app`, `.main`, `.view`                                                             | `AppShell`              | —                                             |
| `.sidebar`, `.brand`, `.nav-item`, `.nav-section`, `.opt-pill`, `.ic`                | `AppSidebar`, `NavItem` | route table                                   |
| `.topbar`, `.right`, `.avatar`                                                       | `AppTopbar`             | `GET /me`                                     |
| `.screen-tabs`, `.stab`                                                              | —                       | dropped per D7                                |
| `.proj-switch`, `.proj-menu`, `.proj-menu-item`, `.proj-menu-action`, `.pn`, `.ppct` | `ProjectSwitcher`       | **Gap (backend):** no project-list endpoint   |
| `.dl-wrap`, `.dl-menu`, `.dl-item`, `.dl-sep`                                        | `ExportMenu`            | `POST /exports`, `GET /exports/{id}/download` |
| `.save-block`, `.save-dot`                                                           | `SaveIndicator`         | **Gap (backend):** no autosave concept        |
| `.bell`, `.badge`                                                                    | `NotificationBell`      | **Gap (backend):** no notification resource   |
| `.footer-note`                                                                       | `AppFooter`             | —                                             |

### Primitives

| Wireframe classes                                                                   | Proposed component               | Notes                                             |
| ----------------------------------------------------------------------------------- | -------------------------------- | ------------------------------------------------- |
| `.btn-ghost`, `.btn-solid`, `.btn`                                                  | `BaseButton` with `variant` prop | three variants in use                             |
| `.chip`, `.chip.on`, `.chip.disabled`                                               | `FilterChip` / `MethodChip`      | toggle semantics; needs `v-model`                 |
| `.card`, `.two-col`                                                                 | `BaseCard`, `TwoColumnLayout`    |                                                   |
| `.note`, `.note.b`, `.note.optional`, `.note.warn`                                  | `CalloutNote` with `tone` prop   | four tones: info, success, optional, warning      |
| `.badge.male/.female/.uncertain/.institution`                                       | `LabelBadge`                     | bound to `CanonicalLabel`                         |
| `.consensus-dot`, `.dot-green/.dot-yellow/.dot-red`                                 | `AgreementIndicator`             | **rebind** to `AgreementTier`                     |
| `.conf-track`, `.conf-fill`                                                         | `ProgressBar`                    | dual use: progress _and_ confidence — split these |
| `.hbar-track`, `.hbar-fill`                                                         | `MetricBar`                      | horizontal metric bar in tables                   |
| `.stat-tile`, `.lbl`, `.val`, `.delta`                                              | `StatTile`                       |                                                   |
| `.ring`, `.progress-card`, `.txt`                                                   | `ProgressRing`                   | conic-gradient ring                               |
| `.toggle`, `.sw`, `.sw.on`                                                          | `BaseSwitch`                     | static in wireframe                               |
| `.slider-track`, `.slider-fill`, `.slider-handle`                                   | `BaseSlider`                     | static in wireframe; see semantic conflicts       |
| `.collapse`, `.collapse-body`                                                       | `CollapsibleSection`             |                                                   |
| `.modal-overlay`, `.modal-box`, `.modal-field`, `.modal-actions`                    | `BaseModal`, `FormField`         |                                                   |
| `.search-box`                                                                       | `SearchInput`                    | **disabled in wireframe**; server-side `q` exists |
| `.tag`, `.src-tag`, `.m-status`, `.file-status`, `.job-status`                      | `StatusPill` with `tone` prop    | four pill styles that can consolidate             |
| `.table-scroll`, `.method-table`, `.mapping`, `.file-list-table`, `.job-hist-table` | `DataTable`                      | four bespoke tables that can consolidate          |

### Domain components

| Wireframe classes                                                                               | Proposed component                 | Backend binding                                          |
| ----------------------------------------------------------------------------------------------- | ---------------------------------- | -------------------------------------------------------- |
| `.project-grid`, `.project-card`, `.ptitle`, `.psrc`, `.pmeta`, `.pprogress-track`, `.pfoot`    | `ProjectCard`                      | **Gap (backend):** no list, no progress projection       |
| `.cta-row`, `.cta`, `.icon`                                                                     | `ActionCard`                       | route targets                                            |
| `.feed-row`                                                                                     | `ActivityFeedRow`                  | **Gap (backend):** no activity/audit endpoint            |
| `.kpi-row`                                                                                      | `KpiRow`                           | derived from evaluation + review counts                  |
| `.annotate-layout`, `.col`                                                                      | `ReviewWorkbench` (3-column)       | shared by Redigieren and Manuell annotieren              |
| `.filt-label`                                                                                   | `FilterGroup`                      | `ReviewItemQuery` fields                                 |
| `.bulk-bar`                                                                                     | `BulkActionBar`                    | **Gap (backend):** no batch annotation endpoint          |
| `.person-row`, `.cb`, `.pname`, `.preason`                                                      | `PersonRow`                        | `ReviewItem`                                             |
| `.detail-name`, `.detail-sub`, `.tei-snippet`                                                   | `PersonDetailHeader`, `TeiSnippet` | `PersonRecord`                                           |
| `.classifier-card`, `.row1`, `.method`                                                          | `MethodResultCard`                 | `GET /aggregations/{id}/results/{result_id}/predictions` |
| `.action-bar`, `.act-btn`                                                                       | `AnnotationActionBar`              | `POST /annotations`                                      |
| `.upload-zone`                                                                                  | `FileDropZone`                     | `POST /projects/{id}/snapshots`                          |
| `.src-switch`, `.src-opt`, `.src-panel`, `.msrc-card`, `.stitle`, `.ssub`                       | `SourceKindSelector`               | `SourceFormat` + `SourcePackaging`                       |
| `.parse-summary`                                                                                | `SnapshotSummary`                  | `DatasetSnapshot` (partial)                              |
| `.gitlab-bar`, `.gitlab-ic`, `.gitlab-form`, `.repo-name`, `.repo-meta`                         | `GitlabSourcePanel`                | **Gap (backend):** no VCS integration                    |
| `.threshold-box`                                                                                | `AutomationThresholdPanel`         | **Gap (backend):** no threshold concept                  |
| `.method-pick`                                                                                  | `MethodSelector`                   | `GET /methods`                                           |
| `.retry-link`                                                                                   | —                                  | **Gap (backend):** no run retry endpoint                 |
| `.kappa-row`, `.kappa-val`                                                                      | `MetricRow`                        | `EvaluationReport`                                       |
| `.bars`, `.bar`, `.cap`, `.legend`                                                              | `DistributionChart`                | `EnsembleMetrics`                                        |
| `.mname`, `.msub`                                                                               | `MethodNameCell`                   | `MethodDescriptor`                                       |
| `.game-wrap`, `.game-hud`, `.timer-ring`, `.hud-stat`, `.game-card`, `.game-btn`, `.combo-pill` | `GameMode*`                        | **Gap (backend):** no scoring resource                   |
| `.lb-row`, `.lb-rank`                                                                           | `LeaderboardRow`                   | **Gap (backend):** no leaderboard                        |

## Screens

Nine screens exist as sibling `.screen` elements; exactly one carries `.active`. Default on load is
Übersicht.

### Projekte

**Intent.** Project list and entry point. Each project owns its own register, runs, progress, and data
source; team membership is per project.

**Contains.** Responsive card grid (`minmax(260px, 1fr)`), one card per project showing title, source-kind
pill, person counts, progress bar, percentage, and relative last-edited time; plus a dashed "new project"
card opening the creation modal.

**Backend.** `POST /projects` creates a project from `slug` (pattern `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`),
`display_name`, and optional `description` ([`models/project.py`](../backend/src/gendertagger/models/project.py)).
`GET /projects` serves the grid and the topbar switcher: a cursor-paginated list, in slug order, of the
projects where the caller has a role, each carrying `current_user_role`. Team membership is per project, as
the wireframe intends ([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)).

**Gaps.**

- **Resolved (backend):** a project's `working_aggregation_execution_id`
  ([ADR-0035](decisions/ADR-0035-project-working-aggregation.md)) names the aggregation its card summarizes,
  so "82 % abgeschlossen" and "6.577 abgeschlossen" are one `GET /aggregations/{id}/review-summary` call away,
  and its `last_annotated_at` is "bearbeitet vor 2 Min."
- **Gap (frontend):** the creation modal collects a name and a source kind but not `slug` or `description`.
  Either collect the slug or derive and confirm it from the display name.
- **Gap (backend):** no project update or delete.

### Übersicht

**Intent.** Project dashboard: automation share, open cases, provenance of completed entries, recent
activity.

**Contains.** An optional-path callout pointing at the game mode; a four-tile KPI row (progress ring plus
"Automatisch entschieden", "Zur Prüfung", "Manuell annotiert"); a four-card CTA row; and a two-column block
with an activity feed and a "where did the finished entries come from" breakdown.

**Backend.** `GET /aggregations/{id}/review-summary` counts one completed aggregation's results by certainty
tier, agreement tier, current review state, final label, and review action, so "Automatisch entschieden"
(`high`), both "Zur Prüfung" queues, "Manuell annotiert" (`reviewed`), and the "wo kamen die fertigen
Einträge her" breakdown (verified vs. corrected, via `review_action`) all read from one request, and
`last_annotated_at` covers "bearbeitet vor 2 Min." `EnsembleMetrics` in
[`models/evaluation.py`](../backend/src/gendertagger/models/evaluation.py) remains the source for
`canonical_label_distribution` inside a completed evaluation report, where the case-study statistics live.

**Gaps.**

- **Gap (backend):** every KPI on this screen is threshold-derived ("Konfidenz ≥ 90 %", "unterhalb
  Schwelle"). See [Semantic conflicts](#semantic-conflicts-to-resolve-before-implementation).
- **Gap (backend):** no activity or audit feed endpoint.
- **Resolved (backend):** the label-source breakdown reads `review_action` on `GET /aggregations/{id}/review-summary`.
- **Gap (frontend/backend):** "davon 62 im Spielmodus" requires annotations to record their capture path.
  `Annotation` has no such field.

### Import

**Intent.** Attach or upload source material, review the parse result, set automation, start classification.

**Contains.** A three-way source selector (Einzelne Datei / Ordner / GitLab-Repository) switching between
three panels; per-panel upload zone, parse callout, four-tile parse summary, and — for folder and GitLab —
a per-file table with status pills; a static "Erkannte Struktur" TEI mapping table; the automation-threshold
box with a static slider and a preview callout; and a "Klassifikation jetzt starten" button.

**Backend.** `POST /projects/{project_id}/snapshots` is multipart, accepts repeated `source` parts, and takes
`source_format` and `packaging` form fields
([`api/routes/projects.py`](../backend/src/gendertagger/api/routes/projects.py)). It returns `202 Accepted` with a pending
`DatasetSnapshot`; the client then polls `GET /snapshots/{id}` for `status`, `record_count`, and
`failure_diagnostic`.

**Gaps.**

- **Gap (frontend):** `source_format` supports `tei`, `csv`, `xlsx`, and `json`; the wireframe offers TEI only.
- **Gap (frontend):** `packaging` supports `single`, `loose`, `zip`, and `tar_gz`; the wireframe offers single
  file and folder only. Archive upload is unreachable.
- **Gap (frontend):** the asynchronous snapshot lifecycle (pending → ready/failed) is not represented; the
  wireframe shows a finished parse immediately.
- **Gap (frontend):** `source_sha256`, `parser_version`, and the ordered source-member metadata available
  from `GET /snapshots/{snapshot_id}/source-members` are not surfaced, although they are the provenance
  anchor for everything downstream. The backend provenance contract is delivered.
- **Gap (backend):** the parse summary invents statistics the API does not return — "Bereits mit @sex: 142",
  "Ohne Namenselement: 14", "Dubletten (gleiche GND-ID): 3". `DatasetSnapshot` exposes only `record_count`.
  Either extend the import result contract or drop these tiles.
- **Gap (backend):** the entire GitLab panel — repository binding, branch and path, access token, "Jetzt
  synchronisieren", per-file commit tracking, "Automatisch auf neue Commits prüfen" — has no backend at all.
- **Gap (backend):** the automation threshold does not exist. See semantic conflicts.
- **Gap (frontend):** upload limits are server-enforced and typed (`SnapshotImportLimits`: 128 members,
  100 MB per member, 500 MB expanded, compression ratio 100, 1 000 000 records) and produce `413`; the
  wireframe shows no limit guidance and no size error state. `GET /snapshot-upload-limits` returns the
  deployment's actual bounds before an upload.

### Klassifikation

**Intent.** Configure and start a run, watch progress, review run history.

**Contains.** A method-picker card with nine chips (six selectable, three disabled with a "nur Batch"
tooltip) and an explanatory note; a current-run card with a run identifier, status pill, start metadata,
estimated remaining time, an overall progress bar, and one `.classifier-card` per method with its own status
and bar; and a run-history table with a retry link and a failure explanation.

**Backend.** `POST /runs` takes `dataset_snapshot_id` and a full `RunConfig`; `POST /runs/{id}/executions`
schedules it; `GET /runs/{id}` and `GET /runs/{id}/executions` return state and per-method
`MethodExecutionSummary`; `GET /runs/{id}/events` streams six SSE event types
([`api/routes/run_events.py`](../backend/src/gendertagger/api/routes/run_events.py)). `GET /snapshots/{id}/runs` lists a snapshot's
runs newest first, and `GET /runs/{id}/aggregations` lists a run's aggregations the same way. Repeating the
default aggregation request returns the existing live or completed aggregation with `200` rather than queueing
another ([ADR-0034](decisions/ADR-0034-reuse-matching-aggregation-on-creation.md)).

**Gaps.**

- **Gap (frontend):** SSE is delivered and unused. The wireframe is fully static; live progress is the single
  highest-value addition on this screen.
- **Gap (frontend):** the method roster is wrong. Ten adapters are registered in
  [`services/method_registry.py`](../backend/src/gendertagger/services/method_registry.py) —
  `parenthetical_qualifier`, `gnd`, `gender_guesser`, `wiki_gendersort`, `hivoto`, `nomquamgender`,
  `hf_distilbert`, `hf_genderize`, `hivoto_xgboost`, `local_llm` — and all are returned by `GET /methods`.
  The wireframe shows nine chips under different names, omits `wiki_gendersort` and
  `parenthetical_qualifier`, and marks `nomquamgender`, `hivoto`, and `hivoto_xgboost` as batch-only, which
  is not true.
- **Gap (frontend):** per-method configuration (`RunConfig.methods[].config`, validated by the registry) and
  `execution.fail_run_on_optional_method_error` have no UI. Chips are on/off only.
- **Gap (frontend):** `failed_count`, `failure_class`, and `failure_diagnostic` per execution are not shown.
- **Gap (frontend):** run provenance (`code_git_commit`, `application_version`, `python_version`,
  `dependency_lock_sha256`, `container_image_digest`, `config_sha256`) and method provenance
  (`model_identifier`, `model_revision`, `model_checksum`, `prompt_version`, `schema_version`,
  `implementation_version`, `normalization_version`) are entirely absent.
- **Gap (backend):** the history table offers "Erneut versuchen ↻". There is no retry endpoint. There is also
  no cancel endpoint, although `RunStatus.cancelled` exists.
- **Resolved (backend):** `GET /snapshots/{snapshot_id}/runs` lists a snapshot's runs newest first, in every
  lifecycle state, so the history table has a source.
- **Gap (frontend):** **the aggregation step is missing entirely.** After executions complete, a run needs
  `POST /runs/{run_id}/aggregations` with a strategy and the exact `method_execution_ids` before any review
  or export is possible. This is the largest structural omission in the wireframe.

### Redigieren

**Intent.** Fast triage of low-certainty and conflicting cases.

**Contains.** A three-column workbench: filter column (reason chips, sort chips, disabled search box); list
column (bulk-action bar, person rows with checkbox, agreement dot, name, reason, and an overflow line);
detail column (name, reason line, TEI snippet, per-method result cards with label badges and confidence
bars, and a four-button action bar with keyboard hints 1–4).

**Backend.** `GET /review-items` takes a `ReviewItemQuery` and returns a `CursorPage[ReviewItem]`
([`models/review.py`](../backend/src/gendertagger/models/review.py)). `POST /annotations` appends one decision.

**Gaps.**

- **Gap (frontend):** `review-items` requires an `aggregation_id`. With no aggregation UI (see above), this
  screen has no addressable data source. Resolve the aggregation flow first.
- **Gap (frontend):** the query supports ten server-side filters — `final_label`, `certainty_tiers`,
  `agreement_tiers`, `workflow_states`, `has_authority_conflict`, `method_name`, `method_label`,
  `prediction_status`, `has_prediction_error`, `q` — plus `sort` and cursor. The three plural filters take
  several values, so each D2 queue is one query. The wireframe exposes three
  invented chips ("Niedrige Konfidenz", "Klassifizierer uneinig", "Kein GND-Treffer") that map to none of
  them, and its search box is `disabled` although `q` is server-side.
- **Gap (frontend):** sort options are `uncertainty` (the versioned `review_triage_v1` policy, per
  [ADR-0022](decisions/ADR-0022-uncertainty-first-review-ordering.md)) and `tei_id`. The wireframe offers
  "Konfidenz aufsteigend" and "Alphabetisch", neither of which exists.
- **Gap (frontend):** `ReviewAction` has three values — `verify`, `correct`, `defer`. The action bar offers
  four labels and no way to defer, and does not distinguish confirming the machine decision from overriding
  it.
- **Gap (frontend):** `AnnotationCreate.comment` is unused.
- **Gap (frontend):** `override_source` (`gnd` or `parenthetical_qualifier`) tells the reviewer that an
  authority overruled the pooled vote. It is not displayed, though it is the single most decision-relevant
  field on the item.
- **Gap (frontend):** optimistic concurrency is unrepresented. `expected_revision` is mandatory and a stale
  write returns `409` with code `annotation_conflict` and the current revision in `details`. The UI needs a
  reload-and-re-decide path. The wireframe instead shows "Automatisch speichern alle 2 Minuten", which
  contradicts the append-only model.
- **Gap (backend):** the bulk bar ("3 ausgewählt → Als Institution markieren") has no batch endpoint. Each
  annotation is a separate `POST` carrying its own `expected_revision`; a client-side loop must handle
  partial failure.
- **Closed (backend):** the detail column shows every method's label and confidence for one person.
  `GET /aggregations/{id}/results/{result_id}/predictions` returns each selected method's full
  `PredictionResult` in selection order, with a null `prediction` where a method persisted none. The UI must
  still present each `method_confidence` as method-specific rather than comparing them.
- **Closed (backend):** the detail column attributes an earlier decision ("von Jo, vor 3 Tagen").
  `GET /annotations?snapshot_id=&tei_id=` returns the complete chain newest first, each entry with the
  reviewer's display name, together with the current `revision` the conflict flow appends against.

### Manuell annotieren

**Intent.** Unrestricted access to every person in the register, independent of the automation result, for
full manual annotation of a sub-corpus.

**Contains.** The same three-column workbench with different filters (status: Alle / Automatisch / Manuell
bestätigt / Noch offen; classification: Male / Female / Institution / Uncertain; search by name, GND ID, or
`xml:id`), a source pill per row (`auto`/`manuell`/`offen`), a pagination line, and the same action bar.

**Backend.** `GET /snapshots/{snapshot_id}/people` returns a `CursorPage[PersonRecord]` in stable TEI-ID
order. `PersonRecord` carries `tei_id`, `surname`, `forenames`, `birth`, `death`, `note`, `events`,
`alt_names`, `name_forms`, `gnd_id`, `external_ids`, `source_member_name`, and `source_record_locator`.

**Gaps.**

- **Resolved (frontend architecture):** “Manuell annotieren” uses `GET /review-items` with the route's
  aggregation ID and `sort=tei_id`, reusing its server-side `q`, status, label, certainty, and agreement
  filters. `list_people` remains an unfiltered raw-register collection; it does not duplicate those query
  semantics.
- **Gap (frontend):** `name_forms`, `alt_names`, `events`, and `external_ids` are rich source-preserving
  fields the detail panel does not use.
- **Resolved (backend):** `GET /snapshots/{snapshot_id}/people/{tei_id}` supports detail reloads and stable
  person deep links without searching cursor pages.

### Spielmodus

**Intent.** Deliberately secondary gamified annotation path writing into the same data as the review screens.

**Contains.** A pre-round choice between open decisions and the entire dataset, a choice of 10, 20, or 50
questions, and a switchable timer; a compact progress, score, streak, and elapsed-time HUD; the source record;
four semantic label buttons with keyboard shortcuts; post-answer machine evidence; a completion summary; and
a persistent project leaderboard for the selected round size.

**Backend.** `POST /projects/{project_id}/game-rounds` validates annotation evidence, computes the score, and
persists an idempotent completed round. `GET /projects/{project_id}/game-leaderboard` returns each reviewer's
best round for one target size. The annotation itself remains the ordinary `POST /annotations` command.

**Frontend.** Delivered as a project-level, opt-in reviewer path for completed aggregations. Project operators
control it from the overview; disabling it hides navigation and blocks direct access without deleting stored
rounds. Open decisions preserve server triage order; the entire-dataset pool uses stable source-ID order so it
can continue through cursor pages across rounds even as decisions append new revisions. A final partial round
stops when the selected pool is exhausted, and the timer preference remains per signed-in account. It does not
implement the wireframe's hint cost or alter the regular review queue.

### Statistik und Methoden

**Intent.** Register quality control and comparative method reliability against GND as reference.

**Contains.** A four-tile KPI row (Coverage, Fleiss' κ, Automatisierungsquote, Ø Review-Zeit); a two-column
block with a bar chart of the classification distribution and an agreement-metrics list; a nine-row method
reliability table (accuracy bar, coverage, mean confidence, UI/batch pill); and a collapsed gamification
section with a three-row leaderboard.

**Backend.** The evaluation subsystem is fully delivered and entirely unused. `POST /evaluations` queues a
`gnd_benchmark_v1` execution over exact `method_execution_ids`; `GET /evaluations/{id}/report` returns an
`EvaluationReport` containing `BenchmarkSummary`, `MethodCoverage` per method, `MethodAccuracy` per method,
a pairwise `KappaCell` matrix, and optional `EnsembleMetrics`.

**Gaps.**

- **Gap (frontend):** evaluation as a _created, asynchronous, reproducible execution_ with status and a
  downloadable report is not represented at all. The wireframe shows numbers with no provenance.
- **Gap (frontend):** unused report content — the pairwise Cohen's κ matrix over eight methods; per-method
  confusion matrices; per-class recall with confidence intervals (`RecallWithCI`); `effective_accuracy`
  alongside `accuracy`; `abstain_count` and `error_count` per method; benchmark size and class composition;
  and the full `EnsembleMetrics` tier distributions.
- **Gap (backend):** "Fleiss' κ (Team)" is computed nowhere.
  [`evaluation/kappa.py`](../backend/src/gendertagger/evaluation/kappa.py) computes pairwise **Cohen's** κ between
  _methods_, not inter-annotator agreement between people.
- **Gap (backend):** "Ø Konfidenz" per method contradicts rule 10 in [`AGENTS.md`](../AGENTS.md) —
  `method_confidence` is method-specific and must not be presented as comparable across methods.
- **Gap (backend):** "Ø Review-Zeit / Fall" is not measured.
- **Gap (backend):** "Spielmodus ↔ Redigieren (Konsistenz)" requires per-path annotation provenance that
  `Annotation` does not record.

### Einstellungen

**Intent.** Data source, automation, save behavior, gamification visibility.

**Contains.** Four cards: data source (current GitLab source, auto-check toggle, allow-commit-export toggle,
"Datenquelle ändern" link); automation (threshold value, "@sex nie überschreiben" toggle); saving (autosave
toggle, interval); gamification (visibility toggle, collapsed-by-default toggle).

**Gaps.**

- The wireframe's eight settings remain unsupported. ADR-0040 permits six deployment-wide branding fields
  through its separate administrative surface. Account locale, theme, and explicit desktop-sidebar collapse
  are independently specified by [ADR-0043](decisions/ADR-0043-account-level-user-preferences.md), with backend
  persistence and generated transport in this increment and personal settings UI deferred. Neither decision
  makes project, scientific, session-policy, or arbitrary deployment settings editable.
- The `/admin/users` directory delivered under
  [ADR-0039](decisions/ADR-0039-administer-local-accounts-over-http.md) is a separate administration route,
  not an implementation of this wireframe settings screen.

### Overlays

**New-project modal.** Name field, three-card source-kind selector, conditional repository-URL field for the
GitLab option, an explanatory note, cancel and create actions. Opens from the project grid card and the
switcher action; closes on button, overlay click, and Escape; focuses the name field on open. Focus is not
trapped — the Vue port must add a focus trap and restore focus on close.

**Export menu.** TEI-XML (enriched), CSV report, a disabled "Nur geprüfte Fälle (CSV)" with a reason, and
"Als Commit ins Repository schreiben". Closes on outside click.

- **Gap (frontend):** `ExportFormat` includes `json`, which the menu omits.
- **Gap (frontend):** `label_source_policy` (`machine_aggregation` vs `human_overrides`) is exactly the
  distinction the disabled "nur geprüfte Fälle" item gestures at, and it is a supported request field.
- **Gap (frontend):** `tei_profile` (`tei_p5_gender_v1`) and `human_resp_id` (the TEI `@resp` value,
  default `#editor`) are unexposed.
- **Gap (frontend):** exports are asynchronous — `POST /exports` returns `202` and the client polls
  `GET /exports/{id}` before `GET /exports/{id}/download`. The menu implies an immediate download.
- **Gap (frontend):** `ExportManifest` records SHA-256 checksums of every output plus the source snapshot
  hash. Nothing surfaces it.
- **Gap (backend):** an export requires both `run_id` and `aggregation_execution_id`. The wireframe has no
  concept of either, so the menu as drawn cannot construct a valid request.
- **Gap (backend):** "Als Commit ins Repository schreiben" has no backend.

## Backend endpoint coverage

The delivered `/api/v1` endpoints, and how the wireframe treats each. Project-scoped roles are
checked against the project that owns the addressed resource.

| Endpoint                                                 | Role                             | Wireframe treatment                                                                                                                                    |
| -------------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET /me`                                                | authenticated                    | mocked ("Sam Kurator:in")                                                                                                                              |
| `GET /auth/session`                                      | authenticated                    | **absent**                                                                                                                                             |
| `POST /auth/login`                                       | unauthenticated                  | **absent — no login screen**                                                                                                                           |
| `POST /auth/logout`                                      | authenticated                    | **absent**                                                                                                                                             |
| `POST /me/password`                                      | authenticated                    | **Delivered** — forced-password-change view                                                                                                            |
| `GET /admin/users`                                       | global admin, password current   | **Delivered** — read-only searchable, cursor-paginated local-account directory ([ADR-0039](decisions/ADR-0039-administer-local-accounts-over-http.md)) |
| `POST /projects`                                         | global operator                  | modal, missing `slug`/`description`                                                                                                                    |
| `GET /projects`                                          | authenticated; own projects only | mocked card grid and switcher                                                                                                                          |
| `GET /projects/{id}`                                     | viewer                           | mocked in topbar                                                                                                                                       |
| `PUT /projects/{id}/working-aggregation`                 | operator                         | **absent**                                                                                                                                             |
| `PUT /projects/{id}/game-mode`                           | operator                         | **Delivered** — project-overview opt-in toggle                                                                                                         |
| `POST /projects/{id}/game-rounds`                        | reviewer; game enabled           | **Delivered** — validated scoring and round persistence                                                                                                |
| `GET /projects/{id}/game-leaderboard`                    | viewer; game enabled             | **Delivered** — best round per reviewer and target size                                                                                                |
| `GET /projects/{id}/members`                             | global admin                     | **absent — no member screen**                                                                                                                          |
| `PUT /projects/{id}/members/{user_id}`                   | global admin                     | **absent**                                                                                                                                             |
| `DELETE /projects/{id}/members/{user_id}`                | global admin                     | **absent**                                                                                                                                             |
| `POST /projects/{id}/snapshots`                          | operator                         | partial — TEI/single only                                                                                                                              |
| `GET /projects/{id}/snapshots`                           | viewer                           | **absent — no snapshot history**                                                                                                                       |
| `GET /snapshot-upload-limits`                            | any role or membership           | **absent — no limit guidance**                                                                                                                         |
| `GET /snapshots/{id}`                                    | viewer                           | absent — no lifecycle shown                                                                                                                            |
| `GET /snapshots/{id}/people`                             | viewer                           | mocked list, unsupported filters                                                                                                                       |
| `GET /snapshots/{id}/runs`                               | viewer                           | mocked run-history table                                                                                                                               |
| `GET /methods`                                           | any role or membership           | hardcoded, wrong roster                                                                                                                                |
| `POST /classify`                                         | any role or membership           | **absent — no screen**                                                                                                                                 |
| `POST /runs`                                             | operator                         | mocked button                                                                                                                                          |
| `GET /runs/{id}`                                         | viewer                           | mocked card                                                                                                                                            |
| `GET /runs/{id}/executions`                              | viewer                           | mocked per-method cards                                                                                                                                |
| `POST /runs/{id}/executions`                             | operator                         | mocked button                                                                                                                                          |
| `GET /runs/{id}/events` (SSE)                            | viewer                           | **absent — static UI**                                                                                                                                 |
| `POST /runs/{id}/aggregations`                           | operator                         | **absent — no screen**                                                                                                                                 |
| `GET /runs/{id}/aggregations`                            | viewer                           | **absent — no screen**                                                                                                                                 |
| `GET /runs/{id}/evaluations`                             | viewer                           | **absent**                                                                                                                                             |
| `GET /runs/{id}/exports`                                 | viewer                           | **absent**                                                                                                                                             |
| `GET /aggregations/{id}`                                 | viewer                           | **absent**                                                                                                                                             |
| `GET /aggregations/{id}/review-summary`                  | viewer                           | mocked KPI tiles and project-card progress                                                                                                             |
| `GET /aggregations/{id}/results`                         | viewer                           | **absent**                                                                                                                                             |
| `GET /aggregations/{id}/results/{result_id}`             | viewer                           | **absent**                                                                                                                                             |
| `GET /aggregations/{id}/results/{result_id}/predictions` | viewer                           | mocked per-method cards                                                                                                                                |
| `GET /review-items`                                      | viewer                           | mocked list, filters do not map                                                                                                                        |
| `GET /annotations`                                       | viewer                           | mocked attribution line                                                                                                                                |
| `POST /annotations`                                      | reviewer                         | mocked action bar, no concurrency                                                                                                                      |
| `POST /evaluations`                                      | operator                         | **absent**                                                                                                                                             |
| `GET /evaluations/{id}`                                  | viewer                           | **absent**                                                                                                                                             |
| `GET /evaluations/{id}/report`                           | viewer                           | mocked with non-existent metrics                                                                                                                       |
| `POST /exports`                                          | operator                         | mocked menu item                                                                                                                                       |
| `GET /exports/{id}`                                      | viewer                           | **absent**                                                                                                                                             |
| `GET /exports/{id}/download`                             | viewer                           | mocked menu item                                                                                                                                       |
| `GET /branding`                                          | unauthenticated                  | **absent — static wireframe footer note only**                                                                                                         |
| `GET /branding/logo`                                     | unauthenticated                  | **absent**                                                                                                                                             |

Authentication is fail-closed: every `/api/v1` route except `POST /auth/login` carries
`require_csrf_protection`, and the default backend is the local account system from
[ADR-0031](decisions/ADR-0031-local-database-authentication.md). Project roles are hierarchical — `viewer` <
`reviewer` < `operator` — and held per project; the global roles are `operator`, which may create projects,
and `admin` ([`api/authorization.py`](../backend/src/gendertagger/api/authorization.py),
[ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)). The wireframe has
no login, no session handling, and no role-conditional affordances; per
[`17-frontend-integration.md`](17-frontend-integration.md) the UI hides or disables controls for convenience
while the server authorizes.

## Wireframe features with no backend support

Grouped by whether they need a backend decision before or after v1.

| Feature                                                        | Screens                            | Recommendation                                                                                                                                                         |
| -------------------------------------------------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GitLab repository source, sync, commit tracking, commit export | Import, Einstellungen, export menu | Defer; needs an ADR and a new resource family. Weigh against [ADR-0005](decisions/ADR-0005-local-first-data-processing.md).                                            |
| Automation confidence threshold                                | Import, Übersicht, Einstellungen   | **Resolve before v1** — it drives three screens' primary metrics.                                                                                                      |
| Project list and per-project progress                          | Projekte, topbar switcher          | Project list **delivered** (`GET /projects`); per-project progress still to add.                                                                                       |
| Per-person, per-method predictions                             | Redigieren, Manuell annotieren     | **Delivered.** `GET /aggregations/{id}/results/{result_id}/predictions`.                                                                                               |
| Annotation history read                                        | Redigieren, Manuell annotieren     | **Delivered.** `GET /annotations?snapshot_id=&tei_id=`.                                                                                                                |
| Run retry and cancel                                           | Klassifikation                     | Add; `cancelled` status already modeled.                                                                                                                               |
| Run list                                                       | Klassifikation                     | **Delivered.** `GET /snapshots/{snapshot_id}/runs`.                                                                                                                    |
| Bulk annotation                                                | Redigieren                         | Client-side loop for v1; batch endpoint later.                                                                                                                         |
| Activity feed                                                  | Übersicht                          | Defer.                                                                                                                                                                 |
| Notifications                                                  | shell                              | Defer.                                                                                                                                                                 |
| Autosave and "last saved"                                      | shell                              | Drop — contradicts append-only annotations.                                                                                                                            |
| User/project settings persistence                              | Einstellungen                      | ADR-0043 adds account locale/theme/desktop-sidebar persistence; its UI and project settings remain deferred.                                                           |
| Game scoring, combos, timer, hints, leaderboard                | Spielmodus, Statistik              | Scoring, streaks, switchable timing, and a project leaderboard are **delivered** in Spielmodus; hint costs and the separate Statistik leaderboard are not implemented. |
| Ø review time per case                                         | Statistik                          | Defer; needs client timing telemetry.                                                                                                                                  |

## Semantic conflicts to resolve before implementation

These are not missing features but contradictions between the wireframe's vocabulary and the canonical
contracts. Each will produce wrong UI if carried over unchanged.

The first two are resolved; their resolutions are recorded as D2 and D3 in
[`24-frontend-delivery-plan.md`](24-frontend-delivery-plan.md).

### The automation threshold does not exist

The wireframe's central control is a percentage threshold ("90 % ausgewählt", "Konfidenz unterhalb Schwelle
(60 % < 90 %)", "Automatisch entschieden: Konfidenz ≥ 90 %"). The backend has no threshold. It models
decision quality categorically:

- `AggregationOutcome`: `decided`, `unresolved_tie`, `no_data`
- `AgreementTier`: `unanimous`, `strong_majority`, `weak_majority`, `no_consensus`, `single_rater`, `no_answer`
- `CertaintyTier`: `high`, `low`, `contested`, `single`, `uncertain`, `no_data`

`PredictionResult.method_confidence` is documented as _"not globally calibrated"_ and rule 10 of
[`AGENTS.md`](../AGENTS.md) forbids treating it as a probability. A percentage threshold over it is not
implementable as drawn.

**Resolved (D2):** the UI is restated in tier vocabulary. The published method
([`paper/article.tex`](paper/article.tex)) is explicit that per-method confidence values are recorded but
do not influence the vote, so a threshold over them has no counterpart in the pipeline. "Automatisch
entschieden" becomes `certainty_tier = high`; "zur Prüfung" becomes the `review_triage_v1` ordering the
backend already produces, split into contested evidence (`low`, `contested`) and thin evidence (`single`,
`uncertain`). The threshold slider and the Einstellungen threshold row are removed rather than reskinned.

### Uncertain is used as a label

The action bar offers Male / Female / **Uncertain** / Institution. `CanonicalLabel` is
`male` / `female` / **`unknown`** / `institution`; `uncertain` is a `CertaintyTier` value. Rule 9 of
[`AGENTS.md`](../AGENTS.md) requires `unknown`, `abstain`, and `error` to stay distinct. The paper warns
against exactly this conflation: `uncertain` identifies entries where only the LLM responded and did so
with low confidence, and is not a vote-level output category.

**Resolved (D3):** canonical labels and tier names stay in English and untranslated in every locale, since
they are the controlled vocabulary written into the TEI output. The action bar becomes
`male` / `female` / `unknown` / `institution`, and the `--uncertain*` tokens are renamed accordingly. The
interface chrome is internationalised in German and English from the first milestone.

### A GND API method does not exist

The wireframe distinguishes "GND API (Live-Abfrage GND-Datensatz)" from "GND Local Lookup". Exactly one
`gnd` method is registered, and it is a content-addressed local SQLite lookup
([ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md)). A live remote lookup would also
conflict with [ADR-0005](decisions/ADR-0005-local-first-data-processing.md).

### Batch-only methods are a fiction

`nomquamgender`, `hivoto`, and `hivoto_xgboost` are registered exactly like the others and returned by
`GET /methods`. The note "6 von 9 Methoden ins UI integriert" and the disabled chips should go; the roster
must come from the API.

### Fleiss versus Cohen kappa

The wireframe reports "Fleiss' κ (Team)". The backend computes pairwise Cohen's κ between methods. These
measure different things over different populations.

### Confidence bars are overloaded

`.conf-track`/`.conf-fill` renders both _execution progress_ (Klassifikation) and _method confidence_
(review detail). The second use is the one that conflicts with rule 10. Split into `ProgressBar` and a
non-numeric per-method indicator.

## Proposed Vue application structure

Consistent with [`17-frontend-integration.md`](17-frontend-integration.md) and
[ADR-0006](decisions/ADR-0006-vue-browser-client-boundary.md).

### Transport

Generate types and client from the FastAPI OpenAPI document; regenerate in CI and fail on drift. No
hand-written schema duplication, no scientific logic in the client.

```text
openapi.json  ->  src/api/schema.d.ts  (openapi-typescript)
              ->  src/api/client.ts    (typed fetch wrapper, credentials: 'include', CSRF header)
```

### Routes

```text
/login
/admin/users                                 AdminUserDirectoryView
/projects                                   ProjectListView
/projects/:projectId
  /overview                                 OverviewView
  /import                                   ImportView
  /snapshots/:snapshotId/runs               RunListView
  /snapshots/:snapshotId/runs/:runId        RunDetailView       (SSE progress)
  /runs/:runId/aggregations/:aggregationId
    /review                                 ReviewQueueView     (sort=uncertainty)
    /people                                 PersonBrowserView   (sort=tei_id)
    /game                                   GameModeView
  /statistics                               StatisticsView
  /settings                                 SettingsView
```

The route shape makes explicit what the wireframe hides: review and export are scoped to a specific
aggregation of a specific run over a specific snapshot. Carrying that context in the URL, rather than in
implicit global state, is the main structural change the port must make.

### State

- **Server state** — a query/cache library (TanStack Query for Vue). Cursor pages are keyed by the full
  filter-plus-sort tuple, because a cursor is only valid for the query that produced it.
- **Client state (Pinia)** — session/`CurrentUser` and roles; the active project/snapshot/run/aggregation
  selection; UI preferences (collapsed sections, tab state).
- **No** duplication of scientific semantics, normalization, aggregation, or final-decision logic.

### Cross-cutting concerns to build once

| Concern                   | Requirement                                                                                                             |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Error envelope            | Single handler for the shared `ApiErrorEnvelope`; map `code` to user-facing copy.                                       |
| `409 annotation_conflict` | Dedicated recovery flow: refetch item, show both decisions, let the reviewer choose.                                    |
| `413` upload limits       | Surface `SnapshotImportLimits` before upload and on rejection.                                                          |
| Async resource polling    | One composable for the `202` → poll → terminal-state pattern used by snapshots, aggregations, evaluations, and exports. |
| SSE                       | One composable with reconnect; on reconnect refetch the resource, since no event log is replayed.                       |
| Cursor pagination         | One composable binding filters, sort, and cursor together.                                                              |
| Roles                     | Directive or composable hiding/disabling controls above the user's role; never the authorization itself.                |
| CSRF                      | Attach the session's CSRF token to every unsafe request.                                                                |

## Required backend additions

Ordered by whether the Vue port is blocked without them.

### Blocking

1. `GET /projects` — cursor-paginated project list. Blocks the shell, the switcher, and the Projekte screen.
   **Delivered** with project-scoped visibility
   ([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)).
2. A per-person method-result read model — every method's `PredictionResult` for one person under one
   aggregation. Blocks the detail column on two screens. **Delivered** as
   `GET /aggregations/{id}/results/{result_id}/predictions`.
3. Annotation history read — `GET /annotations?snapshot_id=&tei_id=` returning the superseding chain. Blocks
   attribution display and the concurrency-conflict resolution flow. **Delivered**, with the current review
   state alongside the chain.

### Near-term

1. Per-project progress projection, so the project cards and Übersicht KPIs have a source. **Delivered**:
   `GET /aggregations/{aggregation_id}/review-summary` supplies the counts, and
   `PUT /projects/{project_id}/working-aggregation`
   ([ADR-0035](decisions/ADR-0035-project-working-aggregation.md)) lets a project name the aggregation its
   card summarizes.
2. A run list for the history table. **Delivered** as `GET /snapshots/{snapshot_id}/runs`, together with the
   other collections the routes need to discover their identifiers: `GET /projects/{project_id}/snapshots`
   and `GET /runs/{run_id}/aggregations`, `/evaluations`, and `/exports`.
3. `POST /runs/{id}/cancel` and a retry path.
4. A decision on the parse-summary statistics (already-set `@sex`, missing name elements, duplicate GND IDs).

### Deferred but design-relevant

Batch annotation, activity feed, notifications, project settings, further personal settings, and VCS
integration remain deferred. Each needs an ADR before it enters the API surface, per
[`22-future-development.md`](22-future-development.md). ADR-0043 admits only account locale, theme, and
explicit desktop-sidebar collapse; the personal settings page and client integration remain later work.

## Implementation sequence

1. **Resolve the two blocking semantic questions** — the automation threshold and the `uncertain`/`unknown`
   naming. They change screen content, not just wiring.
2. **Add the three blocking backend endpoints** (project list, per-person method results, annotation
   history). All three are delivered.
3. **Scaffold** Vite + Vue 3 + TypeScript, generate the OpenAPI client, wire CI drift checking.
4. **Build the shell** — routing, session, roles, error envelope, tokens, primitives.
5. **Import, Klassifikation, Aggregation**, in that order, including SSE. This is the first vertical slice
   and the first point at which the application produces something reviewable.
6. **Redigieren**, with the full server-side filter set, `defer`, `comment`, and conflict recovery.
7. **Manuell annotieren**, reusing the workbench with `sort=tei_id`.
8. **Statistik**, driven by real evaluation executions and reports.
9. **Export**, including format, label-source policy, TEI profile, and manifest display.
10. **Spielmodus**, delivered as a scored but scientifically inert presentation layer over the annotation contract.
11. **Einstellungen** last, scoped to whatever persistence has by then been decided.

Mark the wireframe features listed under
[Wireframe features with no backend support](#wireframe-features-with-no-backend-support) as explicitly out
of scope for v1 in the project plan, so they are not silently expected from the delivered UI.
