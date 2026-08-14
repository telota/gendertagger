# HIVOTO-XGBoost model artifacts

Pickle-free re-export of the already-trained experimental HIVOTO-XGBoost classifier described in
[`docs/paper/article.tex`](../../../docs/paper/article.tex) (character-$n$-gram TF-IDF + XGBClassifier,
trained on the HIVOTO database) and implemented in the legacy reference script
[`__scrap/src/gendertagger/backend/classification/methods/hivoto_xgboost.py`](../../../__scrap/src/gendertagger/backend/classification/methods/hivoto_xgboost.py).

## Provenance

- Source: `hivoto_xgb_vectorizer.joblib` / `hivoto_xgb_model.joblib`, the current (not `_old`) trained pair,
  originally produced by the legacy training script and preserved untracked at
  `__scrap/data/output/models/`.
- No retraining occurred. This is a lossless, local, one-time format conversion of the already-fitted
  `sklearn.feature_extraction.text.TfidfVectorizer` and `xgboost.XGBClassifier` objects, run once in a
  throwaway virtual environment (`scikit-learn==1.9.0`, `xgboost==3.2.0`, `joblib==1.5.3`, `numpy==2.4.6`)
  outside the project's runtime dependencies.
- The source `.joblib` files were originally pickled under `scikit-learn==1.8.0` (per the
  `InconsistentVersionWarning` raised on load); unpickling succeeded without error, and every value
  extracted below round-trips exactly (see Verification).

## Files

- `vocabulary.json` — the vectorizer's `vocabulary_` mapping (token → feature index), 25,000 entries.
- `idf.json` — the vectorizer's `idf_` weights, a plain JSON array ordered by feature index (aligned with
  `vocabulary.json`'s index values, not alphabetically).
- `vectorizer_config.json` — the fixed constructor parameters (`analyzer="char_wb"`, `ngram_range=(2, 5)`,
  `min_df=3`, `sublinear_tf=true`, `max_features=25000`, `dtype=float32`, ...) needed to reconstruct an
  equivalent `TfidfVectorizer` without ever calling `.fit()` — the vectorizer is rebuilt by constructing it
  with this config and then directly assigning `vocabulary_`/`idf_`.
- `model.json` — the XGBoost classifier's own native JSON export (`XGBClassifier.save_model`), not pickle.

None of `vocabulary_`/`idf_`/the XGBoost model requires `pickle.load` to reconstruct or use; only this
one-time conversion step (already performed) touched the original pickled `.joblib` bytes.

## Verification

Reconstructing a vectorizer and model purely from these four files and comparing against the original
`joblib`-loaded objects, over 500 randomly sampled in-vocabulary tokens plus 5 out-of-vocabulary/edge-case
strings:

- `TfidfVectorizer.transform` output: **max abs diff 0.0**
- `XGBClassifier.predict_proba` output: **max abs diff 0.0**

Exact match. The conversion script is not part of the shipped package (it was a one-time local step); its
logic is preserved here for reference and reproducibility, and the same verification approach should be
re-run if these files are ever regenerated from a newly trained model.
