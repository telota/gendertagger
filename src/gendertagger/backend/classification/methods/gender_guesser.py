"""
Gender-guesser lookup for Schleiermacher persons.

For each person in the input CSV the forename field is split on whitespace
into individual tokens and each token is checked with gender_guesser.
Bracketed/abbreviated tokens (e.g. "(Frau)", "von", "L.") are skipped.

Output columns:
    xml_id              – Schleiermacher register ID (primary/foreign key)
    forename            – original forename string from input CSV
    gg_tokens           – pipe-separated list of tokens actually checked
    gg_results          – pipe-separated gender result per token
    gg_gender           – consensus gender (see PRIORITY below)

Consensus priority (highest → lowest):
    female / male  >  mostly_female / mostly_male  >  andy  >  unknown  >  no_name

When tokens produce conflicting definite results (one male, one female)
the consensus is "conflict".

Usage:
    python src/gender_guesser_lookup.py
"""

import re
from pathlib import Path

import pandas as pd
import gender_guesser.detector as gender_lib

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

INPUT_CSV = Path("data/input/schleiermacher_persons.csv")
OUTPUT_DIR = Path("data/results")
OUTPUT_CSV = OUTPUT_DIR / "gender_guesser_results.csv"

# ---------------------------------------------------------------------------
# Consensus helpers
# ---------------------------------------------------------------------------

# Higher index = stronger signal
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
    """Derive a single gender label from a list of per-token results."""
    if not results:
        return "no_name"

    definite = {r for r in results if r in MALE_SET | FEMALE_SET}
    male_votes = definite & MALE_SET
    female_votes = definite & FEMALE_SET

    if male_votes and female_votes:
        return "conflict"

    # Pick the highest-priority result across all tokens
    return max(results, key=lambda r: PRIORITY_RANK.get(r, 0))


# ---------------------------------------------------------------------------
# Token filtering
# ---------------------------------------------------------------------------

# Skip tokens that are clearly not personal first names
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

# Lowercase particles, prepositions, abbreviations and noise words –
# checked against the token lowercased and stripped of trailing punctuation.
_PARTICLES = {
    # Noble/name particles (German, Dutch, French, Italian, Spanish, Arabic, Scandinavian)
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
    # French titles / particles
    "comte",
    "conte",
    "duc",
    "d",
    # Arabic
    "al",
    "al-din",
    "al-husayn",
    # Prepositions / conjunctions
    "af",
    "an",
    "e",
    "in",
    "mit",
    "of",
    "und",
    # Abbreviations / suffixes
    "d.",
    "geb.",
    "jr.",
    "jun.",
    "med.",
    "od.",
    "phil.",
    "sen.",
    # Descriptive noise words that appear in the register
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
        # Normalise for particle check: lowercase, strip trailing punctuation/brackets
        normalised = t.lower().rstrip(".,;:)\"'")
        if normalised in _PARTICLES:
            continue
        result.append(t)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("Gender-guesser lookup")
    print("=" * 50)

    persons = pd.read_csv(INPUT_CSV, dtype=str)
    print(f"Input: {len(persons):,} persons from {INPUT_CSV}")

    detector = gender_lib.Detector(case_sensitive=False)

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
                    "gg_tokens": "",
                    "gg_results": "",
                    "gg_gender": "no_name",
                }
            )
            continue

        results = [detector.get_gender(t) for t in tokens]
        rows.append(
            {
                "xml_id": xml_id,
                "forename": forename,
                "gg_tokens": "|".join(tokens),
                "gg_results": "|".join(results),
                "gg_gender": consensus(results),
            }
        )

    result = pd.DataFrame(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved {len(result):,} rows → {OUTPUT_CSV}")

    print("\nGender distribution:")
    counts = result["gg_gender"].value_counts()
    for label, n in counts.items():
        print(f"  {label:<16} {n:>6,}  ({n / len(result) * 100:.1f}%)")

    multi = result[result["gg_tokens"].str.contains(r"\|", na=False)]
    print(f"\nPersons with multiple tokens checked: {len(multi):,}")


if __name__ == "__main__":
    main()
