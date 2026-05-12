"""
Inter-Annotator Agreement for Gender Classification Methods
===========================================================
Computes:
  - Pairwise Cohen's Kappa (sklearn) for all method pairs
  - Fleiss' Kappa (statsmodels) across all methods
  - Krippendorff's Alpha (krippendorff) across all methods

Only rows where a method returned a substantive label (male / female /
any ambiguous label) are included. Rows with no_name or NaN are treated as
"did not answer" and excluded from the relevant pair/set.

For Fleiss' Kappa and Krippendorff's Alpha only the intersection is used
(rows where every included method gave an answer).

Run from the project root:
    .venv/bin/python scripts/agreements.py
"""

import itertools
from datetime import datetime
from pathlib import Path

import krippendorff
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score
from statsmodels.stats.inter_rater import aggregate_raters, fleiss_kappa

RESULTS = Path("data/results")
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

# ── 0. Load & merge ───────────────────────────────────────────────────────────
files = {
    "gg_gender": "gender_guesser_results.csv",
    "hfgc_gender": "hf_gender_classification_results.csv",
    "hfg_gender": "hf_genderize_results.csv",
    "hv_gender": "hivoto_results.csv",
    "xgb_gender": "hivoto_xgboost_results.csv",
    "nqg_gender": "nqg_results.csv",
    "wgs_gender": "wiki_gendersort_results.csv",
    "llm_gender": "llm_gender_results.csv",
}

base = None
for col, fname in files.items():
    df = pd.read_csv(RESULTS / fname, dtype=str, usecols=["xml_id", col])
    base = df if base is None else base.merge(df, on="xml_id", how="outer")

METHODS = {
    "gg_gender": "gender_guesser",
    "hfgc_gender": "HF ClassifyGender",
    "hfg_gender": "HF Genderize",
    "hv_gender": "HIVOTO",
    "xgb_gender": "HIVOTO-XGBoost",
    "nqg_gender": "NQG",
    "wgs_gender": "Wiki-Gendersort",
    "llm_gender": "LLM",
}

# ── 1. Normalise labels ───────────────────────────────────────────────────────
# Map everything to a small set of canonical labels:
#   male → "male"
#   female → "female"
#   anything else that is not no_name / NaN → "ambiguous"
#   no_name / NaN → None  (excluded from agreement)

FAILED = {"no_name", "nan", ""}


def normalise(val):
    if pd.isna(val):
        return None
    v = str(val).strip().lower()
    if v in FAILED:
        return None
    if v == "male":
        return "male"
    if v == "female":
        return "female"
    return "ambiguous"


for col in METHODS:
    base[col + "_norm"] = base[col].apply(normalise)

norm_cols = [col + "_norm" for col in METHODS]
method_names = list(METHODS.values())

# ── 2. Encode labels for numeric computation ──────────────────────────────────
LABEL_MAP = {"male": 0, "female": 1, "ambiguous": 2}

for col in norm_cols:
    base[col + "_enc"] = base[col].map(LABEL_MAP)  # NaN stays NaN

enc_cols = [col + "_enc" for col in norm_cols]


# ── 3. Pairwise Cohen's Kappa ─────────────────────────────────────────────────
def interpret_kappa(k):
    if k < 0:
        return "Poor (< 0)"
    if k < 0.20:
        return "Slight"
    if k < 0.40:
        return "Fair"
    if k < 0.60:
        return "Moderate"
    if k < 0.80:
        return "Substantial"
    return "Almost perfect"


kappa_rows = []
for (c1, n1), (c2, n2) in itertools.combinations(zip(enc_cols, method_names), 2):
    sub = base[[c1, c2]].dropna()
    if len(sub) < 10:
        kappa_rows.append(
            {
                "Classifier 1": n1,
                "Classifier 2": n2,
                "N": len(sub),
                "Cohen's Kappa": None,
                "Interpretation": "too few rows",
            }
        )
        continue
    k = cohen_kappa_score(sub[c1].astype(int), sub[c2].astype(int))
    kappa_rows.append(
        {
            "Classifier 1": n1,
            "Classifier 2": n2,
            "N": len(sub),
            "Cohen's Kappa": round(k, 3),
            "Interpretation": interpret_kappa(k),
        }
    )

kappa_df = pd.DataFrame(kappa_rows).sort_values("Cohen's Kappa", ascending=False)

print("=" * 65)
print("PAIRWISE COHEN'S KAPPA")
print("=" * 65)
print(kappa_df.to_string(index=False))

# ── 4. Fleiss' Kappa ──────────────────────────────────────────────────────────
# Uses only rows where ALL methods gave an answer
full_mask = base[enc_cols].notna().all(axis=1)
full_df = base.loc[full_mask, enc_cols].astype(int)
n_full = len(full_df)

# aggregate_raters expects (n_subjects × n_raters) → counts per category
data_matrix = full_df.values  # shape (n, 5)
agg, _ = aggregate_raters(data_matrix, n_cat=3)  # 3 categories: 0,1,2
fk = fleiss_kappa(agg)

print(f"\n{'=' * 65}")
print("FLEISS' KAPPA  (rows where all methods answered: N={:,})".format(n_full))
print("=" * 65)
print(f"  Fleiss' Kappa = {fk:.3f}   [{interpret_kappa(fk)}]")

# ── 5. Krippendorff's Alpha ───────────────────────────────────────────────────
# krippendorff expects a (n_raters × n_items) array; NaN = missing
ka_data = base[enc_cols].T.values.astype(float)  # (5, 8273)
ka = krippendorff.alpha(reliability_data=ka_data, level_of_measurement="nominal")

print(f"\n{'=' * 65}")
print(
    "KRIPPENDORFF'S ALPHA  (handles missing data, N={:,} items)".format(base.shape[0])
)
print("=" * 65)
print(f"  Krippendorff's Alpha = {ka:.3f}")
if ka >= 0.800:
    ka_interp = "Acceptable for most purposes (≥ 0.800)"
elif ka >= 0.667:
    ka_interp = "Tentative conclusions only (0.667–0.800)"
else:
    ka_interp = "Unreliable (< 0.667)"
print(f"  Interpretation: {ka_interp}")

# ── 6. Summary ────────────────────────────────────────────────────────────────
summary_rows = [
    {
        "Metric": "Cohen's Kappa (average)",
        "Value": round(kappa_df["Cohen's Kappa"].dropna().mean(), 3),
        "Interpretation": interpret_kappa(kappa_df["Cohen's Kappa"].dropna().mean()),
    },
    {
        "Metric": "Fleiss' Kappa",
        "Value": round(fk, 3),
        "Interpretation": interpret_kappa(fk),
    },
    {
        "Metric": "Krippendorff's Alpha",
        "Value": round(ka, 3),
        "Interpretation": ka_interp,
    },
]
summary_df = pd.DataFrame(summary_rows)

print(f"\n{'=' * 65}")
print("SUMMARY")
print("=" * 65)
print(summary_df.to_string(index=False))

# ── 7. Save ───────────────────────────────────────────────────────────────────
ts = datetime.now().strftime("%Y%m%d_%H%M%S")

kappa_out = OUTPUT / f"cohens_kappa_results_{ts}.csv"
summary_out = OUTPUT / f"agreement_metrics_summary_{ts}.csv"

kappa_df.to_csv(kappa_out, index=False)
summary_df.to_csv(summary_out, index=False)

print(f"\nSaved → {kappa_out}")
print(f"Saved → {summary_out}")
print("\nDone.")
