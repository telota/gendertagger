"""
Per-Record Agreement Analysis for Gender Classification Methods
================================================================
For each record, computes:
  - Fleiss' per-item agreement  P_i = 1/(k(k-1)) * Σ_j n_ij(n_ij - 1)
  - Shannon entropy             H_i = -Σ p_j log₂(p_j)
  - Majority label + vote count
  - Agreement tier (unanimous / strong majority / weak / split / no consensus)

Then aggregates:
  - Distribution of agreement tiers
  - Mean / median / std of P_i and H_i
  - Records with highest disagreement

Run from the project root:
    .venv/bin/python scripts/record_agreement.py
"""

from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

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

base = None
for col, fname in files.items():
    df = pd.read_csv(RESULTS / fname, dtype=str, usecols=["xml_id", col])
    base = df if base is None else base.merge(df, on="xml_id", how="outer")

# Also load forename for readable output
names = pd.read_csv(
    RESULTS / "gender_guesser_results.csv", dtype=str, usecols=["xml_id", "forename"]
)
base = base.merge(names, on="xml_id", how="left")

K = len(METHODS)  # number of raters

# ── 1. Normalise labels (same scheme as agreements.py) ─────────────────────────
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


norm_cols = []
for col in METHODS:
    nc = col + "_norm"
    base[nc] = base[col].apply(normalise)
    norm_cols.append(nc)

# ── 2. Per-record metrics ─────────────────────────────────────────────────────
CATEGORIES = ["male", "female", "ambiguous"]


def record_metrics(row):
    """Compute agreement metrics for one record."""
    votes = [row[c] for c in norm_cols if row[c] is not None]
    k = len(votes)

    if k == 0:
        return pd.Series(
            {
                "n_answered": 0,
                "majority_label": None,
                "majority_count": 0,
                "fleiss_P_i": np.nan,
                "entropy": np.nan,
                "tier": "no_answer",
            }
        )

    counts = Counter(votes)

    # Majority
    majority_label, majority_count = counts.most_common(1)[0]
    # Check for ties
    top_counts = [c for _, c in counts.most_common()]
    has_tie = len(top_counts) > 1 and top_counts[0] == top_counts[1]

    # Fleiss per-item agreement: P_i = 1/(k(k-1)) * Σ_j n_ij(n_ij - 1)
    if k >= 2:
        sum_nij_sq = sum(n * (n - 1) for n in counts.values())
        fleiss_pi = sum_nij_sq / (k * (k - 1))
    else:
        fleiss_pi = 1.0  # single rater: trivially perfect

    # Shannon entropy: H = -Σ p_j log₂(p_j)
    entropy = 0.0
    for n in counts.values():
        p = n / k
        if p > 0:
            entropy -= p * np.log2(p)

    # Agreement tier
    if k == 1:
        tier = "single_rater"
    elif majority_count == k:
        tier = "unanimous"
    elif has_tie:
        tier = "no_consensus"
    elif majority_count >= k - 1:  # e.g. 4/5
        tier = "strong_majority"
    elif majority_count > k / 2:  # e.g. 3/5
        tier = "weak_majority"
    else:
        tier = "no_consensus"

    return pd.Series(
        {
            "n_answered": k,
            "majority_label": majority_label,
            "majority_count": majority_count,
            "fleiss_P_i": round(fleiss_pi, 4),
            "entropy": round(entropy, 4),
            "tier": tier,
        }
    )


print("Computing per-record metrics...")
metrics = base.apply(record_metrics, axis=1)
base = pd.concat([base, metrics], axis=1)

# ── 3. Agreement tier distribution ────────────────────────────────────────────
tier_order = [
    "unanimous",
    "strong_majority",
    "weak_majority",
    "no_consensus",
    "single_rater",
    "no_answer",
]
tier_counts = base["tier"].value_counts().reindex(tier_order).fillna(0).astype(int)

print("\n" + "=" * 65)
print("AGREEMENT TIER DISTRIBUTION")
print("=" * 65)
total = len(base)
for tier, n in tier_counts.items():
    pct = n / total * 100
    bar = "█" * int(pct / 2)
    print(f"  {tier:20s} : {n:>6,}  ({pct:5.1f}%)  {bar}")

# ── 4. Fleiss P_i statistics ──────────────────────────────────────────────────
valid_pi = base["fleiss_P_i"].dropna()

print(f"\n{'=' * 65}")
print(
    f"FLEISS' PER-ITEM AGREEMENT  P_i  (N = {len(valid_pi):,} records with ≥1 answer)"
)
print("=" * 65)
print(f"  Mean   = {valid_pi.mean():.4f}")
print(f"  Median = {valid_pi.median():.4f}")
print(f"  Std    = {valid_pi.std():.4f}")
print(f"  Min    = {valid_pi.min():.4f}")
print(f"  Max    = {valid_pi.max():.4f}")

# P_i value distribution
pi_bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0001]
pi_labels = ["0.0–0.2", "0.2–0.4", "0.4–0.6", "0.6–0.8", "0.8–1.0"]
base["pi_bin"] = pd.cut(
    base["fleiss_P_i"], bins=pi_bins, labels=pi_labels, right=False, include_lowest=True
)
print("\n  Distribution of P_i:")
for lbl in pi_labels:
    n = (base["pi_bin"] == lbl).sum()
    pct = n / len(valid_pi) * 100
    print(f"    {lbl} : {n:>6,}  ({pct:5.1f}%)")

# ── 5. Shannon entropy statistics ─────────────────────────────────────────────
valid_h = base["entropy"].dropna()
h_max = np.log2(K)

print(f"\n{'=' * 65}")
print(f"SHANNON ENTROPY  H_i  (0 = consensus, max = {h_max:.3f} for {K} categories)")
print("=" * 65)
print(f"  Mean   = {valid_h.mean():.4f}")
print(f"  Median = {valid_h.median():.4f}")
print(f"  Std    = {valid_h.std():.4f}")
print(f"  Min    = {valid_h.min():.4f}")
print(f"  Max    = {valid_h.max():.4f}")

# ── 6. Majority vote breakdown ───────────────────────────────────────────────
answered = base[base["n_answered"] >= 2].copy()

print(f"\n{'=' * 65}")
print(f"MAJORITY VOTE BREAKDOWN  (records with ≥ 2 answers: {len(answered):,})")
print("=" * 65)
for count in sorted(answered["majority_count"].unique(), reverse=True):
    sub = answered[answered["majority_count"] == count]
    labels = sub["majority_label"].value_counts()
    detail = ", ".join(f"{l}: {n:,}" for l, n in labels.items())
    print(f"  {count}/{K} agree : {len(sub):>6,} records  ({detail})")

# ── 7. Most disagreed records ────────────────────────────────────────────────
print(f"\n{'=' * 65}")
print("TOP 20 MOST DISAGREED RECORDS  (highest entropy, ≥ 3 answers)")
print("=" * 65)

disagree = base[base["n_answered"] >= 3].nlargest(20, "entropy")[
    [
        "xml_id",
        "forename",
        "n_answered",
        "majority_label",
        "majority_count",
        "fleiss_P_i",
        "entropy",
        "tier",
    ]
    + [c for c in norm_cols]
]
print(disagree.to_string(index=False))

# ── 8. Per-label agreement ────────────────────────────────────────────────────
print(f"\n{'=' * 65}")
print("AGREEMENT BY MAJORITY LABEL")
print("=" * 65)
for lbl in ["male", "female", "ambiguous"]:
    sub = answered[answered["majority_label"] == lbl]
    if len(sub) == 0:
        continue
    pi_mean = sub["fleiss_P_i"].mean()
    h_mean = sub["entropy"].mean()
    unan = (sub["tier"] == "unanimous").sum()
    print(
        f"  {lbl:12s}: N={len(sub):>5,}  "
        f"mean P_i={pi_mean:.3f}  mean H={h_mean:.3f}  "
        f"unanimous={unan:,} ({unan/len(sub)*100:.1f}%)"
    )

# ── 9. Plots ──────────────────────────────────────────────────────────────────

# 9a. Histogram of P_i
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

ax = axes[0]
ax.hist(valid_pi, bins=50, color="#4472C4", edgecolor="white", alpha=0.85)
ax.set_xlabel("Fleiss' per-item agreement  $P_i$")
ax.set_ylabel("Number of records")
ax.set_title("Distribution of per-record agreement ($P_i$)")
ax.axvline(
    valid_pi.mean(), color="red", linestyle="--", label=f"mean = {valid_pi.mean():.3f}"
)
ax.legend()

# 9b. Histogram of Entropy
ax = axes[1]
ax.hist(valid_h, bins=50, color="#ED7D31", edgecolor="white", alpha=0.85)
ax.set_xlabel("Shannon entropy  $H_i$  (bits)")
ax.set_ylabel("Number of records")
ax.set_title("Distribution of per-record entropy ($H_i$)")
ax.axvline(
    valid_h.mean(), color="red", linestyle="--", label=f"mean = {valid_h.mean():.3f}"
)
ax.legend()

plt.tight_layout()
out1 = OUTPUT / "record_agreement_distributions.png"
plt.savefig(out1, dpi=150)
print(f"\nPlot saved → {out1}")
plt.close()

# 9c. Agreement tier pie chart
fig, ax = plt.subplots(figsize=(7, 7))
plot_tiers = tier_counts[tier_counts > 0]
colors = ["#2E7D32", "#66BB6A", "#FFC107", "#E53935", "#9E9E9E", "#E0E0E0"]
ax.pie(
    plot_tiers.values,
    labels=plot_tiers.index,
    autopct="%1.1f%%",
    colors=colors[: len(plot_tiers)],
    startangle=90,
    textprops={"fontsize": 10},
)
ax.set_title("Agreement tier distribution across all records")
out2 = OUTPUT / "record_agreement_tiers.png"
plt.savefig(out2, dpi=150)
print(f"Plot saved → {out2}")
plt.close()

# ── 10. Save full per-record results ─────────────────────────────────────────
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_csv = OUTPUT / f"record_agreement_{ts}.csv"
save_cols = [
    "xml_id",
    "forename",
    "n_answered",
    "majority_label",
    "majority_count",
    "fleiss_P_i",
    "entropy",
    "tier",
] + norm_cols
base[save_cols].to_csv(out_csv, index=False)
print(f"\nFull per-record results → {out_csv}")
print("Done.")
