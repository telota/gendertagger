# ADR-0051: Partial reference aggregation (`reference_partial_v1`)

**Status:** Accepted

## Context

`reference_v1` requires a result for all nine reference methods (`REFERENCE_REQUIRED_METHODS`) before
it will aggregate a run at all — [docs/07-methods-and-aggregation.md](../07-methods-and-aggregation.md)
states this deliberately: "A missing required method fails aggregation rather than silently changing
the ensemble." The requirement exists so that a `reference_v1` result always means the same published
priority chain and pooled vote, never a quietly smaller ensemble under the same name.

In practice, six of the nine methods need a compiled lookup snapshot or model manifest
(`gnd`, `wiki_gendersort`, `hivoto`, `hf_distilbert`, `hf_genderize`) or deployment-specific
configuration (`local_llm`) that a given deployment may not have provisioned yet. A run can complete
successfully with whichever methods a deployment actually has configured, but `reference_v1` then
rejects aggregating it outright (`409 resource_conflict`), with no path to a result at all until every
method is provisioned — discovered directly against a real deployment missing six of the nine.

The guided presentation (D27) in particular has no per-method configuration step of its own: it selects
every registered method automatically, so a deployment missing some assets could never produce a
result through it at all before this decision.

## Decision

Add `reference_partial_v1` as a second, distinct `AggregationStrategy` value. It runs the same priority
chain and pooled vote as `reference_v1` (`parenthetical_qualifier` → `gnd` → an unweighted vote), over
whichever of the nine reference methods the aggregation's own selection actually includes — never fewer
than that selection (every method it does include must still have a complete result for every person),
but never required to be the full nine.

- `aggregate_reference_predictions` and `assess_reference_predictions`
  (`gendertagger.domain.aggregation`, `aggregation_assessment`) take a `require_full_set: bool = True`
  parameter. `True` (the default) is `reference_v1`, unchanged. `False` skips the full-set check and
  reads every pooled/override method through `Mapping.get`, so an absent method simply does not vote —
  it is never treated as an implicit abstain, which it did not do.
- The repository's method-selection validation
  (`SqlAlchemyAggregationRepository._validate_reference_method_selection`) accepts any non-empty subset
  of the allowed reference methods for `reference_partial_v1`, each at most once; `reference_v1` keeps
  requiring the exact nine.
- The executor's per-person completeness check
  (`AggregationExecutor._assess_people`) requires every person to have a result for every method in the
  aggregation's *own* selection (`AggregationPredictionMatrix.selected_methods`), not a hardcoded nine —
  for `reference_v1` that is still the nine, since validation already enforced it; for
  `reference_partial_v1` it is whatever was selected.
- A new deployment-wide setting, `allow_partial_reference_aggregation` (default `true`), gates whether
  `reference_partial_v1` may be used at all. `AggregationService.create_aggregation` rejects a
  `reference_partial_v1` request with `403 partial_aggregation_disabled` while the setting is off.
  Administrators change it at `PATCH /admin/settings/aggregation` (ADR-0040's settings singleton, a
  new column unrelated to branding).
- Persisted result provenance records `metadata.strategy` as whichever strategy actually ran
  (`"reference_v1"` or `"reference_partial_v1"`) — never silently relabels one as the other.

## Consequences

- A deployment can get usable results immediately with whatever methods it has configured, instead of
  needing all nine before `reference_v1` will aggregate anything.
- `reference_v1` itself is untouched: identical required-method set, identical failure on a missing
  method, identical persisted strategy label for every existing result.
- A `reference_partial_v1` result is never confused with `reference_v1`: distinct strategy string,
  distinct persisted provenance, distinct selection-validation path.
- Rejected alternative: relaxing `reference_v1`'s own completeness requirement instead of adding a
  second strategy. Rejected because it would make what "`reference_v1`" means depend on which methods
  happen to be configured on a given deployment at a given time — exactly what the existing design
  explicitly guards against.
- Follow-up (not built here): a before/after visualization in guided mode, and whether "Statistik &
  Methoden" belongs as its own tab versus a link from the generate step — both explicitly deferred by
  the user to a later session.
