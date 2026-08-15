# Evaluation design

## Principle

Evaluation is a first-class, versioned product of the system rather than a separate notebook
afterthought. Every evaluation is a persisted, independently rerunnable execution whose output is an
immutable, checksummed JSON artifact.

A benchmark is not automatically "ground truth". The reference study uses GND-linked entries as an
authority benchmark while acknowledging authority and curation bias.

## Evaluation definition

`EvaluationDefinition` (`gendertagger.models.evaluation`) is the frozen, `extra="forbid"`
configuration that fully determines what an evaluation measures. `EvaluationDefinitionId` defines a
single member, `gnd_benchmark_v1`, which reproduces the published study's exact rules; see
[`ADR-0027`](decisions/ADR-0027-gnd-benchmark-evaluation-definition.md) for the rationale.

| Field | Default | Meaning |
| --- | --- | --- |
| `id` | `gnd_benchmark_v1` | Versioned definition identifier |
| `benchmark_method` | `gnd` | Method supplying benchmark ground truth |
| `benchmark_label_filter` | `(male, female)` | Which of that method's successful labels form the benchmark |
| `scored_methods` | the seven pooled reference methods | Methods entering the coverage and accuracy/recall tables |
| `kappa_extra_methods` | `("hivoto_xgboost",)` | Kappa-only methods, excluded from the accuracy table |
| `confidence_level` | `0.95` | Two-sided confidence level for per-class recall intervals |

The default `scored_methods` are `gender_guesser`, `wiki_gendersort`, `hivoto`, `nomquamgender`,
`hf_distilbert`, `hf_genderize`, and `local_llm`. The import-linter contract keeping
`gendertagger.models` independent of `gendertagger.domain` forbids importing
`REFERENCE_POOLED_METHODS` here, so this default is a models-local literal guarded against drift by
`tests/contracts/test_evaluation_contract.py`.

Model validators reject an invalid configuration at construction: method names must match
`METHOD_NAME_PATTERN`, the label filter must be non-empty and duplicate-free, `scored_methods` and
`kappa_extra_methods` must each be duplicate-free and disjoint from one another, and
`benchmark_method` must appear in neither. Two derived properties drive the engine:
`required_methods` (benchmark plus scored plus kappa-only) and `kappa_methods` (scored plus
kappa-only).

The evaluation roster deliberately differs from the aggregation-vote roster described in
[`07-methods-and-aggregation.md`](07-methods-and-aggregation.md): evaluation excludes the
parenthetical-qualifier rule for negligible benchmark overlap and includes `hivoto_xgboost` for
kappa only.

### Execution resource

An `EvaluationExecution` references:

- `run_id` — the evaluated run; the dataset snapshot is resolved through the run rather than stored
  a second time
- `method_execution_ids` — the exact ordered selection, persisted in `evaluation_method_executions`
  with an explicit `position`
- `definition`, `resolved_config` (the resolved definition serialized verbatim), and `config_sha256`
  over both
- `aggregation_execution_id` — optional; supplying it enables the ensemble metrics block
- `report_artifact_id` — present only on a completed evaluation
- lifecycle fields `status`, `started_at`, `finished_at`, `failure_class`, `failure_diagnostic`

`EvaluationExecutionStatus` is `pending`, `queued`, `running`, `completed`, `failed`, `cancelled`;
`mark_evaluation_finished` accepts only `completed` and `failed` as terminal transitions.

Creation is rejected unless every selected method execution belongs to the run, carries status
`completed` or `completed_with_errors`, names each stable method exactly once, and the selection
equals `definition.required_methods` exactly — missing methods and unexpected methods are both
errors. A supplied aggregation execution must belong to the same run and be completed. The same
checks run again when inputs are loaded, so a selection invalidated between queueing and execution
fails terminally instead of producing a misleading report.

## Execution and persistence

`POST /api/v1/evaluations` (operator role) resolves the versioned definition, then persists the
execution and a durable outbox dispatch row (`DispatchTarget.evaluation_execution`, queue `cpu`) in
one transaction and returns `202 Accepted`. The dispatch relay publishes
`gendertagger.tasks.execute_evaluation` with the broker `task_id` set to the evaluation execution
id, so a redelivered outbox row cannot fan out into duplicate work.

`EvaluationExecutor` (`gendertagger.services.evaluation_execution`) claims a pending or queued
evaluation, loads its inputs, builds the report, stores the artifact, and marks the execution
finished inside a single transaction. A worker crash therefore exposes either the prior claimable
resource or the complete final report, never a committed partial evaluation. `EvaluationInputError`,
`InvalidResourceStateError`, and Pydantic `ValidationError` are terminal; unclassified failures roll
back and retry with full-jitter exponential backoff up to three attempts, after which a fresh claim
records a sanitized diagnostic (URL credentials redacted, capped at 500 characters).

Reads require the viewer role: `GET /api/v1/evaluations/{id}` returns the lifecycle resource, and
`GET /api/v1/evaluations/{id}/report` returns the stored report bytes with the artifact's media
type.

### Input completeness

`build_report` enforces a completeness boundary before computing anything: every person in the
corpus must carry a `Prediction` from every method in `definition.required_methods`. Presence, not
scientific outcome, satisfies it — `success`, `abstain`, and `error` all count — and a missing
prediction raises `EvaluationInputError`. Input loading additionally verifies that the snapshot's
declared `record_count` matches the number of person records actually read, so a partially imported
snapshot cannot be evaluated.

## Reference metrics

### Per method

`MethodCoverage` is computed corpus-wide for every method in `required_methods`:

- `total`, `coverage_count`, and `coverage_share` (rounded to three decimals)
- `label_distribution` across all four canonical labels
- `abstain_count` and `error_count`

Coverage counts every successful result, including a substantive `unknown`: the method evaluated the
input and returned an ambiguous classification, which is scientifically distinct from abstaining.
Coverage, abstentions, and errors always sum to `total`, enforced by a model validator.

`MethodAccuracy` is computed for `scored_methods` only, restricted to the benchmark subset — the
persons whose benchmark-method result is a successful label inside `benchmark_label_filter`:

- `answered_count` and `correct_count`
- `accuracy` and `effective_accuracy`
- `confusion_matrix`, keyed truth label to predicted label
- `recall`, one `RecallWithCI` entry per benchmark label

### Accuracy versus effective accuracy

`accuracy` divides correct labels by the entries the method actually answered.
`effective_accuracy` divides the same numerator by the full benchmark size, so abstentions count
against the method. Both are reported because either alone misleads: a high-precision, low-coverage
method looks equivalent to a method that answers everything under `accuracy`, while
`effective_accuracy` alone cannot separate being wrong from declining to answer.
`effective_accuracy` matches the published study's definition. Both are rounded to three decimals
and degrade to `0.0` rather than dividing by zero on an empty denominator.

### Per-class recall confidence intervals

`recall_ci.wilson_recall_interval` wraps
`statsmodels.stats.proportion.proportion_confint(method="wilson")` with
`alpha = 1 - confidence_level`. The Wilson score interval is used rather than the normal
approximation because per-class benchmark support can be small and recall can sit at or near 0 or 1,
where the normal interval leaves the unit range. Bounds are clamped into `[0, 1]` and rounded to
three decimals. A class with zero benchmark support returns a degenerate all-zero mapping, since the
interval is undefined without observations.

### Inter-method agreement

`kappa.compute_kappa_matrix` wraps `sklearn.metrics.cohen_kappa_score` over every unordered pair of
`definition.kappa_methods`, generated in `itertools.combinations` order. Each pair is restricted to
co-answered entries — persons for which both methods returned a successful label — and the cell
records that `co_answered_count` next to the coefficient. A cell reports `kappa=None` rather than a
misleading number when either:

- fewer than two entries are co-answered, or
- every co-answered label is identical for both methods, so both raters are constant, expected
  agreement is one, and kappa is undefined.

Values are rounded to three decimals and clamped into `[-1, 1]`, and `KappaCell` forbids a
coefficient when `co_answered_count` is zero.

### Ensemble and record level

`EnsembleMetrics` is populated only when the evaluation names an aggregation execution; otherwise the
report's `ensemble` block stays unset.

- `canonical_label_distribution` counts decided results only — an unresolved tie or a no-data outcome
  carries no canonical label
- `agreement_tier_distribution` over `AgreementTier` and `certainty_tier_distribution` over
  `CertaintyTier` cover every result, since each result carries exactly one tier of each kind
- `human_reviewed_count` counts the snapshot's review states with a revision above zero, and
  `human_correction_count` counts those whose current annotation action is `correct`; review and
  correction rates are derived from these counts and the corpus size

`compute_ensemble_metrics` is pure and receives the review counts from its caller; it does not read
`ReviewState` or `Annotation` itself.

## Report artifact

`EvaluationReport` carries the definition id, the `BenchmarkSummary` (benchmark method, labels, size,
per-class counts), the coverage tuple, the accuracy tuple, the kappa matrix, and the optional
ensemble block. Every count invariant — confusion-matrix sums, class-count sums, correct not
exceeding answered — is a Pydantic model validator rather than a test assertion, so a malformed
report cannot be constructed at all, only rejected.

The executor serializes the report to JSON and stores it through `ArtifactStorage` under logical type
`evaluation_report` and media type `application/json`, subject to a 50 MiB ceiling. The artifact row
records the SHA-256 digest, byte size, run id, and evaluation execution id. Evaluation artifacts are
structured data: no plotting dependency is involved and no figure is rendered.

## Benchmark snapshots

Authority data such as GND is resolved from a versioned local snapshot for reproducibility. The GND
adapter selects its compiled SQLite lookup by content through `GndConfig.lookup_sha256`, and the
compiled database embeds its own provenance rows: `method_name`, `lookup_schema_version`,
`compiler_version`, `source_sha256` (plus `source_sha256s` for multi-file sources), an optional
`source_version`, and the compiling `sqlite_version`. A benchmark result therefore identifies
exactly which authority extraction produced it.

## Scientific regression fixtures

Two frozen JSON oracles under `tests/fixtures/scientific/` pin the scientific behavior. They are
exercised by `tests/domain/test_scientific_regression.py` under the `scientific` pytest marker:

- `legacy_characterization.json` captures the legacy script's outputs together with provenance
  (source repository commit, aggregator blob hash, per-file SHA-256 digests) and a redistribution
  approval restricting the fixture to TEI identifiers and method outputs
- `reference_v1.json` holds the expected normalized predictions and reference aggregation results for
  the same records, pins the normalization profile version of every method, and records each accepted
  difference from the legacy oracle together with the decision that justified it

Ten paired case records cover the representative situations:

- ordinary agreement and tie handling: `unanimous_pooled_vote`,
  `unknown_tie_loses_to_substantive_label`
- relational parenthetical qualifiers: `parenthetical_unknown_override`,
  `parenthetical_institution_override_against_pooled_vote`, `parenthetical_institution_reinforces_llm`
- authority conflict and error propagation: `gnd_override_against_female_majority`,
  `explicit_gnd_error`
- lone answers and ambiguity: `lone_high_certainty_llm_institution`, `lone_uncertain_llm_unknown`,
  `leaning_and_ambiguous_normalization`

These fixtures are the gate against silent scientific drift: a change to normalization or aggregation
must either keep them passing or record an approved, ADR-referenced expected difference. Wider
fixture coverage is tracked in [`22-future-development.md`](22-future-development.md).

## Versioned strategies and definitions

`AggregationStrategy` defines one member, `reference_v1`, and `EvaluationDefinitionId` one member,
`gnd_benchmark_v1`. Alternative ensembles or metric configurations arrive as new enum members with
their own configuration and their own persisted executions, never as a silent change to an existing
one, so published reference results stay reproducible. Candidate alternatives are collected in
[`22-future-development.md`](22-future-development.md).
