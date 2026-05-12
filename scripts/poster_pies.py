"""
Poster Pie Charts — Register Gender Distribution
==================================================
Produces two pie charts for the poster:

1. "Before" — Current state of the register (GND coverage only)
   Segments: Male (GND) | Female (GND) | Unknown (GND) | No GND

2. "After" — Fully annotated register (ensemble of all classifiers)
   Segments: Male | Female | Organisation | Unknown

Aggregation strategy for the "after" pie:
  - GND ground truth takes priority when available (male/female).
  - For persons without GND (or GND=unknown): use majority vote
    across all 7 classifiers (gg, hfgc, hfg, hv, xgb, nqg, llm).
  - "organisation" is a special label only the LLM produces; if the
    LLM says organisation AND no other classifier says male/female
    with a clear majority, the person is labelled "organisation".
  - Everything else → "unknown".

Run from the project root:
    python scripts/poster_pies.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from collections import Counter
from pathlib import Path

RESULTS = Path("data/results")
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

# ── 0. Load all results ──────────────────────────────────────────────────────
gnd = pd.read_csv(RESULTS / "gnd_gender_results.csv", dtype=str)
gg = pd.read_csv(RESULTS / "gender_guesser_results.csv", dtype=str)[
    ["xml_id", "gg_gender"]
]
hfgc = pd.read_csv(RESULTS / "hf_gender_classification_results.csv", dtype=str)[
    ["xml_id", "hfgc_gender"]
]
hfg = pd.read_csv(RESULTS / "hf_genderize_results.csv", dtype=str)[
    ["xml_id", "hfg_gender"]
]
hv = pd.read_csv(RESULTS / "hivoto_results.csv", dtype=str)[["xml_id", "hv_gender"]]
xgb = pd.read_csv(RESULTS / "hivoto_xgboost_results.csv", dtype=str)[
    ["xml_id", "xgb_gender"]
]
nqg = pd.read_csv(RESULTS / "nqg_results.csv", dtype=str)[["xml_id", "nqg_gender"]]
llm = pd.read_csv(RESULTS / "llm_gender_results.csv", dtype=str)[
    ["xml_id", "llm_gender"]
]

# Merge everything
base = gnd[["xml_id", "gnd_gender_mapped"]].copy()
for df in [gg, hfgc, hfg, hv, xgb, nqg, llm]:
    base = base.merge(df, on="xml_id", how="outer")

CLASSIFIER_COLS = [
    "gg_gender",
    "hfgc_gender",
    "hfg_gender",
    "hv_gender",
    "xgb_gender",
    "nqg_gender",
    "llm_gender",
]

print(f"Total persons: {len(base):,}")

# ── 1. PIE 1 — "Before" (GND coverage) ───────────────────────────────────────
gnd_map = base["gnd_gender_mapped"].fillna("no_gnd")
pie1 = {
    "Male (GND)": (gnd_map == "male").sum(),
    "Female (GND)": (gnd_map == "female").sum(),
    "Unknown (GND)": (gnd_map == "unknown").sum() + (gnd_map == "error").sum(),
    "No GND": (gnd_map == "no_gnd").sum(),
}

print("\n" + "=" * 55)
print("PIE 1 — BEFORE (GND coverage)")
print("=" * 55)
for k, v in pie1.items():
    print(f"  {k:20s}: {v:>6,}  ({v/len(base)*100:.1f}%)")
print(f"  {'Total':20s}: {sum(pie1.values()):>6,}")

# ── 2. Aggregation — ensemble label per person ───────────────────────────────
MALE_LABELS = {"male", "mostly_male"}
FEMALE_LABELS = {"female", "mostly_female"}
AMBIGUOUS_LABELS = {"conflict", "unknown", "uncertain", "andy"}
FAILED_LABELS = {"no_name", "nan", ""}
ORG_LABEL = "organisation"


def normalise_vote(val):
    """Map a classifier output to a canonical vote."""
    if pd.isna(val):
        return None
    v = str(val).strip().lower()
    if v in FAILED_LABELS:
        return None
    if v in MALE_LABELS:
        return "male"
    if v in FEMALE_LABELS:
        return "female"
    if v == ORG_LABEL:
        return "organisation"
    # ambiguous labels → counted as abstention in majority vote
    return "ambiguous"


def ensemble_label(row):
    """
    Determine a single gender label for a person:
    1. If GND says male/female → trust GND
    2. Otherwise: majority vote across all classifiers
       - "organisation" wins if LLM says so and others abstain/agree
       - male/female need a strict majority of non-abstaining votes
       - else "unknown"
    """
    gnd_val = (
        str(row["gnd_gender_mapped"]).strip().lower()
        if pd.notna(row["gnd_gender_mapped"])
        else ""
    )

    # GND is ground truth
    if gnd_val == "male":
        return "male"
    if gnd_val == "female":
        return "female"

    # Collect votes from all classifiers
    votes = []
    for col in CLASSIFIER_COLS:
        v = normalise_vote(row[col])
        if v is not None:
            votes.append(v)

    if not votes:
        return "unknown"

    counts = Counter(votes)

    # If "organisation" has any votes and there's no clear male/female majority
    org_votes = counts.get("organisation", 0)
    male_votes = counts.get("male", 0)
    female_votes = counts.get("female", 0)
    substantive_votes = male_votes + female_votes  # non-ambiguous, non-org

    # Organisation: LLM is the only classifier that can say this.
    # Trust it if the other classifiers mostly abstained or were ambiguous.
    if org_votes > 0 and substantive_votes <= org_votes:
        return "organisation"

    # Gender majority among substantive votes
    if substantive_votes == 0:
        return "unknown"

    if male_votes > female_votes:
        return "male"
    if female_votes > male_votes:
        return "female"

    # Tie between male and female — check total votes including ambiguous
    # If tied, go with the one that has more raw classifier votes
    raw_male = sum(
        1
        for col in CLASSIFIER_COLS
        if pd.notna(row[col]) and str(row[col]).strip().lower() in MALE_LABELS
    )
    raw_female = sum(
        1
        for col in CLASSIFIER_COLS
        if pd.notna(row[col]) and str(row[col]).strip().lower() in FEMALE_LABELS
    )
    if raw_male > raw_female:
        return "male"
    if raw_female > raw_male:
        return "female"

    return "unknown"


print("\nComputing ensemble labels...")
base["ensemble_label"] = base.apply(ensemble_label, axis=1)

# ── 3. PIE 2 — "After" (fully annotated) ─────────────────────────────────────
pie2 = {
    "Male": (base["ensemble_label"] == "male").sum(),
    "Female": (base["ensemble_label"] == "female").sum(),
    "Organisation": (base["ensemble_label"] == "organisation").sum(),
    "Unknown": (base["ensemble_label"] == "unknown").sum(),
}

print("\n" + "=" * 55)
print("PIE 2 — AFTER (fully annotated via ensemble)")
print("=" * 55)
for k, v in pie2.items():
    print(f"  {k:20s}: {v:>6,}  ({v/len(base)*100:.1f}%)")
print(f"  {'Total':20s}: {sum(pie2.values()):>6,}")

# ── 4. Breakdown: where did each ensemble label come from? ───────────────────
print("\n" + "=" * 55)
print("PROVENANCE — How each ensemble label was determined")
print("=" * 55)

for label in ["male", "female", "organisation", "unknown"]:
    subset = base[base["ensemble_label"] == label]
    from_gnd = subset["gnd_gender_mapped"].isin(["male", "female"]).sum()
    from_vote = len(subset) - from_gnd
    print(
        f"  {label:15s}: {len(subset):>5,} total  |  {from_gnd:>5,} from GND  |  {from_vote:>5,} from classifier vote"
    )

# ── 5. Plot ───────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

# Poster-friendly colours
COLORS_BEFORE = ["#4472C4", "#ED7D31", "#A9D18E", "#D9D9D9"]
COLORS_AFTER = ["#4472C4", "#ED7D31", "#9B59B6", "#D9D9D9"]

# Pie 1 — Before
ax = axes[0]
values1 = list(pie1.values())
labels1 = [f"{k}\n{v:,} ({v/sum(values1)*100:.1f}%)" for k, v in pie1.items()]
wedges1, texts1 = ax.pie(
    values1,
    labels=labels1,
    colors=COLORS_BEFORE,
    startangle=90,
    textprops={"fontsize": 10},
    wedgeprops={"edgecolor": "white", "linewidth": 1.5},
)
ax.set_title("Before — GND Coverage Only", fontsize=14, fontweight="bold", pad=20)

# Pie 2 — After
ax = axes[1]
values2 = list(pie2.values())
labels2 = [f"{k}\n{v:,} ({v/sum(values2)*100:.1f}%)" for k, v in pie2.items()]
wedges2, texts2 = ax.pie(
    values2,
    labels=labels2,
    colors=COLORS_AFTER,
    startangle=90,
    textprops={"fontsize": 10},
    wedgeprops={"edgecolor": "white", "linewidth": 1.5},
)
ax.set_title("After — Ensemble Classification", fontsize=14, fontweight="bold", pad=20)

plt.suptitle(
    "Schleiermacher Person Register — Gender Coverage",
    fontsize=16,
    fontweight="bold",
    y=0.98,
)
plt.tight_layout(rect=[0, 0, 1, 0.93])

out_path = OUTPUT / "poster_gender_pies.png"
plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
print(f"\nPlot saved → {out_path}")
plt.close()

# Also save the per-person ensemble results
out_csv = OUTPUT / "ensemble_gender_labels.csv"
base[["xml_id", "gnd_gender_mapped", "ensemble_label"] + CLASSIFIER_COLS].to_csv(
    out_csv, index=False
)
print(f"Ensemble labels → {out_csv}")

print("\nDone.")
