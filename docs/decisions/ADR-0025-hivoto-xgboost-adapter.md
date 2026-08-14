# ADR-0025: HIVOTO-XGBoost experimental adapter

**Status:** Accepted

## Context

HIVOTO-XGBoost is the tenth documented component and the only one explicitly held out of the reference
vote (see [`07-methods-and-aggregation.md`](../07-methods-and-aggregation.md), and
[ADR-0003](ADR-0003-reference-aggregation.md)/[ADR-0008](ADR-0008-reference-aggregation-edge-contract.md)
for its exclusion from `reference_v1`). Its legacy reference implementation
(`__scrap/src/gendertagger/backend/classification/methods/hivoto_xgboost.py`) is a two-stage classifier, not
a plain name-string model: for each usable forename token, it first checks the *same* majority-voted lookup
HIVOTO itself compiles from the licensed HIVOTO source (male/female/`mostly_male`/`mostly_female`/`andy`/
`unknown`), and only falls back to a trained TF-IDF(char\_wb, n=2–5) + XGBClassifier model for tokens absent
from that lookup. Consensus across a person's tokens is bespoke, not the shared `consensus_label`: any
non-`andy`/`unknown` label (lookup hit or model prediction) counts as a "hard" vote, and majority-vote among
hard votes wins, normalizing `mostly_*` down to plain male/female; only when every token is `andy` does the
result become `andy`; otherwise the mean predicted P(female) across all tokens (lookup hits contribute a
fixed placeholder probability) is thresholded at 0.5. Verified empirically against the full 8,273-row
reference output (`data/output/results/hivoto_xgboost_results.csv`): only `{male, female, andy, no_name}`
ever actually occur, consistent with this reduction never producing `conflict`, `unknown`, or a bare
`mostly_*` result.

The trained model (`hivoto_xgb_vectorizer.joblib`, `hivoto_xgb_model.joblib`) already exists; no retraining
is required or performed by this record. Both were originally pickled (`joblib`/`pickle`), the same
arbitrary-code-execution-on-load risk flagged for the transformer classifiers under
[ADR-0024](ADR-0024-hf-transformer-model-manifest-adapters.md). Both fitted objects were converted once,
locally, to pickle-free formats and verified byte-exact: the `XGBClassifier` via its own native
`save_model` (JSON, not pickle); the `TfidfVectorizer` by extracting its two pieces of learned state
(`vocabulary_`, `idf_`) to plain JSON, reconstructable by building a fresh vectorizer from its known,
unchanged constructor configuration and assigning those two attributes directly, never calling `.fit()`.
Round-trip verification (500 sampled in-vocabulary tokens plus 5 edge cases) found zero numeric difference
between the original pickled objects and the reconstruction from the four converted files. The original
`.joblib` files are preserved, untracked, under `__scrap/`; the converted files are committed at
`data/models/hivoto_xgboost/` (documented in that directory's `PROVENANCE.md`), since — unlike every other
method's external, separately-licensed source data — this model was trained by this project and is small
enough to version directly.

## Decision

Bundle everything `HivotoXgboostMethod.predict_batch` needs into one content-addressed model manifest, using
the same `ModelManifestMetadata`/`ModelDirectoryResolver` mechanism ADR-0024 established, unchanged: five
members — a copy of the already-compiled `hivoto_lookup` SQLite bytes (`hivoto_lookup.sqlite3`), plus
`vocabulary.json`, `idf.json`, `vectorizer_config.json`, and `model.json`. The lookup member is *reused*,
not recompiled: `assets prepare-hivoto-xgboost` takes the already-registered `hivoto_lookup` artifact's
digest and materializes those exact bytes into the new manifest, rather than re-parsing the licensed HIVOTO
source CSV a second time. This keeps the two adapters' lookup-based labels for a given token structurally
guaranteed identical (same bytes, not independently recompiled from the same source) and keeps the
license-gated raw CSV behind exactly one compilation path, matching ADR-0023's acquisition boundary.

The lookup member is read with the *unmodified* `SqliteHivotoLookup` from `gendertagger.methods.hivoto` — it
is byte-identical to what that adapter already reads, so no new lookup reader is introduced. Lookup-query
key normalization matches `HivotoMethod`'s own (`token.lower().rstrip(".,;:)\"'")`) for consistency between
the two adapters querying the same artifact. The reconstructed model's input key normalization instead
matches the original training preprocessing exactly (`token.lower().rstrip(".")`), since fidelity to the
model's trained input distribution takes priority there over consistency with the unrelated lookup-query
convention; the vectorizer's own `lowercase=True` configuration makes explicit case-folding redundant but
harmless. `HivotoXgboostConfig` is an ordinary `LookupMethodConfig`, and registration in
`method_registry.py` needs no new resolver plumbing — the `ModelDirectoryResolver` wired into
`default_method_registry` for the transformer classifiers is generic across logical types and is reused
as-is for this method's manifest.

`REFERENCE_IGNORED_METHODS` already contains `"hivoto_xgboost"` (added when the domain aggregation layer was
last touched); no domain-layer change accompanies this adapter.

## Consequences

- HIVOTO-XGBoost's provisioned lookup labels can never silently diverge from HIVOTO's own, because both
  adapters resolve the identical compiled artifact rather than two independently built tables.
- `scikit-learn` and `xgboost` become a new opt-in `hivoto-xgboost` extra, lazily imported, raising
  `MethodDependencyError` when absent — the same shape as every other optional method dependency.
- The model files are the one method-data dependency in this project that lives in git rather than behind
  external/licensed acquisition; `data/models/hivoto_xgboost/PROVENANCE.md` records why and how they were
  produced so that provenance survives independently of this ADR.
- Two different token-key normalizations exist inside one adapter (lookup query vs. model input) rather than
  one shared normalization function; this is a deliberate fidelity choice, not an oversight, and is
  documented at the point of use.
