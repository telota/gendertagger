# Evaluation design

## Principle

Evaluation is a first-class, versioned product of the system rather than a separate notebook afterthought.

A benchmark is not automatically "ground truth". The reference study uses GND-linked entries as an authority benchmark while acknowledging authority and curation bias.

## Evaluation definition

An Evaluation references:

- DatasetSnapshot
- Run / selected MethodExecutions
- benchmark/reference definition and version
- aggregation execution where relevant
- metric configuration
- generated artifacts/report

## Reference metrics

Per method:

- coverage / abstention rate
- label distribution
- accuracy on benchmark where defined
- effective accuracy where abstentions count against coverage
- per-class recall
- precision/F1 where meaningful
- confusion matrix

Ensemble/record level:

- canonical label distribution
- agreement score distribution
- agreement tier distribution
- certainty tier distribution
- human review rate / correction rate

Inter-method:

- pairwise Cohen's kappa on overlapping substantive responses

## Benchmark snapshots

Authority data such as GND should be resolved from a versioned/local snapshot for reproducibility. Record its artifact checksum and date/version.

## Scientific regression fixtures

Create a small frozen TEI fixture containing representative cases:

- ordinary male/female forenames
- ambiguous names
- missing forename / initials
- relational parenthetical qualifiers
- title-only entries
- institutional names
- conflicting GND/context
- malformed/edge data

The expected normalized predictions and reference aggregation outputs should become regression tests before refactoring the old script away.

## Alternative aggregation experiments

The infrastructure may later support confidence-weighted voting or different ensembles, but these are separate versioned AggregationExecutions/Evaluations. They must not silently replace the published reference strategy.
