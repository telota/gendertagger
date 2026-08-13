# ADR-0008: Make reference aggregation completeness and ties explicit

**Status:** Accepted

## Context

[ADR-0003](ADR-0003-reference-aggregation.md) fixes the published priority chain, but the legacy script relied
on row order for unresolved substantive vote ties and represented missing method files as warnings. Those
behaviors are unsafe in a reproducible service. The normative design also states that ties must be transparent
and that the reference configuration must fail when required published methods are unavailable.

## Decision

The pure `reference_v1` aggregator requires one validated prediction result for each of the two authority
methods and seven pooled published methods. A result may be `success`, `abstain`, or `error`; an absent required
method is not treated as an abstention. Experimental HIVOTO-XGBoost may be supplied for provenance but never
enters the reference vote. Unknown method identifiers fail validation.

The parenthetical-qualifier rule has first priority whenever it returns `status=success`, including canonical
`unknown`. GND has second priority only for successful non-`unknown` labels. Otherwise the seven pooled methods
cast one unweighted vote each; method confidence never changes vote weight.

If `unknown` ties one substantive label for the largest count, the substantive label wins. If multiple
substantive labels remain tied, aggregation returns `outcome=unresolved_tie`, `label=null`, the deterministic
canonical-order `tied_labels`, and complete pooled vote counts. It never chooses a label from insertion or
iteration order. No pooled vote produces `outcome=no_data` and `label=null`.

Authority decisions also store the number of non-abstaining comparison methods and how many agree with the
override. A non-substantive GND `unknown` is excluded from parenthetical support comparisons, matching its
non-voting authority semantics.

## Consequences

Callers must distinguish an unavailable MethodExecution from a persisted per-record abstention or error before
aggregation. Unresolved ties and no-data outcomes are explicit states rather than members of the four-label
alphabet. Persistence and API layers can serialize the decision without inventing a label, and agreement and
certainty can be derived deterministically from stored counts in the next Phase 1 step.
