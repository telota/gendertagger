# ADR-0003: Preserve the published reference aggregation

**Status:** Accepted

## Context

The published workflow defines a specific aggregation whose output is part of the scientific baseline.
Replacing it implicitly with a newly optimized ensemble would make vNext results incomparable with the
reference study.

## Decision

The first service implementation reproduces the published gendertagger aggregation:

- normalize to `male | female | unknown | institution`
- distinguish abstentions from `unknown`
- parenthetical-qualifier override first
- GND substantive override second
- unweighted vote across the seven pooled published methods otherwise
- per-method confidence recorded but not used as vote weight
- versioned agreement and certainty tiers

HIVOTO-XGBoost remains experimental/outside the reference vote unless an explicit alternative strategy is selected.

## Consequences

Alternative ensemble strategies are allowed only as separately versioned aggregation strategies and evaluations.
