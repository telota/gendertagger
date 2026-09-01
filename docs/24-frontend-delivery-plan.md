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

Phase 8's backend prerequisites are met, but three practical preconditions are not, and two of them are
outside the frontend team's control.

| Precondition | State | Blocks |
|---|---|---|
| A real `AuthenticationBackend` | **Not met.** `RejectAllAuthenticationBackend` fails closed; every `/api/v1` call returns `401`. | Everything past a login screen |
| Three missing read endpoints | **Not met.** Project list, per-person method results, annotation history. | Shell, review detail panel, audit view |
| Blocking semantic decisions | **Partly taken.** D2, D3, D4 resolved; D5 and D6 deliberately open. See [Decisions](#decisions-taken). | `GET /projects` shape (D6); Manuell annotieren (D5) |

The frontend can be scaffolded against a mocked or development authentication backend, so M1 and M2 are not
hard-blocked. M3 onward are.

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

**Still needed.**

- [`deploy/docker/frontend.Dockerfile`](../deploy/docker/frontend.Dockerfile) has its real build commented
  out and emits a placeholder `index.html`. The build context is `./frontend`, so `frontend/package.json`
  and its lockfile must live there — separate from the root `package.json`, which exists only for Pyright.
- The production stage serves the built assets from a stock nginx image with **no SPA history fallback**.
  A history-mode router will 404 on any deep link. Either add a `try_files $uri $uri/ /index.html;` config
  to the frontend image or accept hash routing. This is decision [D13](#early-architectural-decisions).
- The `development` stage installs no dependencies and `compose.dev.yaml` builds the `production` target,
  so there is currently no Vite HMR path. Wire the dev target and a bind mount, or run Vite outside Compose
  against `http://localhost:8000`.
- `frontend_sbom` will begin producing a real dependency tree. The repository's provenance and licence
  culture applies to npm packages too — see decision [D9](#early-architectural-decisions).

## Milestones

| ID | Milestone | Size | Hard dependencies |
|---|---|---|---|
| M0 | Decisions and backend prerequisites | M | D1; D6 before `GET /projects` ships; three read endpoints |
| M1 | Scaffold and transport | S | Node toolchain decision (D12); i18n per D3 |
| M2 | Application shell | M | M1; a working auth backend |
| M3 | Projects and import | M | M2; `GET /projects` (D6) |
| M4 | Runs and aggregation | L | M3 |
| M5 | Review workbench | L | M4; per-person method results |
| M6 | Person browser and audit view | M | M5; annotation history endpoint; **D5 (open)** |
| M7 | Evaluation and statistics | M | M4 |
| M8 | Export | S | M4 |
| M9 | Optional paths and production build | M | M5; D13, D14 |

### M0 — Decisions and backend prerequisites

**Goal.** Remove the things that would force rework later.

**Work.**

- Take decisions D1–D6 and record each one as an ADR where it changes a contract or a scientific
  presentation rule, per [`AGENTS.md`](../AGENTS.md).
- Implement the three blocking read endpoints from
  [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md): `GET /projects`, a per-person
  method-result read model, and annotation history.
- Stand up a development authentication backend so the client is exercisable end to end. This is separate
  from choosing the production provider (D1) and should not wait for it.
- Confirm the v1 scope exclusions in writing, so the wireframe's unsupported features are not silently
  expected.

**Exit criterion.** A developer can authenticate against a local deployment, list projects, and read one
person's full method results and annotation history through `/api/v1`.

### M1 — Scaffold and transport

**Goal.** A buildable, type-safe client skeleton with no hand-written schema.

**Work.**

- Scaffold Vite + Vue 3 + TypeScript in `frontend/`, keeping the existing Docker build context.
- Generate `schema.d.ts` from the FastAPI OpenAPI document; wrap it in a typed fetch client with
  `credentials: 'include'` and CSRF header attachment.
- Add a CI job that regenerates the client and fails on drift, closing the gap recorded under "Generated
  TypeScript transport client" in [`22-future-development.md`](22-future-development.md).
- Enable the real build stages in the Dockerfile and wire the dev target.
- Establish the frontend test stack and join it to the existing CI stages (D11).

**Exit criterion.** `npm run build` produces the image served by the gateway, and a deliberate backend
contract change fails CI.

### M2 — Application shell

**Goal.** Everything every screen depends on, built once.

**Work.**

- Router with the nested project/snapshot/run/aggregation structure from
  [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md).
- Session handling against `GET /me`, login/logout, `401` redirect, role-aware hiding and disabling.
- The eight cross-cutting concerns listed in that document: error envelope, `409` recovery, `413` limits,
  async `202`-poll composable, SSE composable, cursor pagination, roles, CSRF.
- Design tokens, typography scale, and the primitive components — with real `<button>`/`<a>` elements,
  focus management, and a focus trap for modals. The wireframe's `role="button"` keyboard shim is not
  carried over.

**Exit criterion.** A viewer, reviewer, and operator each see a correctly scoped shell; an expired session
and a server error both render correctly.

### M3 — Projects and import

**Goal.** The first write path, and the first real provenance surface.

**Work.**

- Project list, project creation including `slug` and `description`, project switcher.
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
- **Aggregation as a first-class step**, per decision D4.

**Exit criterion.** An operator starts a run, watches it complete live, produces an aggregation, and can
read back the exact configuration hash and code provenance that produced it.

### M5 — Review workbench

**Goal.** The Phase 8 exit criterion.

**Work.**

- Three-column workbench driven by `GET /review-items` with the complete server-side filter set, both sort
  orders, and cursor pagination keyed to the filter tuple.
- Detail panel with per-method results, `override_source`, agreement and certainty tiers.
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
  [`23-wireframe-ui-inventory.md`](23-wireframe-ui-inventory.md).

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

- Spielmodus as a presentation layer over the annotation contract, scoring deferred, subject to D14 — the
  constraint from [`22-future-development.md`](22-future-development.md) holds: it must never influence
  which records are shown.
- Einstellungen reduced to whatever persistence exists, or read-only deployment facts.
- SPA routing fallback in the frontend image (D13), production build, same-origin smoke test through the
  gateway.
- Accessibility pass: keyboard paths, focus order, contrast against the token palette, screen-reader labels
  for the agreement indicators.

**Exit criterion.** The production Compose profile serves the built client through the gateway, deep links
resolve, and the review path works end to end behind a real session.

## Open decisions

### Blocking decisions

These change what gets built, not just how. Each needs an owner and a date.

**D1 — Production authentication provider.** `RejectAllAuthenticationBackend` fails closed by design
([`16-open-questions.md`](16-open-questions.md)). Local accounts, institutional OIDC/SSO, or both? OIDC is
currently recorded as deferred in [`22-future-development.md`](22-future-development.md), which conflicts
with shipping a browser client. *Owner: infrastructure and project lead. Recommendation: implement a local
account backend now to unblock delivery, and treat SSO as a later backend swap — the `CurrentUser`
abstraction makes that a contained change.*

**D2 — Automation threshold semantics.** The wireframe's percentage threshold has no backend equivalent and
conflicts with rule 10 of [`AGENTS.md`](../AGENTS.md). *Recommendation: restate the UI in `CertaintyTier`
and `AgreementTier` vocabulary. Introducing a calibrated threshold instead would require an ADR and
contradicts [ADR-0009](decisions/ADR-0009-reference-agreement-certainty.md).*

**D3 — UI label vocabulary and interface language.** The canonical labels are `male`, `female`, `unknown`,
`institution`; the wireframe renders the third as "Uncertain", which is a certainty tier. The UI is German
throughout while the API and documentation are English. Decide the German label vocabulary, resolve the
collision, and decide whether v1 is German-only or introduces i18n from the start. *Recommendation: fix a
German label vocabulary that keeps `unknown` and `uncertain` distinct, and ship German-only with strings
centralised so i18n stays a later addition.*

**D4 — Is aggregation implicit or explicit?** The backend allows many aggregations per run over arbitrary
method-execution subsets. The wireframe assumes one implicit result. *Recommendation: automatically create a
default `reference_v1` aggregation over all completed executions when a run finishes, and expose explicit
aggregation creation as an advanced path. This keeps the common workflow short without hiding the model.*

**D5 — Data source for "Manuell annotieren".** `GET /snapshots/{id}/people` has no filters and no `q`;
`GET /review-items` has both but requires an aggregation. *Recommendation: drive the screen from
`review-items` with `sort=tei_id`. Consequence to accept explicitly: browsing the register requires a
completed aggregation.*

**D6 — Project visibility and role scope.** The wireframe states "Team-Mitgliedschaften gelten projektweise",
but roles are currently global and project-scoped permissions are deferred in
[`22-future-development.md`](22-future-development.md). Decide what `GET /projects` returns for a viewer
before it is implemented, because changing it later is a breaking contract change. *Recommendation: return
all projects for any authenticated viewer in v1 and drop the per-project membership language from the UI
until scoped permissions exist.*

### Early architectural decisions

Not blocking M1, but expensive to reverse after M2.

**D7 — Dual navigation.** The wireframe has both a sidebar and a redundant tab row for the same eight
destinations. *Recommendation: keep the sidebar only.*

**D8 — Dark mode.** `color-scheme: light` is currently fixed. Retrofitting after component work is more
expensive than deciding now.

**D9 — Dependency budget.** In-house primitives versus a component library. The repository publishes an SBOM
for the frontend image and audits dependencies, so every package has a governance cost; against that, a
DIY modal, menu, and combobox carry real accessibility risk. *Recommendation: a small headless
accessibility library for overlay primitives, everything else in-house on the existing tokens.*

**D10 — Charting.** The distribution bars are trivial inline SVG; the κ and confusion matrices are not.
*Recommendation: hand-rolled SVG for bars and matrices before adopting a charting dependency.*

**D11 — Frontend test stack and CI placement.** Unit, component, and end-to-end layers, and how they join
the existing `validate`/`test`/`coverage` stages under [`14-testing.md`](14-testing.md) and
[`18-engineering-and-quality.md`](18-engineering-and-quality.md). Note that the golden fixtures gate
scientific behavior but say nothing about the UI; M5's exit criterion needs its own seeded-snapshot
acceptance test.

**D12 — Node toolchain and lockfile policy.** Node 22 is implied by the Dockerfile. Pin the version, decide
where `frontend/package-lock.json` sits relative to the root `package.json`, and extend the existing
`lockfile` and `dependency_audit` CI jobs to cover it.

**D13 — Routing mode.** History-mode routing requires an SPA fallback in the frontend nginx image, which
does not exist yet. *Recommendation: add the fallback and use history mode; hash routing is a visible
compromise in shareable scholarly URLs.*

**D14 — Does v1 ship the Spielmodus?** It is buildable as a presentation layer without any backend, but it
is also the clearest candidate to defer. *Recommendation: build it, defer scoring.*

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
| No production authentication provider | Client cannot ship regardless of its completeness | Decide D1 at M0; build against a local backend meanwhile |
| Aggregation is invisible in the accepted design | Users expect review immediately after classification | Decide D4 early and make the step legible in M4 rather than hiding it again |
| Threshold decision reverberates across three screens | Late reversal invalidates Import, Übersicht, Einstellungen | Decide D2 before M3 |
| Wireframe promises unbuilt features | Stakeholder expectation gap at delivery | Confirm the scope exclusions in writing at M0 |
| Frontend dependency tree meets a provenance-strict repository | SBOM and licence review friction late in delivery | Set the dependency budget (D9) before M2 |
| No UI-level acceptance coverage | Scientific fixtures pass while the review path is broken | Define the seeded-snapshot acceptance test as part of D11 |

## Immediate next steps

1. Assign owners and dates to D1–D6.
2. Implement the three blocking read endpoints.
3. Stand up a development authentication backend.
4. Confirm the v1 scope exclusions with the stakeholders who reviewed the wireframe.
5. Begin M1 in parallel with items 1–4, since scaffolding and transport generation depend on none of them.
