# Aggregation workflow implementation plan

## Status and scope

Prepared on 2026-09-26 in response to the user's request for an implementation plan. This is proposed
work within Phase 8, not an implementation or a replacement for accepted runtime specifications.
The [implementation plan](15-implementation-plan.md) owns sequencing and exit criteria.

The user explicitly confirmed that ordinary exports should include human decisions by default,
falling back to machine suggestions where no current human label exists. Machine-only export remains
an explicit option. The remaining details below are the recommended implementation direction.

## Intended workflow

An operator configures suggestion generation for a project, chooses a dataset, and starts
**Generate suggestions / Vorschläge erstellen**. The server executes the methods and automatically
combines their outputs. Closing the browser has no effect on completion.

The interface reports: **Running methods → Combining results → Suggestions ready**. Each stage has
its own failure and recovery state. Review then records editorial decisions without rewriting method
outputs or combined suggestions. Export includes those decisions by default.

Advanced users can choose **Run methods only / Nur Methoden ausführen** for experiments. This mode
produces individual method results and does not promise a combined suggestion set. Manual annotation
of a ready dataset remains available without any run or aggregation.

## Existing behavior and constraints

- `RunConfig.aggregation.strategy` already defaults to `reference_v1`, but aggregation execution is
  currently started by a watcher in `AggregationSection.vue` when an operator visits a completed run.
  Backend run completion does not create that aggregation.
- [D4](24-frontend-delivery-plan.md#d4--aggregation-is-created-automatically-with-an-explicit-advanced-path)
  and [ADR-0034](decisions/ADR-0034-reuse-matching-aggregation-on-creation.md) explicitly chose that
  browser-owned trigger. A new ADR must supersede the trigger decision while preserving matching
  aggregation reuse and independent aggregation resources.
- `reference_v1` is the only supported strategy. It requires the nine reference methods; the
  experimental HIVOTO-XGBoost method does not participate in the reference vote. An arbitrary subset
  cannot be silently treated as the published ensemble.
- A recorded `abstain` or `error` prediction satisfies evidence presence without casting a vote.
  A missing prediction does not. `completed_with_errors` can also reflect failed batches with missing
  predictions, so a terminal run status alone cannot establish aggregation eligibility.
- [ADR-0035](decisions/ADR-0035-project-working-aggregation.md) makes the team's working aggregation an
  explicit project selection. Automatic aggregation must not change it.
- Review decisions belong to a person within a snapshot, not to a separate history per aggregation.
  A new snapshot does not inherit annotations. Existing independent review entry, completed-result
  cards, exact links, and snapshot-only annotation must remain usable.
- The current UI calls an unreviewed machine fallback a final label. Both export creation models and
  the export form default to `machine_aggregation`; changing that default needs an explicit contract
  decision and updated scientific export expectations.

## Product and contract decisions

### Preserve the three evidence layers

| Meaning | English presentation | German presentation | Existing contract |
| --- | --- | --- | --- |
| One method's normalized answer and retained raw output | Method results | Methodenergebnisse | `Prediction` |
| Combined machine evidence for one person | Automatic suggestion | Automatischer Vorschlag | `AggregatedResult` |
| Human verification, correction, or deferral | Editorial decision | Redaktionelle Entscheidung | `Annotation` |
| Currently applicable label with its source and review state | Current classification | Aktuelle Klassifikation | Existing final-decision projection |

Use the plural **Automatic suggestions / Automatische Vorschläge** for a completed result collection.
Retain Run/Lauf and Aggregation in technical details where they identify useful provenance. Do not
rename serialized fields such as `final_label` just to improve presentation text.

A current classification is not necessarily reviewed. Show review state separately and keep deferred
cases visibly unresolved. A current `verify` or `correct` annotation supplies the human label; a
`defer` head has no label and falls back to machine evidence under the existing policy. Do not revive
an older superseded human label. An explicit human `unknown` remains a valid human decision.

### Make execution intent explicit

Add a validated run-level aggregation mode with `automatic` and `manual` values. Keep this workflow
metadata distinct from the existing versioned aggregation strategy.

- The ordinary browser action explicitly submits `automatic` and validates the full reference method
  set before expensive work begins. Validation also resolves existing method settings and asset
  references; it must not invent absent local assets or imply that validation guarantees availability.
- The advanced method-only action explicitly submits `manual` and retains the existing ability to
  execute a subset of methods.
- Omitted mode on existing API clients, and historical runs, retain manual orchestration. No migration
  automatically computes new outputs for historical runs.
- Persist the mode and a link to the designated automatic aggregation attempt. Expose a typed workflow
  summary through the ordinary run API so clients can distinguish methods running, aggregation queued
  or running, suggestions available, and blocked/failed/cancelled outcomes.
- Keep `RunStatus` as the method-execution lifecycle. Do not change its meaning to include aggregation
  or make a completed method run appear unfinished because aggregation failed.
- Preserve historical resolved configuration bytes and hashes. New workflow fields must not silently
  alter old `RunConfig` hashes through default injection when historical records are read. Persist a
  canonical immutable workflow-intent snapshot and its hash separately; the current attempt link is
  operational state, not a mutation of that original intent.

The server owns eligibility and workflow state. The client must not implement reference membership,
scientific completeness checks, or result selection by scanning cursor pages.

### Save one project configuration

Provide one optional, revision-protected suggestion configuration per project, containing the method
selection/settings, existing execution settings, and aggregation strategy. Use closed Pydantic
contracts and a narrow API resource, rather than a general project-settings framework.

Operators explicitly save project defaults. Project readers with scientific-data access may inspect
them; management-only access must not acquire scientific-data access through this resource. Concurrent
saves compare an expected revision and return `409` on conflict.

The form loads these defaults, permits an explicit per-run override, and distinguishes **Save for
project** from **Generate suggestions**. Starting a run never implicitly saves defaults. First use
explains which required method settings are missing instead of supplying fictional deployment values.

Each run persists its fully resolved configuration plus the saved configuration revision when used.
Starting from a saved revision must resolve that exact revision or reject a stale request; it must
never silently use newer settings. Changing defaults affects future runs only. Do not store secrets
or replace deployment-owned configuration such as locally hosted service credentials.

### Keep working selection and export explicit

Add a discoverable **Use as working result / Als Arbeitsergebnis verwenden** action for operators on
a completed suggestion set, using the existing working-aggregation endpoint. Show the selected result
in summaries and as a recommendation in review entry. Creating suggestions, opening a page, and choosing
an alternate review context must not move this pointer.

For new exports, default to `human_overrides` consistently in the browser and canonical creation
contracts. Always submit and persist the selected policy. Name the choices **Include editorial
decisions** and **Machine suggestions only**, with canonical policy tokens available in provenance.
Explain that including decisions also includes machine fallbacks for unreviewed or deferred records;
it does not mean that every exported record has been reviewed.

Keep the selected aggregation explicit in the export context. An exact result's export action must
carry that result through; a generic export entry must not silently choose the first cursor-page item.
Existing exports, explicit machine-only requests, label-resolution semantics, certainty rules, and
TEI encoding remain unchanged. Document that newly omitted-policy API requests change behavior.

## Delivery sequence

### 1. Specify the architecture and compatibility contract

Before runtime edits:

- Add a new ADR for server-owned orchestration, narrowly superseding D4 and the browser-trigger
  consequence of ADR-0034. Preserve independent lifecycle resources, reuse identity, and ADR-0035.
- Record the saved project configuration contract and the user-approved export default in the
  relevant ADRs. Number records at implementation time to avoid colliding with concurrent work.
- Update domain, Pydantic/API, persistence, queue, provenance, aggregation, review, export, and frontend
  specifications where these decisions apply. Update the product glossary and classification brief.
  Reconcile the narrow project-configuration feature with the broader settings deferral.
- Define the exact workflow summary, eligibility diagnostics, attempt linkage, retry command, and
  forward migrations. Regenerate OpenAPI and frontend transport with each implemented contract change.

Exit: the next slices have testable lifecycle and API contracts, including legacy behavior, without
changing reference voting, authority overrides, certainty tiers, or evaluation definitions.

### 2. Move automatic aggregation into the application services

Extend the existing run-completion flow and aggregation service rather than introducing a second
pipeline or a browser orchestration layer.

- Extract a unit-of-work-aware aggregation ensure/create operation. Do not call the current public
  service after run commit: it opens a separate transaction and leaves a lost-work window.
- In the transaction that observes method completion, atomically persist either the designated
  aggregation and its existing outbox dispatch, or a durable explanation that aggregation is blocked.
  Cover scheduler completion for empty datasets, successful final batches, and permanent batch errors.
- For automatic runs, consider `completed` and `completed_with_errors` only after checking the
  required method executions. Preserve deliberate failed/cancelled run policies; do not automatically
  continue a run whose execution policy failed it. Manual aggregation remains available when valid.
- Select executions in a stable order from persisted run configuration and reuse ADR-0034's
  concurrency protection and matching identity. Concurrent creation, worker redelivery, and manual
  requests with the identical strategy, configuration, and exact ordered selection must reuse one
  usable aggregation and dispatch intent. Other valid manual selections remain separate resources;
  the automatic workflow follows its designated attempt rather than whichever result is newest.
- Keep the aggregation executor's per-person completeness validation authoritative. Missing evidence
  produces a visible failure with no partial results, not synthetic abstentions or changed voting.
- Persist a finite failure/blocked outcome. Duplicate delivery and reconciliation must not repeatedly
  create new attempts after a permanent failure. An explicit operator-authorized retry can create a
  fresh attempt where valid, preserving failed history and updating the designated-attempt link.
  Bounded transient retries stay on the same attempt. Workers execute the persisted authorized intent
  without requiring the initiating user's browser or session to remain active.
- Use existing outbox delivery/reconciliation for broker outages. Add bounded consistency repair for
  automatic intents only where necessary; it must honor terminal failures and must not backfill legacy
  manual runs or restart cancelled work.

Exit: an automatic run reaches a persisted suggestion set or an actionable failure while every browser
is closed. Retrying aggregation never reruns methods or rewrites predictions.

### 3. Add reusable project configuration

Implement its Pydantic commands/read models, persistence, forward migration, repository/service,
project-scoped API, and generated transport. Reuse method validation and aggregation eligibility from
slice 2. Include revision conflict handling and configuration-source provenance in run creation.

Exit: an operator saves the configuration once, reuses it for another dataset, and can override one
run without altering earlier runs or saved defaults.

### 4. Deliver the ordinary and advanced UI paths

- Update `NewRunForm.vue` and run creation transport for explicit intent and project defaults. Keep
  the normal action **Generate suggestions**; place method-only execution in an advanced path.
- Remove the auto-create watcher from `AggregationSection.vue` after server orchestration is available.
  Visiting a run, review entry, or result list becomes read-only.
- Drive progress and recovery from the run workflow summary and exact aggregation ID. The existing run
  SSE stream ends when methods finish, so continue observing aggregation through supported polling or
  an explicitly specified workflow stream. Preserve GET fallback and reconnect behavior.
- Replace ambiguous result/final wording in run details, review lists/cards, person details, filters,
  project summaries, and export controls in both locales. Show source and review status distinctly.
- Make advanced re-aggregation explain the actual `reference_v1` requirements. Do not offer arbitrary
  reference-method removal as a valid combination. Retain exact aggregation deep links and history.
- Add the working-result action and refresh affected project summaries/recommendations after success.
  Preserve role checks, account-scoped caches, draft protection, and independent manual annotation.

Exit: the user performs one ordinary action and knows when suggestions are ready for review. Method
completion alone is never presented as a completed suggestion-generation workflow.

### 5. Make reviewed exports the default

Update API defaults, service construction, frontend initialization/reset/draft comparison, explanatory
copy, and explicit result-context propagation together. Preserve an explicit machine-only route.

Audit reproducibility before expanding routine use of human overrides: the current version-1 manifest
records the label policy but not the exact annotation heads. Persist the annotation IDs/revisions
actually used in a human-override export, so later reviews cannot obscure its inputs. Retain worker
execution as the selection boundary: capture one consistent set of current annotation heads, including
explicit no-head records and deferred heads. Render labels and review-input provenance from that same
selection. Persist the checksummed review-input artifact alongside outputs, referenced by manifest
version 2, and include the human responsibility configuration. Preserve version-1 readers and exports.
Large selections belong in artifacts or persisted rows, never Celery messages. A retry must reuse any
already durably captured selection; an attempt whose entire transaction rolled back has not captured
one. Do not add a separate request-time review snapshot or change the label resolver.

Exit: a verified/corrected record exports the current human label by default; an unreviewed or deferred
record follows the existing machine fallback; explicit machine-only export still reproduces machine
results. Prior exports and their artifacts remain unchanged and attributable.

### 6. Verify and roll out

Use forward migrations and an explicit deployment order: migrate and deploy backend support first,
then deploy the UI that sends automatic intent and removes browser-created aggregation. Compatibility
checks must cover older clients and in-flight/historical manual runs. Existing matching-aggregation
reuse protects overlaps, but an old browser that sends its former implicit creation request cannot be
promised the new read-only-page behavior; document the required client refresh.

Run the applicable locked checks from [CONTRIBUTING](../CONTRIBUTING.md) and the
[engineering policy](18-engineering-and-quality.md), including contract generation/drift, PostgreSQL
migration/integration, Redis/outbox recovery, scientific regression coverage, frontend tests and builds.
No new method dependencies or model downloads are required for deterministic fixtures.

## Acceptance matrix

| Scenario | Required outcome |
| --- | --- |
| Start ordinary suggestions, then close all browsers | Server produces a completed suggestion set or visible failure |
| Finish methods before aggregation | UI says combining/queued; method status retains its existing meaning |
| Select an incomplete reference method set | Ordinary request fails validation before dispatch; method-only remains possible |
| Required predictions contain abstentions or errors | Presence and vote semantics remain unchanged |
| A failed batch leaves missing predictions | No fabricated output; blocked/failed workflow with no partial suggestion set |
| All present evidence yields no usable vote | Completed `no_data` result, not orchestration failure |
| Empty dataset or simultaneous last-batch completions | One deterministic completion outcome without duplicate aggregation |
| Worker crash, broker outage, redelivery, or identical manual/automatic requests | Durable intent and idempotent recovery; no lost or duplicate matching result |
| Permanent aggregation failure and subsequent page visits | No retry loop; explicit retry preserves attempt history |
| Failed/cancelled run or ignored experimental method failure | Existing run failure policy is honored and displayed accurately |
| Open any picker or run page | No creation, retry, or working-pointer mutation |
| Save defaults concurrently; start from a stale revision | `409` with recoverable draft; no silent configuration substitution |
| Change saved settings after creating a run | Existing resolved configuration, hashes, and results remain unchanged |
| Open another result or create a newer run | Team working selection and annotation history remain unchanged |
| Use a completed aggregation from a failed parent run | Existing explicit review/export access remains valid |
| Review without classification; switch evidence within a snapshot | Existing append-only stream and conflict handling remain intact |
| Human correction, human `unknown`, unreviewed record, deferred head | Export defaults and fallback follow the documented existing resolver |
| Export while reviews change, retry, or review again later | Exact selected annotation provenance remains reconstructible |
| Historical run/config/export or explicit machine-only API request | Existing inputs and outputs retain their meaning |
| Both locales, keyboard, narrow viewport, session recovery | Clear stages, stable context, readable wrapping, and no unauthorized writes |

## Boundaries

This increment does not add alternative aggregation strategies, redefine the published reference
ensemble, calibrate method confidence, transfer reviews between snapshots, introduce publication
sign-off, or create a general workflow engine or multi-preset library. Export format support and the
requirement for a completed aggregation remain unchanged; manual-annotation-only export is separate
work. Reuse existing canonical resources and preserve scientific history throughout.
