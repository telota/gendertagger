# Methods, normalization, aggregation, and certainty

This document is **normative for the reference pipeline**. `reference_v1` is the only member of
`AggregationStrategy` in [`gendertagger.config.run`](../backend/src/gendertagger/config/run.py), and the
behavior described here is what
[`gendertagger.domain.aggregation`](../backend/src/gendertagger/domain/aggregation.py) and
[`gendertagger.domain.aggregation_assessment`](../backend/src/gendertagger/domain/aggregation_assessment.py)
execute. Candidate alternative strategies are collected in
[`22-future-development.md`](22-future-development.md).

## Canonical labels

```text
male
female
unknown
institution
```

`institution` is retained because the historical reference corpus contained organizations in the person register and because some methods can express that distinction.

A method may also **abstain**, which is not a label.

## Implemented methodological families

The published pipeline contains ten components across five families:

1. GND authority lookup
2. parenthetical-qualifier rule
3. `gender-guesser`
4. Wiki-Gendersort
5. HIVOTO
6. `nomquamgender`
7. experimental HIVOTO-XGBoost
8. Hugging Face DistilBERT `padmajabfrl/Gender-Classification`
9. Hugging Face BERT `imranali291/genderize`
10. local LLM (`gpt-oss:20b` in the reference study, served locally)

Nine enter the published aggregation. HIVOTO-XGBoost is held out as an experimental extension.

## Inputs

`PersonInput` in [`gendertagger.models.person`](../backend/src/gendertagger/models/person.py) carries, where
available:

- `tei_id` (the source `xml:id`)
- surname
- forename(s)
- birth/death information
- free-text biographical note
- biographical events
- alternative names
- the ordered direct TEI `persName` forms, when the import profile captured them
- GND identifier
- further external identifiers

Name-only methods use the minimum fields they require. Every name-based classifier
(`gender_guesser`, `wiki_gendersort`, `hivoto`, `nomquamgender`, `hf_distilbert`, `hf_genderize`, and
the experimental `hivoto_xgboost`) reads only `forenames`; the GND adapter reads only `gnd_id`; the
parenthetical-qualifier rule reads `surname`, `forenames`, and `note`. The local LLM prompt carries
the complete entry — identifier, name forms, life dates, note, events, GND identifier, and external
identifiers.

### Versioned lookup data

GND, Wiki-Gendersort, and HIVOTO consume separate immutable SQLite lookup artifacts compiled from retained
source artifacts. Their resolved configuration requires `lookup_sha256`; run scheduling resolves that digest
together with the method-specific logical artifact type and records the resulting artifact on the
MethodExecution. Direct filesystem paths are not scientific configuration. Workers materialize and validate
the selected artifact locally, open it read-only, and bulk-resolve a task batch without external network
access. See [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md).

The two Hugging Face transformer adapters and the experimental HIVOTO-XGBoost adapter select
content-addressed multi-file model manifests through the same `lookup_sha256` field and the same
scheduling path. See [ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md).

The GND lookup preserves source gender and entity-type evidence. No input GND ID or no matching row abstains
as `no_gnd`; a corporate body emits `organisation`; a person emits the stable male/female lookup label when
recognized; missing gender and other retained entity types emit `Unbekannt`. The exact source label, gender
URI, preferred name, normalized and raw entity types, and source record status remain in raw output.


## Per-method result

Every adapter returns:

- canonical label or no label
- `success | abstain | error`
- `method_confidence` where available
- raw label
- raw output
- method-specific metadata/provenance

Per-method confidences are recorded but **do not influence the reference vote**.

## Normalization

Raw classifier outputs are mapped onto the shared four-value alphabet by immutable, adapter-owned profiles.
Each profile has a stable normalization version. Comparison strips surrounding whitespace and case-folds
strings, but predictions retain the exact raw label and output.

Outcome semantics are:

| Raw-output category | Canonical result |
|---|---|
| known male, female, institution, or leaning label | `success` with the mapped canonical label |
| known `andy`, `conflict`, `uncertain`, `unisex`, or `unknown` | `success + unknown` |
| absent, blank, `nan`, `no_answer`, `no_gnd`, or `no_name` | `abstain + null` |
| explicit technical `error` sentinel | `error + null` |
| any other unparseable label | `abstain + null` |

The reference profiles are:

| Adapter | Version | Additional raw-label behavior |
|---|---|---|
| parenthetical qualifier | `parenthetical_qualifier_v1` | canonical male/female/unknown/institution values |
| GND | `gnd_v1` | `Männlich`/`Weiblich`; `Unbekannt`; `organisation` |
| gender-guesser | `gender_guesser_v1` | `mostly_*`; `andy`; `conflict` |
| Wiki-Gendersort | `wiki_gendersort_v1` | `M`/`F`; `UNI`/`unisex`; `UNK`; `conflict`; native `INI` becomes `no_name` and abstains |
| HIVOTO | `hivoto_v1` | `mostly_*`; `andy`; `conflict` |
| nomquamgender | `nomquamgender_v1` | `uncertain`; `conflict` |
| HF DistilBERT | `hf_distilbert_v1` | label/index 0 is male and 1 is female; `conflict` |
| HF genderize | `hf_genderize_v1` | label/index 0 is female and 1 is male; `conflict` |
| local LLM | `local_llm_v1` | `organisation` maps to `institution` |
| HIVOTO-XGBoost | `hivoto_xgboost_v1` | `mostly_*`; `andy`; `conflict` |

Every normalized prediction records the normalization version and outcome reason in metadata. This preserves
the canonical distinction among a substantive `unknown`, abstention, and technical failure. See
[ADR-0007](decisions/ADR-0007-versioned-normalization-outcomes.md).

## Reference aggregation

The aggregation is three-step:

1. normalization
2. voting with authority overrides
3. certainty assignment

### Included methods

Two signals are authority overrides (`REFERENCE_AUTHORITY_METHODS`):

1. parenthetical-qualifier rule (`parenthetical_qualifier`)
2. GND lookup (`gnd`)

The remaining seven published methods enter an unweighted vote (`REFERENCE_POOLED_METHODS`):

- gender-guesser
- Wiki-Gendersort
- HIVOTO
- nomquamgender
- HF DistilBERT
- HF BERT-genderize
- local LLM

The experimental HIVOTO-XGBoost does not enter the reference vote (`REFERENCE_IGNORED_METHODS`).

`reference_v1` requires a result envelope for both override methods and all seven pooled methods. Persisted
`abstain` and `error` results satisfy that completeness requirement but cast no vote. A missing required method
fails aggregation rather than silently changing the ensemble. HIVOTO-XGBoost may be present as provenance but
is ignored.

### Persisted completeness boundary

The asynchronous executor applies that requirement to persisted evidence before it calls the pure aggregator.
For every PersonRecord in the run's immutable snapshot, the selected MethodExecutions must provide exactly one
Prediction from each of the nine required reference methods. The selected executions and predictions must
belong to the same run, snapshot, person, and method identities recorded by the AggregationExecution.

Presence and scientific outcome are separate:

- `success` is present and may contribute a label;
- `abstain` is present and contributes no vote;
- `error` is present and contributes no vote;
- no Prediction row is missing evidence and fails the AggregationExecution.

The executor does not convert absence into a synthetic `abstain` or `error` Prediction. Doing so would invent a
method output, obscure failed batch coverage, and violate Prediction immutability. A valid complete input set
may still produce `outcome=no_data`; that is a completed scientific result, not an execution failure.

For the current corpus scale, the executor persists exactly one AggregatedResult per snapshot person and marks
the AggregationExecution completed in the same transaction. A permanent completeness or contract failure
leaves no result rows and marks the execution failed. See
[ADR-0016](decisions/ADR-0016-asynchronous-aggregation-outbox.md).

### Priority chain

For each record:

1. If the parenthetical-qualifier rule returns `success`, its label becomes the combined label, including
   canonical `unknown`.
2. Else, if GND returns a successful non-`unknown` label, that becomes the combined label.
3. Else, use the plain unweighted majority of successful labels among the seven pooled methods.

Tie rule:

- if `unknown` ties with one of `male`, `female`, or `institution`, the substantive label wins;
- if multiple substantive labels remain tied, return `outcome=unresolved_tie`, `label=null`, deterministic
  canonical-order `tied_labels`, and the complete vote counts;
- if no pooled method casts a vote, return `outcome=no_data` and `label=null`.

No decision may depend on prediction insertion or iteration order. See
[ADR-0008](decisions/ADR-0008-reference-aggregation-edge-contract.md).

### Agreement score and tiers

For a decided majority-vote result:

```text
votes for winning label / number of pooled methods that cast a vote
```

Scores are rounded to three decimal places. The associated tiers are:

- `unanimous`: score = 1.0;
- `strong_majority`: score >= 0.75;
- `weak_majority`: score >= 0.50;
- `no_consensus`: score < 0.50;
- `single_rater`: exactly one useful result;
- `no_answer`: no useful result.

An unresolved substantive tie retains the maximum vote share as its score but is always `no_consensus`.
An authority override records the share of comparison methods agreeing with it. With no comparator, its score
is 1.0 and its tier is `single_rater`, not `unanimous`. A no-data result has a null score and `no_answer`.

Pairwise Cohen's kappa is an evaluation metric, implemented in
[`gendertagger.evaluation.kappa`](../backend/src/gendertagger/evaluation/kappa.py) over records where both
methods provide successful answers; it is not part of the per-record aggregation result.

## Pipeline certainty tiers

Reference tiers:

- `high`: at least two pooled methods voted and agreement is >= 0.75, or any authority override;
- `low`: at least two pooled methods voted and agreement is >= 0.50;
- `contested`: at least two pooled methods voted and agreement is < 0.50, or the vote is unresolved;
- `single`: the local LLM is the only voter and reports typed self-certainty `high`;
- `uncertain`: a lone local LLM reports `low`/`uncertain`, or any other pooled method is the lone voter;
- `no_data`: no usable vote.

A lone local-LLM result without valid self-reported certainty fails assessment rather than guessing. A lone
authority has `single_rater` agreement but `high` certainty. Certainty tier is distinct from
`method_confidence`, which never changes the reference vote, agreement, or certainty. See
[ADR-0009](decisions/ADR-0009-reference-agreement-certainty.md).

## Human review

Disagreement/uncertainty is a primary triage signal. Human review does not rewrite Predictions or AggregatedResults. It creates an Annotation that participates in the derived final decision.

## Versioning

Aggregation behavior carries a stable strategy identifier and version: `AggregationConfig.strategy`
defaults to `reference_v1`, and the resolved strategy is part of the aggregation configuration hash.
Any change to:

- included methods
- override priority
- normalization
- voting
- tie handling
- thresholds
- certainty mapping

creates a new strategy version and is documented in an ADR.
