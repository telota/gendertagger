"""
Compute and print aggregate statistics for data/output/gender_summary.csv.

Sections:
  1. Overall majority-label distribution
  2. Certainty tier distribution
  3. n_methods_answered distribution
  4. Per-method coverage and label breakdown
  5. Per-method mean / median confidence
  6. IAA distribution (binned)

Run from project root:
    python scripts/summary_stats.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SUMMARY_CSV = Path("data/output/gender_summary.csv")

METHODS: dict[str, str] = {
    "pqg": "Paren. qualifier",
    "gg": "gender_guesser",
    "gnd": "GND",
    "hfgc": "HF ClassifyGender",
    "hfg": "HF Genderize",
    "hv": "HIVOTO",
    "nqg": "NQG",
    "wgs": "Wiki-Gendersort",
    "llm": "LLM",
}

SEP = "=" * 65


def _pct(n: int, total: int) -> str:
    return f"{n:>6,}  ({n / total * 100:5.1f}%)"


def main() -> None:
    df = pd.read_csv(SUMMARY_CSV, dtype=str)
    total = len(df)

    df["n_methods_answered"] = pd.to_numeric(df["n_methods_answered"], errors="coerce")
    df["iaa"] = pd.to_numeric(df["iaa"], errors="coerce")

    print(f"\n{SEP}")
    print(f"  GENDER SUMMARY STATISTICS   (N = {total:,} persons)")
    print(SEP)

    # ── 1. Overall majority-label distribution ────────────────────────────────
    print("\n1. PREDICTED GENDER DISTRIBUTION")
    print("-" * 40)
    for label, cnt in df["predicted_gender"].value_counts().items():
        print(f"  {label:<12}  {_pct(cnt, total)}")

    # ── 2. Certainty tier ─────────────────────────────────────────────────────
    CERT_LEGEND = {
        "high": "≥2 methods, IAA ≥ 0.75",
        "low": "≥2 methods, IAA ≥ 0.50",
        "contested": "≥2 methods, IAA < 0.50  (methods genuinely disagree on label)",
        "single": "LLM only, clear signal (llm_cert=high) – uncorroborated",
        "uncertain": "LLM only, weak or no evidence (llm_cert=low/uncertain)",
        "no_data": "no method could answer",
    }
    print(f"\n2. CERTAINTY TIER")
    print("-" * 65)
    order = ["high", "low", "contested", "single", "uncertain", "no_data"]
    cert_counts = df["cert"].value_counts()
    for tier in order:
        if tier not in cert_counts:
            continue
        cnt = cert_counts[tier]
        legend = CERT_LEGEND.get(tier, "")
        print(f"  {tier:<10}  {_pct(cnt, total)}   {legend}")

    # ── 3. n_methods_answered ─────────────────────────────────────────────────
    print(f"\n3. NUMBER OF METHODS THAT ANSWERED")
    print("-" * 40)
    for n, cnt in df["n_methods_answered"].value_counts().sort_index().items():
        print(f"  {int(n)} methods   {_pct(cnt, total)}")

    # ── 4. Per-method coverage and label breakdown ────────────────────────────
    print(f"\n4. PER-METHOD COVERAGE AND LABEL BREAKDOWN  (N = {total:,})")
    print("-" * 75)
    header = f"  {'Method':<22}  {'Answered':>8}  {'Cov%':>5}  {'male':>6}  {'female':>7}  {'unknown':>8}  {'inst.':>6}"
    print(header)
    print("  " + "-" * 73)
    for short, name in METHODS.items():
        col = f"{short}_gender"
        if col not in df.columns:
            continue
        answered = int(df[col].notna().sum())
        vc = df[col].value_counts()
        print(
            f"  {name:<22}  {answered:>8,}  {answered / total * 100:>5.1f}"
            f"  {int(vc.get('male', 0)):>6,}"
            f"  {int(vc.get('female', 0)):>7,}"
            f"  {int(vc.get('unknown', 0)):>8,}"
            f"  {int(vc.get('institution', 0)):>6,}"
        )

    # ── 5. Per-method confidence ──────────────────────────────────────────────
    print(f"\n5. PER-METHOD CONFIDENCE  (only rows with a confidence value)")
    print("-" * 60)
    print(f"  {'Method':<22}  {'n':>6}  {'mean':>6}  {'median':>7}  {'≥0.75':>7}")
    print("  " + "-" * 58)
    for short, name in METHODS.items():
        col = f"{short}_confidence"
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce").dropna()
        if vals.empty:
            continue
        hi = int((vals >= 0.75).sum())
        print(
            f"  {name:<22}  {len(vals):>6,}  {vals.mean():>6.3f}  {vals.median():>7.3f}  {hi:>6,}  ({hi / len(vals) * 100:.0f}%)"
        )

    # ── 6. IAA distribution ───────────────────────────────────────────────────
    iaa = df["iaa"].dropna()
    print(
        f"\n6. INTER-ANNOTATOR AGREEMENT (IAA)  (rows where ≥2 methods answered, n={len(iaa):,})"
    )
    print("-" * 50)
    print(f"  mean   = {iaa.mean():.3f}")
    print(f"  median = {iaa.median():.3f}")
    print(f"  min    = {iaa.min():.3f}")
    print(f"  max    = {iaa.max():.3f}")
    print()
    bins = [0.0, 0.5, 0.6, 0.75, 0.9, 1.001]
    labels = ["< 0.50", "0.50–0.60", "0.60–0.75", "0.75–0.90", "0.90–1.00"]
    bucketed = pd.cut(iaa, bins=bins, labels=labels, include_lowest=True)
    for lbl, cnt in bucketed.value_counts().sort_index().items():
        print(f"  {lbl}   {_pct(cnt, len(iaa))}")

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    main()
