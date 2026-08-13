# Methods, normalization, aggregation, and certainty

This document is **normative for the reference pipeline**. The infrastructure may support additional strategies later, but the first implementation must reproduce this behavior before extending it.

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

The flattened TEI person representation includes where available:

- `xml:id`
- surname
- forename(s)
- birth/death information
- free-text biographical note
- alternative names
- GND identifier

Name-only methods use the minimum fields they require. The local LLM may receive the full register entry/context according to method configuration.

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
| parenthetical qualifier | `parenthetical_qualifier_v1` | canonical male/female/unknown values |
| GND | `gnd_v1` | `Männlich`/`Weiblich`; `Unbekannt`; `organisation` |
| gender-guesser | `gender_guesser_v1` | `mostly_*`; `andy`; `conflict` |
| Wiki-Gendersort | `wiki_gendersort_v1` | `M`/`F`; `UNI`/`unisex`; `UNK`; `INI` abstains |
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

Two signals are authority overrides:

1. parenthetical-qualifier rule
2. GND lookup

The remaining seven published methods enter an unweighted vote:

- gender-guesser
- Wiki-Gendersort
- HIVOTO
- nomquamgender
- HF DistilBERT
- HF BERT-genderize
- local LLM

The experimental HIVOTO-XGBoost does not enter the reference vote.

`reference_v1` requires a result envelope for both override methods and all seven pooled methods. Persisted
`abstain` and `error` results satisfy that completeness requirement but cast no vote. A missing required method
fails aggregation rather than silently changing the ensemble. HIVOTO-XGBoost may be present as provenance but
is ignored.

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

### Agreement score

For majority-vote results:

```text
votes for winning label / number of methods that cast a vote
```

For authority-override results, record the share of remaining methods agreeing with the override, in addition to the fact that the label came from an override.

## Agreement tiers

Per-record agreement:

- `unanimous`
- `strong_majority` >= 0.75
- `weak_majority` >= 0.50
- `no_consensus` < 0.50
- `single_rater`
- `no_answer`

Pairwise method agreement is evaluated with Cohen's kappa on records where both methods provide substantive non-abstention answers.

## Pipeline certainty tiers

Reference tiers:

- `high`: at least two methods voted and >= 0.75 agreement, or authority override according to reference policy
- `low`: at least two voted and >= 0.50 agreement
- `contested`: at least two voted and < 0.50 agreement
- `single`: only one useful method result and that method is the LLM with self-reported high confidence
- `uncertain`: lone LLM result with low/uncertain self-confidence
- `no_data`: no usable vote

Certainty tier is distinct from `method_confidence`.

## Human review

Disagreement/uncertainty is a primary triage signal. Human review does not rewrite Predictions or AggregatedResults. It creates an Annotation that participates in the derived final decision.

## Versioning

Aggregation behavior must have a stable strategy identifier and version. Any change to:

- included methods
- override priority
- normalization
- voting
- tie handling
- thresholds
- certainty mapping

creates a new strategy version and should be documented in an ADR.
