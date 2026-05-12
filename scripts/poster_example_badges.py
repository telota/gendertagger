"""
Poster Example Badges — Two-Person Method Comparison
=====================================================
Visualises how all 7 gender classification methods classify two example
persons from the Schleiermacher register:

  • Friedrich Daniel Ernst Schleiermacher (S0003676) — male
  • Henriette (Jette) Schleiermacher (S0003677) — female

Each method is shown as a colour-coded badge with the classification
result and confidence percentage (where available).

Run from the project root:
    python scripts/poster_example_badges.py
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

# ── Colour palette ────────────────────────────────────────────────────────────
MALE_COLOR = "#4472C4"  # Steel blue
MALE_LIGHT = "#D6E4F0"  # Light blue background
FEMALE_COLOR = "#ED7D31"  # Warm orange
FEMALE_LIGHT = "#FDE8D0"  # Light orange background
GND_COLOR = "#C8A951"  # Gold for ground truth
GND_LIGHT = "#FFF5D6"  # Light gold
TEXT_DARK = "#1A1A1A"
TEXT_MID = "#555555"
WHITE = "#FFFFFF"
CARD_BG = "#F7F7F7"

# ── Data ──────────────────────────────────────────────────────────────────────
# Method display names and abbreviations
METHODS = [
    ("gender-guesser", "Dictionary lookup"),
    ("ClassifyGender\n(DistilBERT)", "Transformer"),
    ("Genderize\n(BERT)", "Transformer"),
    ("HIVOTO", "Phonetic rules"),
    ("nomquamgender", "Statistical"),
    ("Wiki-Gendersort", "Wikipedia-based"),
    ("LLM\n(gpt-oss:20b)", "Large Language Model"),
]

# Friedrich Daniel Ernst Schleiermacher (S0003676)
# All methods → male
FRIEDRICH = {
    "name": "Friedrich Daniel Ernst\nSchleiermacher",
    "years": "(1768–1834)",
    "gnd_label": "male",
    "xml_id": "S0003676",
    "results": [
        ("male", None),  # gender-guesser — no numeric confidence
        ("male", 1.000),  # ClassifyGender — avg(1.0, 1.0, 1.0)
        ("male", 0.991),  # Genderize — avg(0.9938, 0.9884, 0.9916)
        ("male", None),  # HIVOTO — "sicher" but no numeric
        ("male", 0.988),  # nomquamgender — 1 - avg(0.000, 0.016, 0.020)
        ("male", None),  # Wiki-Gendersort — no numeric confidence
        ("male", 0.990),  # LLM — 0.99
    ],
}

# Henriette (Jette) Schleiermacher, née von Mühlenfels (S0003677)
# All methods → female
HENRIETTE = {
    "name": "Henriette (Jette)\nSchleiermacher",
    "years": "(1788–1840)",
    "gnd_label": "female",
    "xml_id": "S0003677",
    "results": [
        ("female", None),  # gender-guesser
        ("female", 1.000),  # ClassifyGender — 1.0
        ("female", 0.983),  # Genderize — 0.9825
        ("female", None),  # HIVOTO — "sicher"
        ("female", 0.989),  # nomquamgender — 0.989
        ("female", None),  # Wiki-Gendersort
        ("female", 0.990),  # LLM — 0.99
    ],
}


def draw_rounded_rect(ax, x, y, w, h, radius=0.15, **kwargs):
    """Draw a rounded rectangle."""
    fancy = mpatches.FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=mpatches.BoxStyle.Round(pad=0, rounding_size=radius),
        **kwargs,
    )
    ax.add_patch(fancy)
    return fancy


def draw_person_card(ax, person, x_offset, card_width):
    """Draw a full person card with GND header and 7 method badges."""
    badge_h = 0.55
    badge_gap = 0.18
    top_y = 8.5

    is_male = person["gnd_label"] == "male"
    accent = MALE_COLOR if is_male else FEMALE_COLOR
    accent_light = MALE_LIGHT if is_male else FEMALE_LIGHT

    # ── Person header ─────────────────────────────────────────────────────
    header_y = top_y + 0.3
    ax.text(
        x_offset + card_width / 2,
        header_y + 1.05,
        person["name"],
        ha="center",
        va="center",
        fontsize=14,
        fontweight="bold",
        color=TEXT_DARK,
        linespacing=1.3,
    )
    ax.text(
        x_offset + card_width / 2,
        header_y + 0.15,
        person["years"],
        ha="center",
        va="center",
        fontsize=10,
        color=TEXT_MID,
    )

    # ── GND ground truth badge ────────────────────────────────────────────
    gnd_y = header_y - 0.85
    gnd_w = card_width - 0.6
    gnd_x = x_offset + 0.3
    draw_rounded_rect(
        ax,
        gnd_x,
        gnd_y,
        gnd_w,
        badge_h,
        radius=0.18,
        facecolor=GND_LIGHT,
        edgecolor=GND_COLOR,
        linewidth=2,
        zorder=3,
    )
    # Gold star marker + label
    ax.plot(
        gnd_x + 0.25,
        gnd_y + badge_h / 2,
        marker="*",
        markersize=14,
        color=GND_COLOR,
        markeredgecolor="#8B7332",
        markeredgewidth=0.5,
        zorder=4,
    )
    ax.text(
        gnd_x + 0.55,
        gnd_y + badge_h / 2,
        "GND Ground Truth",
        ha="left",
        va="center",
        fontsize=10,
        fontweight="bold",
        color="#8B7332",
        zorder=4,
    )
    label_text = person["gnd_label"].upper()
    symbol = "♂" if is_male else "♀"
    ax.text(
        gnd_x + gnd_w - 0.25,
        gnd_y + badge_h / 2,
        f"{symbol} {label_text}",
        ha="right",
        va="center",
        fontsize=11,
        fontweight="bold",
        color=accent,
        zorder=4,
    )

    # ── Method badges ─────────────────────────────────────────────────────
    badge_w = card_width - 0.6
    badge_x = x_offset + 0.3

    for i, ((method_name, method_type), (result, confidence)) in enumerate(
        zip(METHODS, person["results"])
    ):
        by = gnd_y - (i + 1) * (badge_h + badge_gap)
        result_is_male = result == "male"
        bg_color = MALE_LIGHT if result_is_male else FEMALE_LIGHT
        border_color = MALE_COLOR if result_is_male else FEMALE_COLOR
        result_color = MALE_COLOR if result_is_male else FEMALE_COLOR

        # Badge background
        draw_rounded_rect(
            ax,
            badge_x,
            by,
            badge_w,
            badge_h,
            radius=0.18,
            facecolor=bg_color,
            edgecolor=border_color,
            linewidth=1.5,
            zorder=3,
        )

        # Method name (left side)
        ax.text(
            badge_x + 0.2,
            by + badge_h / 2,
            method_name,
            ha="left",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=TEXT_DARK,
            zorder=4,
            linespacing=0.9,
        )

        # Result symbol + label (right side)
        symbol = "♂" if result_is_male else "♀"
        ax.text(
            badge_x + badge_w - 0.25,
            by + badge_h / 2 + (0.1 if confidence is not None else 0),
            f"{symbol} {result}",
            ha="right",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=result_color,
            zorder=4,
        )

        # Confidence percentage (under result, if available)
        if confidence is not None:
            pct_text = f"{confidence * 100:.1f} %"
            ax.text(
                badge_x + badge_w - 0.25,
                by + badge_h / 2 - 0.14,
                pct_text,
                ha="right",
                va="center",
                fontsize=8.5,
                color=TEXT_MID,
                zorder=4,
            )
        else:
            # Show a small "no score" indicator
            ax.text(
                badge_x + badge_w - 0.25,
                by + badge_h / 2 - 0.07,
                "",
                ha="right",
                va="center",
                fontsize=7,
                color="#AAAAAA",
                zorder=4,
            )

        # Confidence bar (thin, inside badge at bottom)
        if confidence is not None:
            bar_y = by + 0.06
            bar_h = 0.05
            bar_max_w = badge_w - 0.4
            bar_x = badge_x + 0.2
            # Background bar
            draw_rounded_rect(
                ax,
                bar_x,
                bar_y,
                bar_max_w,
                bar_h,
                radius=0.02,
                facecolor="#E8E8E8",
                edgecolor="none",
                zorder=4,
            )
            # Filled bar
            fill_w = bar_max_w * confidence
            if fill_w > 0.04:
                draw_rounded_rect(
                    ax,
                    bar_x,
                    bar_y,
                    fill_w,
                    bar_h,
                    radius=0.02,
                    facecolor=border_color,
                    edgecolor="none",
                    alpha=0.6,
                    zorder=5,
                )


# ── Build figure ──────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 11))
ax.set_xlim(0, 14)
ax.set_ylim(-0.5, 11.5)
ax.set_aspect("equal")
ax.axis("off")

# Title
ax.text(
    7,
    11.0,
    "Example: Classification of Two Register Entries",
    ha="center",
    va="center",
    fontsize=16,
    fontweight="bold",
    color=TEXT_DARK,
)
ax.text(
    7,
    10.55,
    "How 7 independent methods classify the same person by forename",
    ha="center",
    va="center",
    fontsize=11,
    color=TEXT_MID,
)

# Draw both cards
card_w = 5.8
gap = 0.8
left_x = (14 - 2 * card_w - gap) / 2
right_x = left_x + card_w + gap

draw_person_card(ax, FRIEDRICH, left_x, card_w)
draw_person_card(ax, HENRIETTE, right_x, card_w)

# Divider line between cards
mid_x = left_x + card_w + gap / 2
ax.plot(
    [mid_x, mid_x],
    [0.5, 9.8],
    color="#DDDDDD",
    linewidth=1,
    linestyle="--",
    zorder=1,
)

# Legend at bottom
legend_y = -0.1
ax.text(
    7,
    legend_y,
    "Confidence bars shown for methods that output probability scores  ·  "
    "GND (Gemeinsame Normdatei) serves as ground truth",
    ha="center",
    va="center",
    fontsize=8.5,
    color=TEXT_MID,
    style="italic",
)

plt.tight_layout()

# Save
out_png = OUTPUT / "poster_example_badges.png"
out_svg = OUTPUT / "poster_example_badges.svg"
fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor="white")
fig.savefig(out_svg, bbox_inches="tight", facecolor="white")
print(f"Saved → {out_png}")
print(f"Saved → {out_svg}")
plt.close()

print("Done.")
