# ADR-0012: Name-based classifier adapter pattern and gender-guesser

**Status:** Accepted

## Context

Phase 5 migrates the published classification methods to adapters behind the frozen
`GenderMethod` contract and the Phase 1 normalization profiles. Four of them — `gender_guesser`,
`wiki_gendersort`, `hivoto`, and `nomquamgender` — are name-based: they split a person's forename into
candidate tokens, classify each token independently, and reduce the per-token labels to one raw label.
In the legacy pipeline each script re-declared the same forename token filter and a near-identical
priority consensus; an AST comparison confirmed the skip pattern and the 58-element particle set are
byte-for-byte identical across all four (only the held-out experimental `hivoto_xgboost` differs). These
methods also require method-specific runtime libraries or data that the API and lightweight workers do
not need. `gender_guesser` is the first and cheapest: a pure dictionary lookup through the
`gender-guesser` library with no data file, model, or network dependency. See
[methods and aggregation](../07-methods-and-aggregation.md).

## Decision

Introduce a shared `gendertagger.methods.name_tokens` module that owns, verbatim, the forename token
filter (`usable_forename_tokens`) and a parameterized `consensus_label`. Forename values are split on
whitespace and filtered by the shared skip pattern and particle set; splitting per forename value is
equivalent to the legacy single-column whitespace split. `consensus_label` returns `no_name` for no
tokens and `conflict` when definite male and female labels both occur, otherwise the highest-priority
label wins, with labels absent from the priority list ranked as weakly as the first entry — matching the
reference `PRIORITY_RANK.get(r, 0)`. The label alphabet, priority order, and per-token classification
stay method-specific; only the filter and reduction are shared so they cannot drift.

Adapters declare their runtime library as an opt-in extra under `[project.optional-dependencies]` and
import it lazily. A missing extra raises `MethodDependencyError`, which the batch executor treats as a
permanent (non-retryable) failure, distinct from transient infrastructure errors. Each adapter's backend
is obtained through an injectable factory so unit tests run deterministically without the optional
dependency; the default factory constructs the real backend once and caches it on the adapter instance.

`GenderGuesserMethod` tokenizes `person.forenames`, looks up each token with a case-insensitive
`gender-guesser` detector, takes the consensus over the per-token labels, and normalizes the result
against the frozen `gender_guesser_v1` profile. It reports no `method_confidence` because the dictionary
outcome is categorical and deterministic. The prediction preserves the checked tokens and per-token
results as raw output. `implementation_version` is `gender_guesser_v1`, versioned independently of the
normalization version.

## Consequences

- The core install, API, and CPU workers stay slim; `gender-guesser` is pulled only by the `guesser`
  extra, and enabling it fails loudly and permanently when absent rather than silently degrading.
- The shared token filter is defined once, so the four name-based adapters cannot diverge; changing it is
  a scientific change requiring a new ADR and fixture review.
- Reproduction is exact: on the reference corpus the adapter's raw label matches the legacy
  `gender_guesser` output for all 8277 records, and the shared tokenizer matches legacy tokenization for
  all 8277 records.
- Name-only methods cannot express `institution`, consistent with their frozen profiles.
- The pattern — shared tokens, opt-in extra with lazy import, and an injected, cached backend — is reused
  by the `wiki_gendersort`, `hivoto`, and `nomquamgender` adapters that follow.
- The legacy filter quirk in which dotted particles without a bare form (for example `geb.`, `jr.`)
  survive is preserved deliberately; removing it would change tokenization and require its own ADR.
