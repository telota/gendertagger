# ADR-0007: Version raw-label normalization and preserve outcome semantics

**Status:** Accepted

## Context

The legacy CSV aggregator used one permissive fallback: every label not recognized as male, female,
institution, or a no-answer sentinel became substantive `unknown`. That also converted the literal GND
`error` sentinel and future schema-drift values to `unknown`. The canonical vNext contracts instead require
`unknown`, `abstain`, and `error` to remain distinct, while the reference aggregation still needs inspectable,
method-specific mappings.

## Decision

Each of the ten Phase 1 methodological components owns an immutable, named normalization profile with a
stable `normalization_version`. Normalization is pure and applies these rules:

- known male, female, institution, leaning, and ambiguous labels use the explicit adapter profile;
- known ambiguous values such as `andy`, `conflict`, `uncertain`, `unisex`, and `unknown` produce
  `status=success` with canonical label `unknown`;
- absent values and known no-input sentinels produce `status=abstain` with no label;
- the explicit technical sentinel `error` produces `status=error` with no label;
- other unparseable values produce `status=abstain`, never an invented substantive label;
- matching strips and case-folds strings, while the exact raw label and raw output remain preserved;
- normalization version and outcome reason are recorded in prediction metadata.

The ten profiles cover the parenthetical-qualifier rule, GND, gender-guesser, Wiki-Gendersort, HIVOTO,
nomquamgender, both Hugging Face classifiers, the local LLM, and experimental HIVOTO-XGBoost. Model and data
access remain responsibilities of the later concrete adapters.

## Consequences

The three legacy GND rows carrying the literal `error` value are now technical errors rather than substantive
`unknown` predictions. Unexpected adapter labels abstain visibly with retained raw evidence, so schema drift
cannot silently enter a vote as `unknown`. Golden regression fixtures must characterize this accepted vNext
reference semantic explicitly. Any mapping change requires a new normalization version, an update to the
normative methods document, and a superseding ADR.
