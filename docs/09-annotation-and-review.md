# Annotation and review

## Role of the UI

The browse/game interface is an annotation client. It is not a second datastore and it does not contain independent classification logic.

The UI reads candidates from FastAPI and writes annotations through FastAPI.

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

A human decision should capture:

- project/person (`tei_id`)
- snapshot context
- label or review action
- reviewer identity
- timestamp
- optional comment/reason
- aggregation/result being reviewed
- optional source/evidence reference
- superseded annotation when correcting a prior review

## Actions

Suggested v1 actions:

- verify existing label
- correct label
- set `unknown`
- set `institution`
- defer / needs further research

`defer` is a review workflow state, not necessarily a canonical gender label.

## Final decision

A derived final decision resolves:

```text
latest valid human annotation, if present
otherwise selected machine aggregation
```

Do not copy the human label back into the Prediction or AggregatedResult rows.

## Auditability

Human annotation is part of scholarly provenance. Do not hard-delete ordinary review history. Administrative redaction/deletion, if ever needed, must be explicit and logged.

## Game mechanics

If playful/game mechanics are retained, scoring/streaks/UI effects must remain outside the scientific annotation semantics. A click that produces an annotation must still map to the same explicit reviewed decision and reviewer identity.


## Multi-user concurrency

The append-only annotation model must also handle two reviewers opening the same record. Maintain a monotonically increasing review revision for each person/snapshot decision stream.

Every annotation/correction command includes `expected_revision`, the revision the browser observed. If it is stale, FastAPI returns `409 Conflict` with `annotation_conflict`; the client reloads the current review state before another write.

This is optimistic concurrency over the **review stream**, not mutation/versioning of an Annotation row. Historical annotations remain immutable. ETags may later mirror the same revision, but the domain revision is authoritative.

## Review query API

Review candidates must be queryable server-side by uncertainty, agreement, final label, review status, authority/ensemble conflict, method result, and error presence, and must be **sorted** server-side by the triage rank above. The browser must not download the full snapshot and implement scientific triage locally. A dedicated `review-items` resource is preferred over UI-page-specific endpoints.

Cursors are scoped to the filters *and* the sort. Continuing a cursor under a different query returns `422` with `invalid_cursor` instead of silently reordering a partially reviewed queue.
