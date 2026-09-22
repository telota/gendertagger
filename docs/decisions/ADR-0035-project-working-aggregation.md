# ADR-0035: An explicit working-aggregation pointer per project

**Status:** Accepted

## Context

A project owns many aggregations over time: one per run, and per D4 in
[`24-frontend-delivery-plan.md`](../24-frontend-delivery-plan.md) potentially several per run once
re-aggregation without re-running methods becomes routine. The Projekte and Übersicht screens need one
number per project — the review summary from `GET /aggregations/{id}/review-summary`
([ADR](ADR-0034-reuse-matching-aggregation-on-creation.md) and the review summary added alongside it) — but a
project has no server-side notion of which aggregation that is.

Deriving it implicitly ("the newest completed aggregation of the newest run of the newest ready snapshot")
fails in a way reviewers would notice immediately. Annotations belong to one `DatasetSnapshot`
([ADR-0002](ADR-0002-immutable-dataset-snapshots.md)) and do not carry forward to a re-import — cross-snapshot
annotation inheritance is listed as deferred in
[`22-future-development.md`](../22-future-development.md#cross-snapshot-comparison-and-annotation-inheritance).
A card computed from "the newest snapshot" would therefore drop to zero reviewed the moment an operator
imports a corrected register, even though the team is still actively working the previous snapshot's queue.
The same problem recurs one level down: a newer run against the same snapshot, for example with a changed
method roster, would silently take over the card and the review queue's target without anyone choosing that.

Which aggregation a team is reviewing against is an editorial decision with consequences — it is what the
review queue, the Übersicht tiles, and (once built) the default export target all point at — so it should be
recorded, not inferred from recency.

## Decision

`Project` gains a nullable `working_aggregation_execution_id`. Setting it is a project-operator action,
`PUT /api/v1/projects/{project_id}/working-aggregation`, with a body naming the `aggregation_execution_id` or
`null` to clear it. The command is rejected unless the aggregation exists, is `completed`, and belongs to a
run whose snapshot belongs to this project; a mismatched project resolves as `404`, like any other resource
outside the caller's project, and a wrong status resolves as `409`, like the aggregation and review-item
routes it is consistent with.

The pointer is read from `AccessibleProject`, alongside every project a caller can already see. It is a
single mutable reference, not an audit trail: the codebase already defers a full history of project changes
—the "Append-only history of role and membership changes" item in
[`22-future-development.md`](../22-future-development.md#append-only-history-of-role-and-membership-changes)
covers memberships, and this decision extends the same deferral to the working-aggregation pointer. Nothing
in the current scope reads who set it or when, so nothing records that yet.

Auto-creating the default aggregation (D4) does not itself change the pointer. A client that wants the
default aggregation to become the project's working aggregation calls the new endpoint explicitly after
`POST /runs/{run_id}/aggregations` returns, the same way it already treats aggregation as a visible step
rather than a hidden one.

## Consequences

- A project card, and the Übersicht tiles, read `working_aggregation_execution_id` from the project and then
  call `GET /aggregations/{id}/review-summary` once; no client-side recency heuristic is needed.
- Re-importing a snapshot or starting a new run never silently moves what a team is reviewing. Moving to a
  newer aggregation is a deliberate action with the same visibility as creating one.
- A project with no working aggregation yet (before the first run completes, or after a project is created)
  simply has no summary to show; the client treats that the same as any other project with no data yet.
- `working_aggregation_execution_id` is a plain pointer, not scientific provenance: it does not appear in
  export manifests or evaluation reports, and changing it does not affect any persisted `AggregatedResult` or
  `Annotation`.
- The FK from `projects` to `aggregation_executions` is a genuine forward reference in table-creation order —
  `projects` is created before `aggregation_executions` in the baseline migration — so the column is declared
  with `use_alter=True`, matching the existing pattern for every other forward-referencing foreign key in
  `db/artifacts.py`.
- Attribution (who set it, when) is deferred, as noted above. Should a later screen need it, the column pair
  can be added without revisiting this decision.
