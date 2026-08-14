# ADR-0022: Order the review queue by a versioned uncertainty-first rank

**Status:** Accepted

## Context

[Annotation and review](../09-annotation-and-review.md) requires the review queue to prioritize records by
uncertainty and disagreement, but the `review-items` collection returned only register order by `tei_id`.
Reviewers therefore had to page through confident records to reach contested ones, or reproduce the triage
order in the browser, which the [frontend integration policy](../17-frontend-integration.md) forbids.

Ordering interacts with keyset pagination. A sort key that a concurrent annotation can change would move a
record between pages and make continuation skip or repeat candidates. The queue must therefore order by
evidence that is immutable for a completed aggregation, not by review progress.

Two triage signals were not available as ordinary columns. Authority-versus-ensemble disagreement is derivable
from the stored override counts, but technical prediction errors were only derivable through a correlated
subquery over the aggregation's member method executions. Sorting by such a subquery forces it to be evaluated
for every candidate row of every page.

## Decision

The review queue exposes an explicit `sort` parameter with `uncertainty` as its default and `tei_id` for
predictable full traversal. `uncertainty` applies the versioned `review_triage_v1` policy, which assigns one
integer rank per candidate. A lower rank is reviewed earlier:

| Rank | Condition |
|---|---|
| 0 | `certainty_tier=contested` |
| 1 | `certainty_tier=low` |
| 2 | `certainty_tier=uncertain` |
| 3 | `certainty_tier=single` |
| 4 | `certainty_tier=no_data` |
| 5 | authority-versus-ensemble disagreement |
| 6 | a technical prediction error |
| 7 | every remaining record |

A certainty tier that carries its own rank wins over both flags, so a contested record with a failed method
still sorts as contested. `no_data` ranks after `single` because a record without usable evidence still needs
a human label, but carries no disagreement to adjudicate. `high` has no rank of its own: a confident record is
promoted only by an authority conflict or a prediction error, which is why both flags rank after every
substantive tier. Records sharing a rank keep the stable `(tei_id, person_record_id)` tie-breaker.

Every rank input is immutable for a completed aggregation. `workflow_state` and the review revision are
deliberately excluded from the sort key and remain filters. Technical prediction errors are projected onto
`aggregated_results.has_prediction_error` when the aggregation persists its results, so the rank is a function
of one row.

Cursors are scoped to the requested sort as well as to the filters, and carry the rank of the last returned
item alongside its `tei_id`. Continuing a cursor under a different sort fails as an invalid cursor rather than
silently reordering a partially reviewed queue.

## Consequences

Reviewers receive the most uncertain records first without client-side triage, and the ordering is explicit,
named, and versioned rather than implied by the UI. Because the sort key is immutable, annotating a record on
one page never disturbs later pages of the same traversal.

`has_prediction_error` becomes persisted, publicly readable state on an aggregated result rather than a
per-query derivation. It is a projection of immutable prediction evidence, so re-running an aggregation
reproduces it, and the accompanying migration backfills existing rows from their member executions.

The rank is a bucket order, not a continuous uncertainty score: within one rank, records are returned in
register order rather than by `agreement_score`. Refining the order inside a rank changes the traversal that
existing cursors describe and therefore requires a new policy version, `review_triage_v2`, rather than an
in-place edit of these ranks.
