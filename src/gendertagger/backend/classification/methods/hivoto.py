"""
hivoto gender lookup for Schleiermacher persons.

Looks up each forename token against the hivoto dataset
(Historisches Vornamentool, v1.0.0). The same token-splitting
and consensus logic as gender_guesser_lookup.py is used so
results are directly comparable.

Lookup strategy:
  - Primary key: Originalschreibung (lowercased)
  - Fallback key: Klassifizierte_Originalschreibung (lowercased, trailing dot stripped)
  - When a token matches multiple rows, majority vote on the mapped gender;
    ties are broken by priority rank (male/female > mostly_* > andy > unknown)

hivoto Namensgeschlecht → mapped label:
  männlich (Q18)                                    → male
  weiblich (Q17)                                    → female
  männlich, vorwiegend (Q1381598)                   → mostly_male
  weiblich, vorwiegend (Q1381599)                   → mostly_female
  männlich, vorwiegend (nur deutsche Vornamen) (…)  → mostly_male
  weiblich, vorwiegend (nur deutsche Vornamen) (…)  → mostly_female
  uneindeutig (Q369534)                             → andy
  unsicher                                          → unknown

Output columns:
  xml_id          – Schleiermacher register ID (primary/foreign key)
  forename        – original forename string
  hv_tokens       – pipe-separated tokens actually checked
  hv_results      – pipe-separated mapped gender per token
  hv_certainty    – pipe-separated Sicherheit per token (sicher / mittlere Sicherheit / -)
  hv_gender       – consensus gender across all tokens

Usage:
    python src/hivoto_lookup.py
"""

import re
from pathlib import Path
from collections import Counter

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

INPUT_CSV = Path("data/input/schleiermacher_persons.csv")
HIVOTO_CSV = Path("data/raw/HIVOTO/2026-02-09_hivoto_vs_1_0_0.csv")
OUTPUT_DIR = Path("data/results")
OUTPUT_CSV = OUTPUT_DIR / "hivoto_results.csv"

# ---------------------------------------------------------------------------
# Gender mapping
# ---------------------------------------------------------------------------


def map_gender(raw: str) -> str:
    """Map a hivoto Namensgeschlecht string to our internal label."""
    r = str(raw).strip()
    if r.startswith("männlich, vorwiegend"):
        return "mostly_male"
    if r.startswith("weiblich, vorwiegend"):
        return "mostly_female"
    if "männlich" in r:
        return "male"
    if "weiblich" in r:
        return "female"
    if "uneindeutig" in r:
        return "andy"
    return "unknown"


# ---------------------------------------------------------------------------
# Build lookup index
# ---------------------------------------------------------------------------


def build_index(hivoto: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """
    Return a dict: normalised_token → (mapped_gender, certainty).

    For tokens that appear multiple times (different sources / entries),
    majority vote is used. Ties are broken by priority rank.
    """
    PRIORITY = ["unknown", "andy", "mostly_male", "mostly_female", "male", "female"]
    PRIORITY_RANK = {v: i for i, v in enumerate(PRIORITY)}

    # Build per-key lists
    records: dict[str, list[tuple[str, str]]] = {}

    for _, row in hivoto.iterrows():
        orig = str(row["Originalschreibung"]).strip().lower()
        klas = str(row["Klassifizierte_Originalschreibung"]).strip().lower().rstrip(".")
        gender = map_gender(row["Namensgeschlecht"])
        certainty = str(row.get("Sicherheit_Geschlechtszuordnung", "")).strip()

        for key in {orig, klas}:
            if not key:
                continue
            records.setdefault(key, []).append((gender, certainty))

    # Aggregate
    index = {}
    for key, entries in records.items():
        genders = [e[0] for e in entries]
        counts = Counter(genders)
        # Majority vote; break ties by priority rank
        winner = max(counts, key=lambda g: (counts[g], PRIORITY_RANK.get(g, 0)))
        # Certainty: "sicher" if all entries are sicher, else "mittlere Sicherheit"
        certainties = {e[1] for e in entries}
        certainty = "sicher" if certainties == {"sicher"} else "mittlere Sicherheit"
        index[key] = (winner, certainty)

    return index


# ---------------------------------------------------------------------------
# Token filtering  (same rules as gender_guesser_lookup.py)
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
    "af",
    "da",
    "de",
    "dei",
    "del",
    "della",
    "dem",
    "der",
    "des",
    "di",
    "du",
    "ibn",
    "il",
    "la",
    "le",
    "les",
    "van",
    "vom",
    "von",
    "zu",
    "zum",
    "zur",
    "v",
    "v.",
    "comte",
    "conte",
    "duc",
    "d",
    "al",
    "al-din",
    "al-husayn",
    "af",
    "an",
    "e",
    "in",
    "mit",
    "of",
    "und",
    "d.",
    "geb.",
    "jr.",
    "jun.",
    "med.",
    "od.",
    "phil.",
    "sen.",
    "biblische",
    "die",
    "eisernen",
    "historisch-philologische",
    "ihre",
    "kurmärkische",
    "mathematische",
    "mittlere",
    "philosophisch-historische",
    "philosophische",
    "physikalisch-mathematische",
    "physikalische",
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
# Consensus  (same logic as gender_guesser_lookup.py)
# ---------------------------------------------------------------------------

PRIORITY = [
    "no_name",
    "unknown",
    "andy",
    "mostly_male",
    "mostly_female",
    "male",
    "female",
]
PRIORITY_RANK = {v: i for i, v in enumerate(PRIORITY)}
MALE_SET = {"male", "mostly_male"}
FEMALE_SET = {"female", "mostly_female"}


def consensus(results: list[str]) -> str:
    if not results:
        return "no_name"
    definite = {r for r in results if r in MALE_SET | FEMALE_SET}
    male_votes = definite & MALE_SET
    female_votes = definite & FEMALE_SET
    if male_votes and female_votes:
        return "conflict"
    return max(results, key=lambda r: PRIORITY_RANK.get(r, 0))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("hivoto gender lookup")
    print("=" * 50)

    print(f"Loading hivoto data from {HIVOTO_CSV} …")
    hivoto = pd.read_csv(HIVOTO_CSV, sep=";", dtype=str)
    print(f"  {len(hivoto):,} entries")

    print("Building lookup index …")
    index = build_index(hivoto)
    print(f"  {len(index):,} unique keys indexed")

    persons = pd.read_csv(INPUT_CSV, dtype=str)
    print(f"Input: {len(persons):,} persons from {INPUT_CSV}")

    rows = []
    for _, person in persons.iterrows():
        xml_id = person["xml_id"]
        forename = person.get("forename", "")

        tokens = usable_tokens(forename)

        if not tokens:
            rows.append(
                {
                    "xml_id": xml_id,
                    "forename": forename,
                    "hv_tokens": "",
                    "hv_results": "",
                    "hv_certainty": "",
                    "hv_gender": "no_name",
                }
            )
            continue

        results = []
        certainties = []
        for t in tokens:
            key = t.lower().rstrip(".,;:)\"'")
            if key in index:
                g, c = index[key]
            else:
                g, c = "unknown", ""
            results.append(g)
            certainties.append(c)

        rows.append(
            {
                "xml_id": xml_id,
                "forename": forename,
                "hv_tokens": "|".join(tokens),
                "hv_results": "|".join(results),
                "hv_certainty": "|".join(certainties),
                "hv_gender": consensus(results),
            }
        )

    result = pd.DataFrame(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(result):,} rows → {OUTPUT_CSV}")

    print("\nGender distribution:")
    counts = result["hv_gender"].value_counts()
    for label, n in counts.items():
        print(f"  {label:<16} {n:>6,}  ({n / len(result) * 100:.1f}%)")

    multi = result[result["hv_tokens"].str.contains(r"\|", na=False)]
    print(f"\nPersons with multiple tokens checked: {len(multi):,}")


if __name__ == "__main__":
    main()
