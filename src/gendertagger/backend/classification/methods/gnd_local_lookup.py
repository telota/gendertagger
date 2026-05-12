"""
GND gender lookup for Schleiermacher persons.

Joins the input persons CSV with the pre-built GND ground truth database
and writes the gender results to data/results/.

Output columns:
    xml_id              – Schleiermacher register ID (primary/foreign key)
    gnd_uri             – original GND URI from input CSV (or empty)
    gnd_id              – bare GND identifier (or empty)
    gnd_gender_mapped   – male / female / unknown / no_gnd
    gnd_gender_label    – raw label from GND (e.g. "Männlich")
    gnd_gender_id       – full GND gender URI
    gnd_preferred_name  – preferred name from GND
    http_status         – API response code (200, 404, …), NaN for no GND

Usage:
    python src/gnd_gender_lookup.py
"""

from pathlib import Path
import sqlite3
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

INPUT_CSV = Path("data/input/schleiermacher_persons.csv")
DB_PATH = Path("output/ground_truth.db")
OUTPUT_DIR = Path("data/results")
OUTPUT_CSV = OUTPUT_DIR / "gnd_gender_results.csv"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def extract_gnd_id(uri: str | None) -> str | None:
    """Extract the bare GND ID from a d-nb.info URI."""
    if not uri or not isinstance(uri, str):
        return None
    return uri.rstrip("/").split("/")[-1] if "d-nb.info/gnd" in uri else None


def main():
    print("GND gender lookup")
    print("=" * 50)

    # --- Load input CSV ---
    persons = pd.read_csv(INPUT_CSV, dtype=str)
    print(f"Input: {len(persons):,} persons from {INPUT_CSV}")

    # Derive bare GND id from URI column
    persons["gnd_id"] = persons["gnd_uri"].apply(extract_gnd_id)
    with_gnd = persons["gnd_id"].notna().sum()
    print(f"  with GND URI: {with_gnd:,}")

    # --- Load GND ground truth from SQLite ---
    conn = sqlite3.connect(DB_PATH)
    gnd = pd.read_sql(
        """
        SELECT
            gnd_id,
            gnd_gender_id,
            gnd_gender_label,
            gnd_gender_mapped,
            gnd_preferred_name,
            http_status
        FROM gnd_ground_truth
        """,
        conn,
    )
    conn.close()
    print(f"GND ground truth: {len(gnd):,} entries loaded from {DB_PATH}")

    # --- Join ---
    result = persons[["xml_id", "gnd_uri", "gnd_id"]].merge(
        gnd,
        on="gnd_id",
        how="left",
    )

    # Fill persons without GND
    result["gnd_gender_mapped"] = result["gnd_gender_mapped"].fillna("no_gnd")

    # --- Save ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(result):,} rows → {OUTPUT_CSV}")

    # --- Summary ---
    print("\nGender distribution:")
    counts = result["gnd_gender_mapped"].value_counts()
    for label, n in counts.items():
        print(f"  {label:<12} {n:>6,}  ({n / len(result) * 100:.1f}%)")


if __name__ == "__main__":
    main()
