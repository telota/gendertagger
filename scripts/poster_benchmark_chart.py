"""
Poster Benchmark Chart — Effective Accuracy + Per-Class Recall
===============================================================
Computes three metrics that actually differentiate the classifiers:

  1. Effective Accuracy  = Correct / Total GT records  (penalises abstentions)
  2. Male Recall         = Correct male / Total GT males
  3. Female Recall       = Correct female / Total GT females

Produces a grouped horizontal bar chart suitable for a poster.

Run from the project root:
    python scripts/poster_benchmark_chart.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

RESULTS = Path("data/results")
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

# ── 0. Load all result files ─────────────────────────────────────────────────
gnd = pd.read_csv(RESULTS / "gnd_gender_results.csv", dtype=str)

files = {
    "gg_gender": ("gender_guesser_results.csv", "gender-guesser"),
    "hfgc_gender": (
        "hf_gender_classification_results.csv",
        "ClassifyGender\n(DistilBERT)",
    ),
    "hfg_gender": ("hf_genderize_results.csv", "Genderize (BERT)"),
    "hv_gender": ("hivoto_results.csv", "HIVOTO"),
    # "xgb_gender": ("hivoto_xgboost_results.csv", "HIVOTO-XGBoost"),
    "nqg_gender": ("nqg_results.csv", "nomquamgender"),
    "wgs_gender": ("wiki_gendersort_results.csv", "Wiki-Gendersort"),
    "llm_gender": ("llm_gender_results.csv", "LLM\n(oss-gpt:20b)"),
}

base = gnd[["xml_id", "gnd_gender_mapped"]].copy()
for col, (fname, _) in files.items():
    df = pd.read_csv(RESULTS / fname, dtype=str, usecols=["xml_id", col])
    base = base.merge(df, on="xml_id", how="outer")

# ── 1. Ground truth subset ───────────────────────────────────────────────────
gt = base[base["gnd_gender_mapped"].isin(["male", "female"])].copy()
TOTAL_GT = len(gt)
TOTAL_MALE = (gt["gnd_gender_mapped"] == "male").sum()
TOTAL_FEMALE = (gt["gnd_gender_mapped"] == "female").sum()

print(f"Ground truth: {TOTAL_GT} records  ({TOTAL_MALE} male, {TOTAL_FEMALE} female)")

# ── 2. Compute metrics per method ────────────────────────────────────────────
rows = []
for col, (_, name) in files.items():
    pred = gt[col].fillna("").str.strip().str.lower()

    # Correct classifications
    male_mask = (pred == "male") & (gt["gnd_gender_mapped"] == "male")
    female_mask = (pred == "female") & (gt["gnd_gender_mapped"] == "female")
    correct_m = male_mask.sum()
    correct_f = female_mask.sum()
    correct_total = correct_m + correct_f

    # Answered (binary only)
    answered = pred.isin({"male", "female"}).sum()
    wrong = answered - correct_total

    eff_acc = correct_total / TOTAL_GT * 100
    male_recall = correct_m / TOTAL_MALE * 100
    female_recall = correct_f / TOTAL_FEMALE * 100
    precision = correct_total / answered * 100 if answered > 0 else 0

    rows.append(
        {
            "Method": name,
            "Answered": answered,
            "Correct": correct_total,
            "Wrong": wrong,
            "Effective Accuracy %": round(eff_acc, 1),
            "Male Recall %": round(male_recall, 1),
            "Female Recall %": round(female_recall, 1),
            "Precision %": round(precision, 1),
        }
    )

df = pd.DataFrame(rows).set_index("Method")
df = df.sort_values(
    "Effective Accuracy %", ascending=True
)  # best on top after invert_yaxis

print("\n" + "=" * 70)
print(
    "BENCHMARK METRICS (GT = {:,} records, {:,} male, {:,} female)".format(
        TOTAL_GT, TOTAL_MALE, TOTAL_FEMALE
    )
)
print("=" * 70)
print(df.to_string())

# ── 3. Grouped bar chart ─────────────────────────────────────────────────────
methods = df.index.tolist()
eff_acc = df["Effective Accuracy %"].values
male_rec = df["Male Recall %"].values
female_rec = df["Female Recall %"].values

y = np.arange(len(methods))
h = 0.22  # bar height (slightly narrower for visible gaps)
gap = 0.06  # extra space between bar groups

fig, ax = plt.subplots(figsize=(12, 7))

# Three bars per method — distinct greyscale fills (Figma-safe, no hatch)
bars_eff = ax.barh(
    y + h + gap,
    eff_acc,
    h,
    label="Overall Accuracy",
    color="#2D2D2D",
    edgecolor="black",
    linewidth=0.7,
)
bars_m = ax.barh(
    y,
    male_rec,
    h,
    label="Male Recall",
    color="#888888",
    edgecolor="black",
    linewidth=0.7,
)
bars_f = ax.barh(
    y - h - gap,
    female_rec,
    h,
    label="Female Recall",
    color="#D0D0D0",
    edgecolor="black",
    linewidth=0.7,
)

# Value labels on bars
for bars in [bars_eff, bars_m, bars_f]:
    for bar in bars:
        w = bar.get_width()
        ax.text(
            w + 0.4,
            bar.get_y() + bar.get_height() / 2,
            f"{w:.1f}%",
            va="center",
            fontsize=9,
        )

ax.set_yticks(y)
ax.set_yticklabels(methods, fontsize=11)
ax.set_xlabel("Percentage (%)", fontsize=12)
ax.set_xlim(0, 112)
ax.set_title(
    "Classifier Benchmark on GND Ground Truth\n"
    f"(N = {TOTAL_GT:,} persons: {TOTAL_MALE:,} male, {TOTAL_FEMALE:,} female)",
    fontsize=14,
    fontweight="bold",
    pad=15,
)

# Add a vertical reference line at the minimum interesting range
ax.axvline(x=50, color="#CCCCCC", linestyle="--", linewidth=0.8, zorder=0)

ax.legend(
    loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, fontsize=11, frameon=False
)
ax.invert_yaxis()

# Light grid
ax.xaxis.set_major_locator(mticker.MultipleLocator(10))
ax.xaxis.set_minor_locator(mticker.MultipleLocator(5))
ax.grid(axis="x", which="major", color="#E0E0E0", linewidth=0.5)
ax.set_axisbelow(True)

plt.tight_layout()
plt.subplots_adjust(bottom=0.12)

out_png = OUTPUT / "poster_benchmark_recall.png"
out_svg = OUTPUT / "poster_benchmark_recall.svg"
plt.savefig(out_png, dpi=200, bbox_inches="tight", facecolor="white")
plt.savefig(out_svg, bbox_inches="tight", facecolor="white")
print(f"\nPlot saved → {out_png}")
print(f"Plot saved → {out_svg}  (import this into Figma)")
plt.close()

print("\nDone.")
