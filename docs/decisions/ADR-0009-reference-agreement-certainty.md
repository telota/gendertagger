# ADR-0009: Derive reference agreement and certainty from explicit evidence

**Status:** Accepted

## Context

The published reference behavior defines agreement thresholds and authority promotion, but edge cases need an
unambiguous service contract. In particular, an authority may fire without a comparator, unresolved ties now
have no winning label, and the legacy helper initially marked every lone pooled voter as `single` before only
refining lone-LLM rows. Method confidence cannot safely resolve these cases because confidence scales are not
globally calibrated.

## Decision

Reference agreement and certainty are pure derivations from the immutable aggregation decision and prediction
evidence. Agreement shares are rounded to three decimal places, matching the reference output.

For a decided pooled vote, agreement is the winning-label count divided by all pooled votes. The tiers are
`unanimous` at 1.0, `strong_majority` at or above 0.75, `weak_majority` at or above 0.50, and `no_consensus`
below 0.50. Two or more pooled votes map to certainty `high`, `low`, or `contested` at the same thresholds.

An unresolved substantive tie retains the maximum vote share as `agreement_score` but is always
`agreement_tier=no_consensus` and `certainty_tier=contested`, because no label won. No usable vote has a null
score, `agreement_tier=no_answer`, and `certainty_tier=no_data`.

An authority override uses the recorded share of comparison methods agreeing with the override. With no
comparison method, it receives score 1.0 and `agreement_tier=single_rater`, not `unanimous`. Every authority
override receives reference certainty `high`, regardless of comparator disagreement; the score and tier retain
that disagreement for review.

A lone pooled voter has score 1.0 and `agreement_tier=single_rater`. It receives certainty `single` only when
the voter is the local LLM and its typed `self_reported_certainty` is `high`. A lone local LLM reporting `low`
or `uncertain`, and every lone non-authority method, receives certainty `uncertain`. A lone LLM prediction with
missing or invalid self-reported certainty fails assessment rather than guessing. `method_confidence` never
changes agreement or certainty.

Pairwise Cohen's kappa remains an evaluation concern for Phase 7 and is not part of this aggregation result.

## Consequences

Stored vote and override counts are sufficient to reproduce per-record scores and tiers. An authority can be
high-certainty reference evidence while still exposing zero comparator agreement. The conservative lone-voter
rule avoids treating an arbitrary method-specific confidence as calibrated evidence. Existing corpus output is
preserved for observed lone-voter rows, which are local-LLM-only, while previously unspecified hypothetical
lone non-LLM rows become explicitly uncertain.
