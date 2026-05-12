"""
Wiki-Gendersort lookup for Schleiermacher persons.

Uses the Wiki-Gendersort database (694 376 first-name→gender mappings
derived from Wikipedia) described in:

    Nicolas Bérubé & Vincent Larivière (2020).
    "Wiki-Gendersort: Automatic gender detection using first names in
    Wikipedia." https://osf.io/preprints/socarxiv/ezw7p/

For each person in the input CSV the forename field is split into tokens
(same rules as the other lookup scripts) and each token is looked up in
the NamesOut.txt flat-file database.  The nameclean() function from the
original code is applied to each token before lookup, handling hyphens,
diacritics, initials, and other edge cases.

Label mapping (Wiki-Gendersort → project):
    M   → male
    F   → female
    UNI → unisex
    INI → no_name   (initials only)
    UNK → unknown

Consensus across tokens follows the same logic as the other classifiers:
    male / female  >  unisex  >  unknown  >  no_name
    conflicting male + female tokens → conflict

Output columns:
    xml_id          – Schleiermacher register ID (primary/foreign key)
    forename        – original forename string
    wgs_tokens      – pipe-separated tokens actually checked
    wgs_matched     – pipe-separated name that matched in the DB (via nameclean)
    wgs_raw         – pipe-separated raw Wiki-Gendersort label (M/F/UNI/INI/UNK)
    wgs_results     – pipe-separated mapped label per token
    wgs_gender      – consensus gender across all tokens

Usage:
    python methods/wiki_gendersort.py
"""

import re
import string
from pathlib import Path

import pandas as pd
from unidecode import unidecode

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

INPUT_CSV = Path("data/input/schleiermacher_persons.csv")
OUTPUT_DIR = Path("data/results")
OUTPUT_CSV = OUTPUT_DIR / "wiki_gendersort_results.csv"
NAMES_DB = Path("data/raw/wiki_gendersort/NamesOut.txt")

# ---------------------------------------------------------------------------
# Label mapping:  Wiki-Gendersort native → project convention
# ---------------------------------------------------------------------------

LABEL_MAP = {
    "M": "male",
    "F": "female",
    "UNI": "unisex",
    "INI": "no_name",
    "UNK": "unknown",
}

# ---------------------------------------------------------------------------
# Consensus  (mirrors the other lookup scripts)
# ---------------------------------------------------------------------------

PRIORITY = ["no_name", "unknown", "unisex", "male", "female"]
PRIORITY_RANK = {v: i for i, v in enumerate(PRIORITY)}
MALE_SET = {"male"}
FEMALE_SET = {"female"}


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
# Token filtering  (identical to the other lookup scripts)
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
# nameclean()  — adapted from the original Wiki-Gendersort code
# ---------------------------------------------------------------------------


def _countalpha(name: str) -> int:
    """Count alphabetical characters in a string."""
    chars = string.ascii_lowercase + string.ascii_uppercase
    return sum(1 for c in name if unidecode(c) in chars)


def _countvowel(name: str) -> int:
    """Count vowels in a string."""
    return sum(1 for c in name if unidecode(c) in "aeiouyAEIOUY")


def nameclean(first_name: str) -> list[str]:
    """Clean a first name and return candidate lookup strings (priority order).

    This is the original nameclean() from Wiki-Gendersort, adapted for
    single-token inputs (the forename tokens produced by usable_tokens).
    """
    name = first_name

    # Move text in quotation marks or parentheses to end
    while True:
        left_i = right_i = -1
        if '"' in name and name.find('"') != name.rfind('"'):
            left_i = name.find('"')
            right_i = left_i + 1 + name[left_i + 1 :].find('"')
        if "(" in name and ")" in name and name.find("(") < name.rfind(")"):
            left_i = name.find("(")
            right_i = name.rfind(")")
        if left_i != -1 and right_i != -1:
            name = (
                name[:left_i]
                + " "
                + name[right_i + 1 :]
                + " "
                + name[left_i + 1 : right_i]
            )
        else:
            break

    # Split on non-letter/non-period/non-hyphen characters
    namf = ""
    for ch in name:
        if _countalpha(ch) >= 1 or ch in {".", "-"}:
            namf += ch
        else:
            namf += " "
    namf = [n for n in namf.split() if _countalpha(n) != 0]

    # Handle periods and fused strings
    j = 0
    while j < len(namf):
        if (
            len(namf[j]) >= 4
            and namf[j][-1] == "."
            and namf[j][-2].isupper()
            and namf[j][-3].islower()
        ):
            namf.insert(j + 1, namf[j][-2:])
            namf[j] = namf[j][:-2]
        if namf[j][-1] == "." and 4 > len(namf[j]) > 1:
            namf.append(namf[j][:-1])
            del namf[j]
            j -= 1
        j += 1

    # Split remaining periods
    j = 0
    while j < len(namf):
        if "." in namf[j]:
            namsplit = namf[j].split(".")[::-1]
            for n in namsplit:
                namf.insert(j + 1, n)
            del namf[j]
            j += len(namsplit) - 1
        j += 1

    # Hyphenated names → keep compound + individual parts
    j = 0
    while j < len(namf):
        while namf[j] and namf[j][0] == "-":
            namf[j] = namf[j][1:]
        while namf[j] and namf[j][-1] == "-":
            namf[j] = namf[j][:-1]
        if "-" in namf[j]:
            for n in namf[j].split("-")[::-1]:
                namf.insert(j + 1, n)
        j += 1

    # Filter initials, normalise case, add unidecoded variants
    namf2 = []
    for nam in namf:
        if _countalpha(nam) > 1 and _countvowel(nam) > 0:
            if len(nam) <= 1:
                n = nam.upper()
            else:
                n = nam[0].upper() + nam[1:].lower()
            namf2.append(n)
            un = unidecode(n)
            if n != un:
                namf2.append(un)
    return namf2


# ---------------------------------------------------------------------------
# Wiki-Gendersort database loader
# ---------------------------------------------------------------------------


class WikiGendersort:
    """Lightweight wrapper around the NamesOut.txt lookup table."""

    def __init__(self, db_path: str | Path = NAMES_DB):
        self.db_path = Path(db_path)
        self.names_key: dict[str, str] = {}
        with open(self.db_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2:
                    raw_name = "\t".join(parts[:-1]).upper()
                    if raw_name:
                        raw_name = raw_name[0] + raw_name[1:].lower()
                    gender = parts[-1]
                    self.names_key[raw_name] = gender
        print(f"  Wiki-Gendersort DB loaded: {len(self.names_key):,} entries")

    def assign(self, name: str) -> tuple[str, str | None]:
        """Assign a raw Wiki-Gendersort label to a first-name token.

        Returns (raw_label, matched_name).
        raw_label is one of M, F, UNI, INI, UNK.
        matched_name is the DB key that produced the result, or None.
        """
        namelist = nameclean(name)
        gend = "UNK"
        matched = None

        for nam in namelist:
            if nam in self.names_key:
                new_gend = self.names_key[nam]
                if new_gend != "UNK":
                    if matched is None:
                        matched = nam
                    gend = new_gend
            if gend not in {"UNK", "UNI"}:
                matched = nam
                break

        if not namelist and name:
            gend = "INI"
        if name.upper() == "NULL":
            gend = "UNK"

        return gend, matched


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("Wiki-Gendersort lookup")
    print("=" * 50)

    wg = WikiGendersort(NAMES_DB)

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
                    "wgs_tokens": "",
                    "wgs_matched": "",
                    "wgs_raw": "",
                    "wgs_results": "",
                    "wgs_gender": "no_name",
                }
            )
            continue

        raw_labels = []
        mapped_labels = []
        matched_names = []
        for t in tokens:
            raw, matched = wg.assign(t)
            raw_labels.append(raw)
            mapped_labels.append(LABEL_MAP.get(raw, "unknown"))
            matched_names.append(matched or "")

        rows.append(
            {
                "xml_id": xml_id,
                "forename": forename,
                "wgs_tokens": "|".join(tokens),
                "wgs_matched": "|".join(matched_names),
                "wgs_raw": "|".join(raw_labels),
                "wgs_results": "|".join(mapped_labels),
                "wgs_gender": consensus(mapped_labels),
            }
        )

    result = pd.DataFrame(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(result):,} rows → {OUTPUT_CSV}")

    print("\nGender distribution:")
    counts = result["wgs_gender"].value_counts()
    for label, n in counts.items():
        print(f"  {label:<16} {n:>6,}  ({n / len(result) * 100:.1f}%)")

    multi = result[result["wgs_tokens"].str.contains(r"\|", na=False)]
    print(f"\nPersons with multiple tokens checked: {len(multi):,}")


if __name__ == "__main__":
    main()
