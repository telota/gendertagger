# ADR-0027: GND-gendered benchmark and evaluation metrics (`gnd_benchmark_v1`)

**Status:** Accepted

## Context

Phase 6's exit criterion is that "reference study outputs can be regenerated from a stored run" (see
[`15-implementation-plan.md`](../15-implementation-plan.md)), where the reference study is the published paper
this migration exists to carry forward (`docs/paper/article.tex`). The paper defines a specific evaluation
methodology against the *schleiermacher digital* register: a GND-gendered benchmark subset (entries whose GND
authority record resolves to `male`/`female`, excluding `institution` and unresolved/abstained entries -- 2,253
of 8,277 in the published run), a 7-method accuracy/recall table (the pooled methods only -- GND is excluded
because it *is* the benchmark, and the parenthetical-qualifier rule is excluded for negligible GND overlap), and
an 8-method pairwise Cohen's kappa matrix (the 7 pooled methods plus the experimental `hivoto_xgboost`, again
excluding GND and parenthetical-qualifier for insufficient coverage overlap). See
[`10-evaluation.md`](../10-evaluation.md) and [`07-methods-and-aggregation.md`](../07-methods-and-aggregation.md).

This evaluation roster is **not** the same as the `reference_v1` aggregation-vote roster
(`gendertagger.domain.aggregation.REFERENCE_REQUIRED_METHODS`/`REFERENCE_IGNORED_METHODS`): the aggregation vote
includes the parenthetical-qualifier rule and excludes `hivoto_xgboost`, while the evaluation benchmark excludes
parenthetical-qualifier and includes `hivoto_xgboost` for kappa. Reusing the aggregation roster directly for
evaluation would silently misrepresent the published methodology.

Real reproduction data for the full case study exists locally (`data/raw/schleiermacher/Register/Personen/`,
`data/raw/GND/authorities-gnd-person_dnbmarc.mrc.xml`) but is never committed to the repository; only small
approved excerpts join `tests/fixtures/scientific/` as regression fixtures, consistent with existing project
practice. The full-corpus reproduction happens through the ordinary asynchronous import/run/aggregation/
evaluation pipeline once persistence exists (a later ADR), not through this record.

## Decision

Evaluation is a general-purpose capability, not a hardcoded reproduction of one paper's numbers.
`EvaluationDefinition` (`gendertagger.models.evaluation`) is a versioned, immutable configuration selecting:

- `benchmark_method`: the method supplying benchmark ground truth (`gnd` by default);
- `benchmark_label_filter`: which of that method's successful labels count as the benchmark (`(male, female)` by
  default -- the "gendered" filter);
- `scored_methods`: methods entering the corpus-wide coverage table and the benchmark-scoped accuracy/recall
  table (the seven pooled reference methods by default);
- `kappa_extra_methods`: methods entering the pairwise Cohen's kappa matrix in addition to `scored_methods`, but
  not the accuracy table (`hivoto_xgboost` by default);
- `confidence_level`: the two-sided confidence level for per-class recall intervals (`0.95` by default).

`EvaluationDefinitionId.gnd_benchmark_v1` is the default definition and reproduces the paper's exact rules. A
future definition (a different benchmark method, corpus, or method roster) is a new enum member with its own
configuration, versioned the same way `AggregationStrategy` versions aggregation behavior -- never a silent
change to `gnd_benchmark_v1`'s meaning.

`scored_methods`' default value cannot import `REFERENCE_POOLED_METHODS` directly: the import-linter contract
"Canonical models are independent of domain and infrastructure" forbids `gendertagger.models` from importing
`gendertagger.domain`. The default is therefore a models-local literal tuple, guarded against drift by
`tests/contracts/test_evaluation_contract.py::test_default_scored_methods_matches_the_reference_pooled_roster`,
which asserts equality against `gendertagger.domain.aggregation.REFERENCE_POOLED_METHODS` directly (tests carry
no import-linter restriction).

Metric computation is pure and split by concern under `gendertagger.evaluation` (forbidden from importing
`api`/`cli`/`db`/`services`/`storage`/`tasks`, mirroring the existing `domain` contract, but free to import
`domain` -- evaluation is a sibling layer, not a replacement for it):

- `benchmark.py` selects the benchmark subset (persons whose benchmark-method result matches the label filter);
- `metrics.py` computes corpus-wide per-method coverage/label distribution and benchmark-scoped accuracy,
  effective accuracy (correct divided by the full benchmark size, so abstentions count against the method --
  matching the paper's definition), and confusion matrices;
- `recall_ci.py` wraps `statsmodels.stats.proportion.proportion_confint(method="wilson")` for per-class recall
  confidence intervals;
- `kappa.py` wraps `sklearn.metrics.cohen_kappa_score`, restricted per pair to entries both methods answered,
  reporting `kappa=None` (rather than a misleading number) when fewer than two entries are co-answered or when
  every co-answered label is identical for both methods;
- `ensemble.py` computes canonical-label, agreement-tier, and certainty-tier distributions from a supplied
  `AggregatedResult` set, plus caller-supplied human-review counts (it does not read `ReviewState`/`Annotation`
  itself);
- `report.py` orchestrates the above into one immutable `EvaluationReport`, enforcing the completeness boundary
  (every person must carry a `Prediction`, of any status, from every method in `definition.required_methods`)
  before computing anything, raising `EvaluationInputError` otherwise -- mirroring
  `AggregationExecutor`/`aggregate_reference_predictions`'s own completeness check.

`scikit-learn` and `statsmodels` become core (non-extra) dependencies: evaluation is a required Phase 6
capability of the base service, not a per-method opt-in adapter like the existing `hivoto-xgboost` extra
(which now only adds `xgboost`, since `scikit-learn` moved to core).

This record covers only the pure computation layer (`models/evaluation.py` and `gendertagger.evaluation`). A
subsequent ADR covers the asynchronous persistence, outbox dispatch, and API surface that make Evaluation a full
resource comparable to `AggregationExecution`.

## Consequences

- Evaluation results depend only on persisted evidence and configuration, never on iteration or insertion order,
  matching the reference aggregation's own reproducibility guarantee.
- A method absent from `scored_methods`/`kappa_extra_methods` (e.g. the parenthetical-qualifier rule) is simply
  not evaluated for accuracy/kappa; it is not silently included with degenerate statistics.
- `EvaluationReport` and its constituent models are exhaustively self-validating (every count invariant --
  confusion-matrix sums, class-count sums, correct-not-exceeding-answered, etc. -- is a Pydantic model validator,
  not merely asserted in tests), so a malformed report can never be constructed, only rejected.
- The evaluation roster's divergence from the aggregation-vote roster is a deliberate, documented fact of the
  published methodology, not an inconsistency to reconcile.
- No plotting dependency (e.g. matplotlib) is introduced; evaluation artifacts are structured JSON/CSV data,
  never a rendered report or regenerated figure, per Phase 6 scope.
