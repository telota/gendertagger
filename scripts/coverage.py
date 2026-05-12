"""
Coverage & Classification Distribution Report
===============================================
Shows how much of the register each method actually covers, counting ALL
substantive labels (male, female, organisation, mostly_male, etc.) as
"classified" — not just binary male/female.

Three coverage tiers:
  - Binary (male / female only)
  - Substantive (any definitive label including organisation, mostly_*)
  - Overall (anything that is not no_name / NaN — includes ambiguous)

Also prints a full classification distribution per method.

Run from the project root:
    python scripts/coverage.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

RESULTS = Path("data/results")
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

# ── 0. Load all results ──────────────────────────────────────────────────────
files = {
    "gg_gender": ("gender_guesser_results.csv", "gender_guesser"),
    "hfgc_gender": ("hf_gender_classification_results.csv", "HF ClassifyGender"),
    "hfg_gender": ("hf_genderize_results.csv", "HF Genderize"),
    "hv_gender": ("hivoto_results.csv", "HIVOTO"),
    "xgb_gender": ("hivoto_xgboost_results.csv", "HIVOTO-XGBoost"),
    "nqg_gender": ("nqg_results.csv", "NQG"),
    "wgs_gender": ("wiki_gendersort_results.csv", "Wiki-Gendersort"),
    "llm_gender": ("llm_gender_results.csv", "LLM"),
}

base = None
for col, (fname, _) in files.items():
    df = pd.read_csv(RESULTS / fname, dtype=str, usecols=["xml_id", col])
    base = df if base is None else base.merge(df, on="xml_id", how="outer")

METHODS = {col: name for col, (_, name) in files.items()}
TOTAL = len(base)

print(f"Total persons in register: {TOTAL:,}\n")

# ── 1. Label taxonomy ────────────────────────────────────────────────────────
# What counts as what:
BINARY = {"male", "female"}
LEANING = {"mostly_male", "mostly_female"}
OTHER_SUBSTANTIVE = {"organisation"}
AMBIGUOUS = {"conflict", "unknown", "uncertain", "andy"}
FAILED = {"no_name", "nan", ""}


def categorise(val):
    """Categorise a single classifier output."""
    if pd.isna(val):
        return "no_answer"
    v = str(val).strip().lower()
    if v in FAILED:
        return "no_answer"
    if v in BINARY:
        return v  # "male" or "female"
    if v in LEANING:
        return v
    if v in OTHER_SUBSTANTIVE:
        return v
    if v in AMBIGUOUS:
        return v
    return v  # anything else, keep as-is


# ── 2. Full distribution per method ──────────────────────────────────────────
print("=" * 70)
print("CLASSIFICATION DISTRIBUTION PER METHOD")
print("=" * 70)

all_labels = set()
dist_data = {}

for col, name in METHODS.items():
    cats = base[col].apply(categorise)
    counts = cats.value_counts()
    dist_data[name] = counts
    all_labels.update(counts.index)

# Sort labels in a sensible order
label_order = [
    "male",
    "female",
    "mostly_male",
    "mostly_female",
    "organisation",
    "conflict",
    "unknown",
    "uncertain",
    "andy",
    "no_answer",
]
# Add any labels we haven't accounted for
for lbl in sorted(all_labels):
    if lbl not in label_order:
        label_order.insert(-1, lbl)  # insert before no_answer

dist_df = pd.DataFrame(dist_data).reindex(label_order).fillna(0).astype(int)
dist_pct = dist_df.div(TOTAL) * 100

print("\nAbsolute counts:")
print(dist_df.to_string())
print("\nPercentages:")
print(dist_pct.round(1).to_string())

# ── 3. Coverage tiers ────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("COVERAGE TIERS PER METHOD")
print("=" * 70)

cov_rows = []
for col, name in METHODS.items():
    cats = base[col].apply(categorise)

    n_male = (cats == "male").sum()
    n_female = (cats == "female").sum()
    n_mostly_m = (cats == "mostly_male").sum()
    n_mostly_f = (cats == "mostly_female").sum()
    n_org = (cats == "organisation").sum()
    n_ambiguous = cats.isin(AMBIGUOUS).sum()
    n_no_answer = (cats == "no_answer").sum()

    binary = n_male + n_female
    substantive = binary + n_mostly_m + n_mostly_f + n_org
    any_answer = TOTAL - n_no_answer

    cov_rows.append(
        {
            "Method": name,
            "Male": n_male,
            "Female": n_female,
            "Leaning (m/f)": n_mostly_m + n_mostly_f,
            "Organisation": n_org,
            "Ambiguous": n_ambiguous,
            "No answer": n_no_answer,
            "Binary cov.": f"{binary / TOTAL * 100:.1f}%",
            "Substantive cov.": f"{substantive / TOTAL * 100:.1f}%",
            "Any answer": f"{any_answer / TOTAL * 100:.1f}%",
        }
    )

cov_df = pd.DataFrame(cov_rows).set_index("Method")
print(cov_df.to_string())

# ── 4. Coverage comparison chart ─────────────────────────────────────────────
methods = list(METHODS.values())

fig, ax = plt.subplots(figsize=(12, 6))

# Compute the three tiers as percentages
binary_pcts = []
subst_pcts = []
any_pcts = []

for col, name in METHODS.items():
    cats = base[col].apply(categorise)
    n_male = (cats == "male").sum()
    n_female = (cats == "female").sum()
    n_mostly_m = (cats == "mostly_male").sum()
    n_mostly_f = (cats == "mostly_female").sum()
    n_org = (cats == "organisation").sum()
    n_no_answer = (cats == "no_answer").sum()

    binary_pcts.append((n_male + n_female) / TOTAL * 100)
    subst_pcts.append(
        (n_male + n_female + n_mostly_m + n_mostly_f + n_org) / TOTAL * 100
    )
    any_pcts.append((TOTAL - n_no_answer) / TOTAL * 100)

y = np.arange(len(methods))
h = 0.25

bars3 = ax.barh(
    y + h,
    any_pcts,
    h,
    label="Any answer (incl. ambiguous)",
    color="#D9D9D9",
    edgecolor="white",
)
bars2 = ax.barh(
    y,
    subst_pcts,
    h,
    label="Substantive (m/f/org/leaning)",
    color="#A9D18E",
    edgecolor="white",
)
bars1 = ax.barh(
    y - h,
    binary_pcts,
    h,
    label="Binary (male/female only)",
    color="#4472C4",
    edgecolor="white",
)

# Add percentage labels
for bars in [bars1, bars2, bars3]:
    for bar in bars:
        w = bar.get_width()
        ax.text(
            w + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{w:.1f}%",
            va="center",
            fontsize=8,
        )

ax.set_yticks(y)
ax.set_yticklabels(methods)
ax.set_xlabel("Coverage (%)")
ax.set_xlim(0, 110)
ax.set_title("Coverage per Method — Three Tiers")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=9)
ax.invert_yaxis()

plt.tight_layout()
plt.subplots_adjust(bottom=0.2)
out1 = OUTPUT / "coverage_tiers.png"
plt.savefig(out1, dpi=200, bbox_inches="tight", facecolor="white")
print(f"\nPlot saved → {out1}")
plt.close()

# ── 5. Stacked distribution chart ────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 6))

# Group into display categories
display_cats = ["male", "female", "organisation", "leaning", "ambiguous", "no_answer"]
display_colors = ["#4472C4", "#ED7D31", "#9B59B6", "#70AD47", "#FFC000", "#D9D9D9"]
display_labels = [
    "Male",
    "Female",
    "Organisation",
    "Leaning (mostly m/f)",
    "Ambiguous",
    "No answer",
]

stacked_data = {}
for col, name in METHODS.items():
    cats = base[col].apply(categorise)
    stacked_data[name] = {
        "male": (cats == "male").sum(),
        "female": (cats == "female").sum(),
        "organisation": (cats == "organisation").sum(),
        "leaning": cats.isin({"mostly_male", "mostly_female"}).sum(),
        "ambiguous": cats.isin(AMBIGUOUS).sum(),
        "no_answer": (cats == "no_answer").sum(),
    }

left = np.zeros(len(methods))
for cat, color, label in zip(display_cats, display_colors, display_labels):
    vals = np.array([stacked_data[m][cat] / TOTAL * 100 for m in methods])
    bars = ax.barh(
        methods,
        vals,
        left=left,
        label=label,
        color=color,
        edgecolor="white",
        linewidth=0.5,
    )
    for i, (v, l) in enumerate(zip(vals, left)):
        if v > 2.5:
            ax.text(l + v / 2, i, f"{v:.0f}%", ha="center", va="center", fontsize=8)
    left += vals

ax.set_xlabel("Share of register (%)")
ax.set_title("Classification Distribution per Method")
ax.set_xlim(0, 100)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=9)
ax.invert_yaxis()

plt.tight_layout()
plt.subplots_adjust(bottom=0.2)
out2 = OUTPUT / "coverage_distribution.png"
plt.savefig(out2, dpi=200, bbox_inches="tight", facecolor="white")
print(f"Plot saved → {out2}")
plt.close()

# ── 6. Save distribution CSV ─────────────────────────────────────────────────
out_csv = OUTPUT / "coverage_distribution.csv"
dist_df.to_csv(out_csv)
print(f"Distribution CSV → {out_csv}")

print("\nDone.")
