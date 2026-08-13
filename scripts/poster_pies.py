"""
Poster Pie Charts — Register Gender Distribution
==================================================
Produces two pie charts for the poster:

1. "Before" — Current state of the register (GND coverage only)
   Segments: Male (GND) | Female (GND) | Unknown (GND) | No GND

2. "After"  — Fully annotated register (final reviewed labels)
   Segments: Male | Female | Institution | Unknown

The "after" values come from data/output/gender_reviewed.csv.
Per row, the final label is `corrected_gender` if non-empty
(manual review override), otherwise `predicted_gender`.

Run from the project root:
    python scripts/poster_pies.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

REVIEWED = Path("data/output/gender_reviewed.csv")
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

# ── 0. Load reviewed dataset ────────────────────────────────────────────────
df = pd.read_csv(REVIEWED, dtype=str)
print(f"Total persons: {len(df):,}")

# Final per-row label: corrected if reviewer set one, otherwise predicted.
corrected = df["corrected_gender"].fillna("").str.strip()
df["final_gender"] = corrected.where(corrected != "", df["predicted_gender"])

# ── 1. PIE 1 — "Before" (GND coverage) ──────────────────────────────────────
gnd = df["gnd_gender"].fillna("").str.strip().str.lower()
pie1 = {
    "Male (GND)": int((gnd == "male").sum()),
    "Female (GND)": int((gnd == "female").sum()),
    "Unknown (GND)": int((gnd == "unknown").sum()),
    "No GND": int((gnd == "").sum()),
}

print("\n" + "=" * 55)
print("PIE 1 — BEFORE (GND coverage)")
print("=" * 55)
for k, v in pie1.items():
    print(f"  {k:20s}: {v:>6,}  ({v / len(df) * 100:.1f}%)")
print(f"  {'Total':20s}: {sum(pie1.values()):>6,}")

# ── 2. PIE 2 — "After" (reviewed final labels) ──────────────────────────────
final = df["final_gender"].fillna("").str.strip().str.lower()
pie2 = {
    "Male": int((final == "male").sum()),
    "Female": int((final == "female").sum()),
    "Institution": int((final == "institution").sum()),
    "Unknown": int((final == "unknown").sum()),
}

print("\n" + "=" * 55)
print("PIE 2 — AFTER (final reviewed labels)")
print("=" * 55)
for k, v in pie2.items():
    print(f"  {k:15s}: {v:>6,}  ({v / len(df) * 100:.1f}%)")
print(f"  {'Total':15s}: {sum(pie2.values()):>6,}")

# ── 3. Colours (sampled from the viridis kappa-heatmap) ─────────────────────
_viridis = plt.get_cmap("viridis")
C_MALE = _viridis(0.15)         # deep blue/purple
C_FEMALE = _viridis(0.55)       # teal/green
C_INSTITUTION = _viridis(0.85)  # yellow-green
C_MISSING = "#BFBFBF"           # neutral grey for "no info"
C_MISSING_LIGHT = "#E0E0E0"     # lighter grey for GND=unknown

COLORS_BEFORE = [C_MALE, C_FEMALE, C_MISSING_LIGHT, C_MISSING]
COLORS_AFTER = [C_MALE, C_FEMALE, C_INSTITUTION, C_MISSING]


# ── 4. Plot helper ──────────────────────────────────────────────────────────
def _autopct(min_pct: float = 3.0):
    """Show percentage inside a slice only when it is >= min_pct."""

    def fmt(pct):
        return f"{pct:.1f}%" if pct >= min_pct else ""

    return fmt


def draw_pie(ax, data: dict, colors, title: str):
    labels = list(data.keys())
    values = list(data.values())
    total = sum(values)

    wedges, _texts, autotexts = ax.pie(
        values,
        labels=None,  # no inline labels → use legend instead, avoids overlap
        colors=colors,
        startangle=90,
        counterclock=False,
        autopct=_autopct(min_pct=3.0),
        pctdistance=0.72,
        textprops={"fontsize": 11, "color": "white", "fontweight": "bold"},
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
    )
    # Dark text on the light grey slices so percentages stay readable.
    for t, color in zip(autotexts, colors):
        if color in (C_MISSING_LIGHT, C_MISSING):
            t.set_color("#333333")

    ax.set_title(title, fontsize=14, fontweight="bold", pad=16)

    legend_labels = [
        f"{lab} — {val:,} ({val / total * 100:.1f}%)"
        for lab, val in zip(labels, values)
    ]
    ax.legend(
        wedges,
        legend_labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        frameon=False,
        fontsize=10,
        handlelength=1.2,
        handleheight=1.2,
    )


# ── 5. Render figure ────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 7.5))
draw_pie(axes[0], pie1, COLORS_BEFORE, "Before — GND Coverage Only")
draw_pie(axes[1], pie2, COLORS_AFTER, "After — Reviewed Final Labels")

plt.tight_layout(rect=[0, 0.02, 1, 1.0])

out_path = OUTPUT / "poster_gender_pies.png"
plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
plt.close()
print(f"\nPlot saved → {out_path}")
print("Done.")
