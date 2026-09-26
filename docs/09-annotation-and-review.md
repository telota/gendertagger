# Annotation and review

## Role of the UI

The browse/game interface is an annotation client. It is not a second datastore and it does not contain independent classification logic.

The UI reads candidates from FastAPI and writes annotations through FastAPI.

## Annotation before classification

A successfully imported snapshot can be annotated before any classification has run. The canonical
`GET /api/v1/snapshots/{snapshot_id}/annotation-items` collection projects every imported person and
their current human decision as `SnapshotAnnotationItem`. It returns name and identity fields,
`workflow_state`, `review_revision`, `current_annotation_id`, `review_action`, and `human_label`.
It does not invent machine labels, confidence, or certainty for unclassified data. A person without an
annotation has revision zero, state `unreviewed`, and null decision fields; a deferred head has a null
human label, preserving the distinction between a workflow decision and the `unknown` gender label.

The collection supports case-insensitive `q` search across TEI identifier and names, repeated
`workflow_states`, and an optional `human_label`. Results use stable `(tei_id, person_record_id)`
ordering and cursor pagination; the cursor binds the snapshot and every filter. Changes to review
state can change membership in a filtered query, but never its sort key. Clients reload a filtered
list after appending a decision. `GET /api/v1/snapshots/{snapshot_id}/annotation-items/{tei_id}` reads
an exact record even when it is outside the current page. Both resources require a ready snapshot and
ordinary project read access.

Writes use the existing `POST /api/v1/annotations` command and reviewer permission, leaving
`aggregated_result_id` unset when there is no machine evidence. Manual label selection is a `correct`
action; machine verification is offered only when a machine result is present. Optional classification
evidence does not create a separate review stream: decisions and revisions belong to the same person
in the same snapshot, regardless of the selected run. A different snapshot has its own stream.

## Review queue

Triage is ordered on the server, not in the browser. `GET /api/v1/review-items` accepts `sort=uncertainty`
(the default) or `sort=tei_id`, and `uncertainty` applies the versioned `review_triage_v1` rank:

1. `contested`
2. `low`
3. `uncertain`
4. `single`
5. `no_data`
6. authority-vs-ensemble disagreement
7. explicit prediction errors
8. every remaining record

A certainty tier that carries its own rank wins over both flags, and records sharing a rank keep the stable
`(tei_id, person_record_id)` order. Every rank input is immutable for a completed aggregation, so annotating a
record never moves it between cursor pages; review state stays a filter and never becomes a sort key. See
[ADR-0022](decisions/ADR-0022-uncertainty-first-review-ordering.md).

The exact UI ordering can evolve without changing scientific results as long as the underlying
selection/filter is explicit. Changing the rank itself is a new policy version rather than an in-place edit,
because outstanding cursors describe the traversal it defines.

## Annotation model

`AnnotationCreate` in [`models/review.py`](../backend/src/gendertagger/models/review.py) is the
optimistically concurrent command that appends one human decision. It carries `snapshot_id`,
`tei_id`, `action`, an optional `label`, an optional `comment`, an optional `aggregated_result_id`
identifying the machine result under review, and `expected_revision`.

The persisted `Annotation` read model adds the server-owned facts: `id`, the resolved
`person_record_id`, `reviewer_user_id`, `supersedes_annotation_id` when the decision corrects an
earlier review, `resulting_revision`, and `created_at`.

## Actions

`ReviewAction` defines three append-only editorial actions:

- `verify`: confirm the label under review
- `correct`: replace it with a different label
- `defer`: mark the record as needing further research

`verify` and `correct` both require a `CanonicalLabel` (`male`, `female`, `unknown`, or
`institution`); `defer` must not carry one. Recording `unknown` or `institution` is therefore a
`correct` action carrying that label, not a separate action of its own.

`defer` is a review workflow state, not a canonical gender label. `ReviewWorkflowState` projects the
resulting stream state as `unreviewed`, `reviewed`, or `deferred`.

## Final decision

A derived final decision resolves:

```text
latest valid human annotation, if present
otherwise selected machine aggregation
```

Do not copy the human label back into the Prediction or AggregatedResult rows.

## Auditability

Human annotation is part of scholarly provenance. Ordinary review history is never hard-deleted.
Administrative redaction and audit-logged deletion are recorded in
[`22-future-development.md`](22-future-development.md).

`GET /api/v1/annotations?snapshot_id=&tei_id=` makes that history readable. It returns an
`AnnotationHistory`: the person's `ReviewState` plus every annotation in the stream, newest first, each as an
`AttributedAnnotation` carrying the reviewer's display name. The chain is complete by construction —
revisions run without gaps from the current `revision` down to 1 — so the head is the current decision and
each entry supersedes the next. A reviewer who receives `409 annotation_conflict` reloads this resource,
reads what changed and who changed it, and appends against its `revision`. Like every project read, it is
visible to members of the snapshot's project only, so reviewer names do not leave the project
([ADR-0033](decisions/ADR-0033-project-scoped-membership-roles.md)).


## Multi-user concurrency

The append-only annotation model must also handle two reviewers opening the same record. Maintain a monotonically increasing review revision for each person/snapshot decision stream.

Every annotation/correction command includes `expected_revision`, the revision the browser observed. If it is stale, FastAPI returns `409 Conflict` with `annotation_conflict`; the client reloads the current review state before another write.

This is optimistic concurrency over the **review stream**, not mutation/versioning of an Annotation row. Historical annotations remain immutable. The domain revision is authoritative; mirroring it into HTTP ETag headers is recorded in [`22-future-development.md`](22-future-development.md).

## Review query API

Review candidates must be queryable server-side by uncertainty, agreement, final label, review status, authority/ensemble conflict, method result, and error presence, and must be **sorted** server-side by the triage rank above. The browser must not download the full snapshot and implement scientific triage locally. A dedicated `review-items` resource is preferred over UI-page-specific endpoints.

Cursors are scoped to the filters *and* the sort. Continuing a cursor under a different query returns `422` with `invalid_cursor` instead of silently reordering a partially reviewed queue.

Certainty tier, agreement tier, and review state each accept several values, and a record matches when it has any of them, so a queue that spans two tiers is one ordered query rather than two streams merged in the browser. `GET /aggregations/{aggregation_id}/review-summary` counts an aggregation's results by certainty tier, agreement tier, review state, final label, and review action, so a client can show how many records a queue holds, how many are still unreviewed, and how many were verified versus corrected, without downloading them. See [`05-api.md`](05-api.md#review-summary).
