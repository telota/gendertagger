# ADR-0019: nomquamgender adapter

**Status:** Accepted

## Context

`nomquamgender` is the fifth Phase 5 method and the last name-based adapter in this migration batch. It is a
statistical first-name classifier: for each token the `nomquamgender` library returns a female probability
`p(gf)`, which the legacy pipeline thresholded into a categorical label and reduced by the shared consensus.
It reuses the name-based adapter pattern from
[ADR-0012](ADR-0012-name-based-classifier-adapter-pattern.md) and the frozen `nomquamgender_v1` profile. The
legacy decision threshold was `0.1`; the former illustrative YAML configuration instead showed `0.5`, which
is degenerate because it collapses the uncertain band and overlaps the male and female decisions. See
[methods and aggregation](../07-methods-and-aggregation.md).

## Decision

Port `classify` verbatim: `p(gf) <= threshold` is male, `p(gf) >= 1 - threshold` is female, otherwise
uncertain; a missing or NaN probability is unknown. Per token the adapter annotates with `nomquamgender`,
classifies each probability, takes the priority consensus, and normalizes against the frozen
`nomquamgender_v1` profile. The threshold is resolved run configuration defaulting to the reference `0.1`
and constrained to the open interval `(0, 0.5)` so the male and female bands can neither overlap nor vanish;
the then-current illustrative configuration was corrected from the degenerate `0.5` to `0.1`. NaN
probabilities are preserved as null in raw output, and the adapter reports no `method_confidence` because the
vote is taken over labels, not over one calibrated probability.

`nomquamgender` is the opt-in `nomquam` extra, imported lazily; its absence raises `MethodDependencyError`
and fails the batch permanently. The annotator backend is injectable for testing and built once per adapter.

## Consequences

- Reproduces the legacy `nomquamgender` output exactly on all 8277 reference-corpus records at threshold
  `0.1`.
- The `(0, 0.5)` constraint rejects the previously shipped degenerate `0.5`; the example configuration now
  uses the reference `0.1`, so resolving it through the registry produces the reference behavior.
- `numpy` and `pandas` enter the dependency closure only through the `nomquam` extra, never the core service.
- `p(gf)` is retained as descriptive provenance and never influences the vote, preserving the separation
  between method output and the aggregation.
