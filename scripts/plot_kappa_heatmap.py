"""Render the pairwise Cohen's kappa heatmap used in the paper.

Reads the long-format kappa CSV produced by ``scripts/agreements.py`` and
writes ``docs/paper/figures/kappa_heatmap.{pdf,png}``.

The diagonal is left as N/A (self-comparison is trivially 1.0 and would
visually flatten the colour scale), the colour scale is fixed to the full
[0, 1] kappa range, and method names are harmonised with the labels used
throughout the paper.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Map CSV labels onto the names used in the paper text and tables.
LABEL_MAP = {
    "gender_guesser": "gender-guesser",
    "Wiki-Gendersort": "Wiki-Gendersort",
    "HIVOTO": "HIVOTO",
    "HIVOTO-XGBoost": "HIVOTO-XGBoost",
    "NQG": "nomquamgender",
    "HF ClassifyGender": "HF DistilBERT",
    "HF Genderize": "HF BERT-genderize",
    "LLM": "LLM",
}

# Row/column order chosen to surface the three method clusters discussed
# in the paper (dictionary, transformer, LLM).
METHOD_ORDER = [
    "HIVOTO",
    "HIVOTO-XGBoost",
    "nomquamgender",
    "gender-guesser",
    "Wiki-Gendersort",
    "HF DistilBERT",
    "HF BERT-genderize",
    "LLM",
]


def build_matrix(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["Classifier 1"] = df["Classifier 1"].map(LABEL_MAP)
    df["Classifier 2"] = df["Classifier 2"].map(LABEL_MAP)
    if df[["Classifier 1", "Classifier 2"]].isna().any().any():
        unknown = sorted(
            set(pd.read_csv(csv_path)["Classifier 1"]).union(
                pd.read_csv(csv_path)["Classifier 2"]
            )
            - set(LABEL_MAP)
        )
        raise ValueError(f"Unmapped classifier labels: {unknown}")

    matrix = pd.DataFrame(
        np.nan, index=METHOD_ORDER, columns=METHOD_ORDER, dtype=float
    )
    for _, row in df.iterrows():
        a, b, k = row["Classifier 1"], row["Classifier 2"], float(row["Cohen's Kappa"])
        matrix.loc[a, b] = k
        matrix.loc[b, a] = k
    return matrix


def render(matrix: pd.DataFrame, out_base: Path) -> None:
    n = len(matrix)
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    # viridis_r (dark/purple = high agreement) matches the poster pies and
    # aligns with the "darker = stronger" convention common in published
    # kappa heatmaps.
    cmap = plt.get_cmap("viridis_r").copy()
    cmap.set_bad(color="#d9d9d9")
    masked = np.ma.masked_invalid(matrix.values)
    im = ax.imshow(masked, cmap=cmap, vmin=0.0, vmax=1.0)

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(matrix.columns, rotation=40, ha="right", fontsize=9)
    ax.set_yticklabels(matrix.index, fontsize=9)
    ax.tick_params(top=False, bottom=True, labeltop=False, labelbottom=True)

    # Cell annotations: kappa with two decimals for off-diagonal, "N/A" on
    # the diagonal. Text colour flips on the dark end of the colormap so
    # numbers stay legible.
    for i in range(n):
        for j in range(n):
            if i == j:
                ax.text(
                    j, i, "N/A",
                    ha="center", va="center",
                    color="#555555", fontsize=9, fontstyle="italic",
                )
            else:
                v = matrix.values[i, j]
                ax.text(
                    j, i, f"{v:.2f}",
                    ha="center", va="center",
                    color="white" if v > 0.55 else "black",
                    fontsize=9,
                )

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(r"Cohen's $\kappa$", fontsize=10)

    fig.tight_layout()
    out_base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out_base.with_suffix(".png"), bbox_inches="tight", dpi=200)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("output/cohens_kappa_results_20260512_210717.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/paper/figures/kappa_heatmap"),
        help="Output path without extension (.pdf and .png are written).",
    )
    args = parser.parse_args()
    matrix = build_matrix(args.input)
    render(matrix, args.output)
    print(f"Wrote {args.output.with_suffix('.pdf')} and .png")


if __name__ == "__main__":
    main()
