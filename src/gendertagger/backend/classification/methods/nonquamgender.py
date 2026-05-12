"""
nomquamgender (nqg) lookup for Schleiermacher persons.

For each person in the input CSV the forename field is split into tokens
(same rules as gender_guesser_lookup.py and hivoto_lookup.py) and each
token is looked up via nqg.NBGC.annotate(). The native output is a
probability p(gf) — probability of being gendered female — which is stored
as-is alongside a categorical label derived from a configurable threshold.

Threshold logic (default threshold = 0.1):
  p(gf)  ≤  threshold            → male
  p(gf)  ≥  1 − threshold        → female
  threshold < p(gf) < 1-threshold → uncertain
  NaN (name not in database)      → unknown

Consensus across tokens: same as other classifiers:
  male / female  >  uncertain  >  unknown  >  no_name
  conflicting male + female tokens → conflict

Output columns:
  xml_id       – Schleiermacher register ID (primary/foreign key)
  forename     – original forename string
  nqg_tokens   – pipe-separated tokens actually checked
  nqg_pgf      – pipe-separated p(gf) values per token (NaN if not found)
  nqg_results  – pipe-separated categorical label per token
  nqg_gender   – consensus gender across all tokens

Usage:
    python src/nqg_lookup.py
"""

import re
from pathlib import Path

import pandas as pd
import nomquamgender as nqg

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

INPUT_CSV  = Path("data/input/schleiermacher_persons.csv")
OUTPUT_DIR = Path("data/results")
OUTPUT_CSV = OUTPUT_DIR / "nqg_results.csv"

# ---------------------------------------------------------------------------
# Classification threshold
# ---------------------------------------------------------------------------

THRESHOLD = 0.1   # p(gf) ≤ THRESHOLD → male; ≥ 1-THRESHOLD → female


def classify(pgf: float) -> str:
    """Map a p(gf) float to a categorical label."""
    if pd.isna(pgf):
        return "unknown"
    if pgf <= THRESHOLD:
        return "male"
    if pgf >= 1 - THRESHOLD:
        return "female"
    return "uncertain"


# ---------------------------------------------------------------------------
# Consensus  (mirrors gender_guesser_lookup.py / hivoto_lookup.py)
# ---------------------------------------------------------------------------

PRIORITY      = ["no_name", "unknown", "uncertain", "male", "female"]
PRIORITY_RANK = {v: i for i, v in enumerate(PRIORITY)}
MALE_SET      = {"male"}
FEMALE_SET    = {"female"}


def consensus(results: list[str]) -> str:
    if not results:
        return "no_name"
    definite     = {r for r in results if r in MALE_SET | FEMALE_SET}
    male_votes   = definite & MALE_SET
    female_votes = definite & FEMALE_SET
    if male_votes and female_votes:
        return "conflict"
    return max(results, key=lambda r: PRIORITY_RANK.get(r, 0))


# ---------------------------------------------------------------------------
# Token filtering  (same rules as the other lookup scripts)
# ---------------------------------------------------------------------------

_SKIP_RE = re.compile(
    r"""
    ^\(          |   # bracketed: (Frau), (Kinder...)
    \)$          |   # closing bracket (trailing)
    ^\w\.$       |   # single-letter abbreviations: L., A., ...
    ^\d          |   # starts with digit
    ^-+$             # dashes only
    """,
    re.VERBOSE,
)

_PARTICLES = {
    "af", "da", "de", "dei", "del", "della", "dem", "der", "des", "di", "du",
    "ibn", "il", "la", "le", "les", "van", "vom", "von", "zu", "zum", "zur",
    "v", "v.",
    "comte", "conte", "duc", "d",
    "al", "al-din", "al-husayn",
    "an", "e", "in", "mit", "of", "und",
    "d.", "geb.", "jr.", "jun.", "med.", "od.", "phil.", "sen.",
    "biblische", "die", "eisernen", "historisch-philologische", "ihre",
    "kurmärkische", "mathematische", "mittlere", "philosophisch-historische",
    "philosophische", "physikalisch-mathematische", "physikalische",
    "reformiertes",
}


def usable_tokens(forename: str | None) -> list[str]:
    """Split a forename string and return checkable tokens."""
    if not forename or not isinstance(forename, str):
        return []
    result = []
    for t in forename.split():
        if _SKIP_RE.match(t):
            continue
        normalised = t.lower().rstrip(".,;:)\"'")
        if normalised in _PARTICLES:
            continue
        result.append(t)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("nomquamgender (nqg) lookup")
    print("=" * 50)
    print(f"Threshold: p(gf) ≤ {THRESHOLD} → male  |  ≥ {1-THRESHOLD} → female")

    model = nqg.NBGC()

    persons = pd.read_csv(INPUT_CSV, dtype=str)
    print(f"Input: {len(persons):,} persons from {INPUT_CSV}")

    rows = []
    for _, person in persons.iterrows():
        xml_id   = person["xml_id"]
        forename = person.get("forename", "")

        tokens = usable_tokens(forename)

        if not tokens:
            rows.append({
                "xml_id":      xml_id,
                "forename":    forename,
                "nqg_tokens":  "",
                "nqg_pgf":     "",
                "nqg_results": "",
                "nqg_gender":  "no_name",
            })
            continue

        annotations = model.annotate(tokens)   # list of [given, used, sources, counts, p(gf)]
        pgf_vals    = [a[4] for a in annotations]
        labels      = [classify(p) for p in pgf_vals]

        rows.append({
            "xml_id":      xml_id,
            "forename":    forename,
            "nqg_tokens":  "|".join(tokens),
            "nqg_pgf":     "|".join("" if pd.isna(p) else f"{p:.3f}" for p in pgf_vals),
            "nqg_results": "|".join(labels),
            "nqg_gender":  consensus(labels),
        })

    result = pd.DataFrame(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(result):,} rows → {OUTPUT_CSV}")

    print("\nGender distribution:")
    counts = result["nqg_gender"].value_counts()
    for label, n in counts.items():
        print(f"  {label:<16} {n:>6,}  ({n / len(result) * 100:.1f}%)")

    multi = result[result["nqg_tokens"].str.contains(r"\|", na=False)]
    print(f"\nPersons with multiple tokens checked: {len(multi):,}")


if __name__ == "__main__":
    main()
