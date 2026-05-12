"""
Gender Classification Benchmark
================================
Compares all classification methods against GND as ground truth.

Methods: gender_guesser, HF ClassifyGender, HF Genderize, HIVOTO, NQG, LLM
Ground truth: GND records where gnd_gender_mapped is 'male' or 'female'

Run from the project root:
    python scripts/benchmark.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from pathlib import Path

RESULTS = Path("data/results")
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

# ── 0. Load all result files ─────────────────────────────────────────────────
gnd = pd.read_csv(RESULTS / "gnd_gender_results.csv", dtype=str)
gg = pd.read_csv(RESULTS / "gender_guesser_results.csv", dtype=str)
hfgc = pd.read_csv(RESULTS / "hf_gender_classification_results.csv", dtype=str)
hfg = pd.read_csv(RESULTS / "hf_genderize_results.csv", dtype=str)
hv = pd.read_csv(RESULTS / "hivoto_results.csv", dtype=str)
xgb = pd.read_csv(RESULTS / "hivoto_xgboost_results.csv", dtype=str)
nqg = pd.read_csv(RESULTS / "nqg_results.csv", dtype=str)
wgs = pd.read_csv(RESULTS / "wiki_gendersort_results.csv", dtype=str)
llm = pd.read_csv(RESULTS / "llm_gender_results.csv", dtype=str)

print("=" * 55)
print("LOADED FILES")
print("=" * 55)
print(f"  GND    : {len(gnd):6,} rows")
print(f"  gg     : {len(gg):6,} rows")
print(f"  hfgc   : {len(hfgc):6,} rows")
print(f"  hfg    : {len(hfg):6,} rows")
print(f"  hv     : {len(hv):6,} rows")
print(f"  xgb    : {len(xgb):6,} rows")
print(f"  nqg    : {len(nqg):6,} rows")
print(f"  wgs    : {len(wgs):6,} rows")
print(f"  llm    : {len(llm):6,} rows")

# ── merge all into one wide DataFrame ───────────────────────────────────────
gnd_s = gnd[["xml_id", "gnd_gender_mapped"]]
base = gnd_s.copy()
for df, col in [
    (gg, ["xml_id", "gg_gender"]),
    (hfgc, ["xml_id", "hfgc_gender"]),
    (hfg, ["xml_id", "hfg_gender"]),
    (hv, ["xml_id", "hv_gender"]),
    (xgb, ["xml_id", "xgb_gender"]),
    (nqg, ["xml_id", "nqg_gender"]),
    (wgs, ["xml_id", "wgs_gender"]),
    (llm, ["xml_id", "llm_gender"]),
]:
    base = base.merge(df[col], on="xml_id", how="outer")

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

print(f"\nCombined DataFrame: {len(base):,} rows × {base.shape[1]} columns")
print(base.head(5).to_string())

# ── 1. Ground truth from GND ─────────────────────────────────────────────────
gt = gnd[gnd["gnd_gender_mapped"].isin(["male", "female"])].copy()

print("\n" + "=" * 55)
print("1. GROUND TRUTH (GND)")
print("=" * 55)
print(f"  Total GND records        : {len(gnd):>6,}")
print(f"    no GND match           : {(gnd['gnd_gender_mapped']=='no_gnd').sum():>6,}")
print(f"    GND gender = unknown   : {(gnd['gnd_gender_mapped']=='unknown').sum():>6,}")
print(f"    GND gender = male      : {(gnd['gnd_gender_mapped']=='male').sum():>6,}")
print(f"    GND gender = female    : {(gnd['gnd_gender_mapped']=='female').sum():>6,}")
print(f"  Ground truth subset size : {len(gt):>6,}  (male + female only)")

# ── 2. Coverage statistics ───────────────────────────────────────────────────
CLASSIFIED = {"male", "female"}
AMBIGUOUS = {
    "conflict",
    "unknown",
    "uncertain",
    "unisex",
    "andy",
    "mostly_male",
    "mostly_female",
}
FAILED = {"no_name"}


def categorise(val):
    if pd.isna(val) or val == "":
        return "failed"
    v = str(val).strip().lower()
    if v in CLASSIFIED:
        return "classified"
    if v in FAILED:
        return "failed"
    return "ambiguous"


cov_rows = []
for col, name in METHODS.items():
    series = base[col] if col in base.columns else pd.Series(dtype=str)
    total = len(series)
    cats = series.apply(categorise)
    n_cls = (cats == "classified").sum()
    n_amb = (cats == "ambiguous").sum()
    n_fail = (cats == "failed").sum()
    cov_rows.append(
        {
            "Method": name,
            "Total": total,
            "Classified": n_cls,
            "Ambiguous": n_amb,
            "Failed/no_name": n_fail,
            "Coverage %": round(n_cls / total * 100, 1),
        }
    )

coverage_df = pd.DataFrame(cov_rows).set_index("Method")

print("\n" + "=" * 55)
print("2. COVERAGE STATISTICS PER METHOD")
print("=" * 55)
print(coverage_df.to_string())

# ── 3. Classification distribution ──────────────────────────────────────────
LABEL_ORDER = [
    "male",
    "female",
    "conflict",
    "unknown",
    "uncertain",
    "unisex",
    "andy",
    "mostly_male",
    "mostly_female",
    "no_name",
    "NaN/missing",
]

dist_rows = []
for col, name in METHODS.items():
    series = base[col].copy() if col in base.columns else pd.Series(dtype=str)
    series = (
        series.fillna("NaN/missing").str.strip().str.lower().replace("", "NaN/missing")
    )
    counts = series.value_counts()
    total = len(series)
    row = {"Method": name}
    for lbl in LABEL_ORDER:
        row[lbl] = int(counts.get(lbl, 0))
        row[lbl + " %"] = round(counts.get(lbl, 0) / total * 100, 1)
    dist_rows.append(row)

dist_df = pd.DataFrame(dist_rows).set_index("Method")

print("\n" + "=" * 55)
print("3. CLASSIFICATION DISTRIBUTION (counts)")
print("=" * 55)
print(dist_df[LABEL_ORDER].to_string())

# ── 4. Precision evaluation on GND ground truth ──────────────────────────────
prec_rows = []
for col, name in METHODS.items():
    method_df = base[["xml_id", col]].copy()
    merged = gt[["xml_id", "gnd_gender_mapped"]].merge(
        method_df, on="xml_id", how="left"
    )

    total_gt = len(merged)
    pred = (
        merged[col]
        .fillna("NaN/missing")
        .str.strip()
        .str.lower()
        .replace("", "NaN/missing")
    )

    n_failed = pred.isin({"no_name", "nan/missing"}).sum()
    n_classified = pred.isin({"male", "female"}).sum()
    n_ambiguous = total_gt - n_failed - n_classified

    answered_mask = pred.isin({"male", "female"})
    n_match = (
        pred[answered_mask] == merged.loc[answered_mask, "gnd_gender_mapped"]
    ).sum()
    accuracy = round(n_match / n_classified * 100, 1) if n_classified > 0 else None

    male_gt = merged["gnd_gender_mapped"] == "male"
    female_gt = merged["gnd_gender_mapped"] == "female"
    n_match_m = ((pred == "male") & male_gt).sum()
    n_match_f = ((pred == "female") & female_gt).sum()

    prec_rows.append(
        {
            "Method": name,
            "GT records": total_gt,
            "Classified": n_classified,
            "Ambiguous": n_ambiguous,
            "Failed/no_name": n_failed,
            "Correct": int(n_match),
            "Accuracy %": accuracy,
            "Correct male": int(n_match_m),
            "Correct female": int(n_match_f),
        }
    )

prec_df = pd.DataFrame(prec_rows).set_index("Method")

print("\n" + "=" * 55)
print("4. PRECISION ON GND GROUND TRUTH")
print("=" * 55)
print(prec_df.to_string())

# per-class breakdown
print("\n  Per-class correct:")
for m in prec_df.index:
    print(
        f"    {m:<22}  male={prec_df.loc[m,'Correct male']:>5,}  female={prec_df.loc[m,'Correct female']:>5,}"
    )

# ── 5. Summary table ─────────────────────────────────────────────────────────
summary = coverage_df[
    ["Classified", "Ambiguous", "Failed/no_name", "Coverage %"]
].copy()
summary["GT records"] = prec_df["GT records"]
summary["Correct on GT"] = prec_df["Correct"]
summary["Accuracy on GT %"] = prec_df["Accuracy %"]

print("\n" + "=" * 55)
print("5. SUMMARY")
print("=" * 55)
print(summary.to_string())

# ── 6. Misclassification breakdown ──────────────────────────────────────────
mis_rows = []
for col, name in METHODS.items():
    merged = gt[["xml_id", "gnd_gender_mapped"]].merge(
        base[["xml_id", col]], on="xml_id", how="left"
    )
    pred = (
        merged[col]
        .fillna("NaN/missing")
        .str.strip()
        .str.lower()
        .replace("", "NaN/missing")
    )
    answered = pred.isin({"male", "female"})
    wrong = answered & (pred != merged["gnd_gender_mapped"])
    m_as_f = ((pred == "female") & (merged["gnd_gender_mapped"] == "male")).sum()
    f_as_m = ((pred == "male") & (merged["gnd_gender_mapped"] == "female")).sum()
    mis_rows.append(
        {
            "Method": name,
            "Answered": int(answered.sum()),
            "Wrong total": int(wrong.sum()),
            "Error %": (
                round(wrong.sum() / answered.sum() * 100, 1)
                if answered.sum() > 0
                else None
            ),
            "Male→Female": int(m_as_f),
            "Female→Male": int(f_as_m),
        }
    )

mis_df = pd.DataFrame(mis_rows).set_index("Method")

print("\n" + "=" * 55)
print("6. MISCLASSIFICATIONS ON GND GROUND TRUTH")
print("=" * 55)
print(mis_df.to_string())

# ── 7. Plots ─────────────────────────────────────────────────────────────────
methods = list(METHODS.values())

# Coverage + Accuracy side by side
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

ax = axes[0]
cov_vals = [coverage_df.loc[m, "Coverage %"] for m in methods]
bars = ax.barh(methods, cov_vals, color=sns.color_palette("Blues_d", len(methods)))
ax.set_xlabel("Coverage %")
ax.set_title("Coverage: % of records classified\n(male or female)")
ax.set_xlim(0, 105)
for bar, val in zip(bars, cov_vals):
    ax.text(
        val + 0.5,
        bar.get_y() + bar.get_height() / 2,
        f"{val:.1f}%",
        va="center",
        fontsize=9,
    )

ax = axes[1]
acc_vals = [
    prec_df.loc[m, "Accuracy %"] if prec_df.loc[m, "Accuracy %"] is not None else 0
    for m in methods
]
bars = ax.barh(methods, acc_vals, color=sns.color_palette("Greens_d", len(methods)))
ax.set_xlabel("Accuracy %")
ax.set_title("Accuracy on GND ground truth\n(among classified records)")
ax.set_xlim(0, 105)
for bar, val in zip(bars, acc_vals):
    label = f"{val:.1f}%" if val > 0 else "N/A"
    ax.text(
        val + 0.5, bar.get_y() + bar.get_height() / 2, label, va="center", fontsize=9
    )

plt.tight_layout()
out1 = OUTPUT / "benchmark_coverage_accuracy.png"
plt.savefig(out1, dpi=150)
print(f"\nPlot saved → {out1}")
plt.close()

# Stacked distribution bar
plot_labels = [
    "male",
    "female",
    "conflict",
    "unknown",
    "unisex",
    "no_name",
    "NaN/missing",
]
colors = ["#4472C4", "#ED7D31", "#FFC000", "#A9D18E", "#9DC3E6", "#BFBFBF", "#E2EFDA"]

fig, ax = plt.subplots(figsize=(14, 5))
totals = {m: sum(int(dist_df.loc[m, l]) for l in plot_labels) for m in methods}
left = np.zeros(len(methods))

for lbl, clr in zip(plot_labels, colors):
    vals = np.array(
        [
            int(dist_df.loc[m, lbl]) / totals[m] * 100 if totals[m] > 0 else 0
            for m in methods
        ]
    )
    ax.barh(methods, vals, left=left, label=lbl, color=clr)
    for i, (v, l) in enumerate(zip(vals, left)):
        if v > 3:
            ax.text(l + v / 2, i, f"{v:.0f}%", ha="center", va="center", fontsize=8)
    left += vals

ax.set_xlabel("Share of total records (%)")
ax.set_title("Classification distribution per method")
ax.set_xlim(0, 100)
ax.legend(loc="lower right", ncol=3)
plt.tight_layout()
out2 = OUTPUT / "benchmark_distribution.png"
plt.savefig(out2, dpi=150)
print(f"Plot saved → {out2}")
plt.close()

print("\nDone.")
