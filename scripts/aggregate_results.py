"""
Aggregate all gender classification results into a single summary table.

Reads all per-method result CSVs, merges them on xml_id alongside the
input person register, and computes:

  - Canonical gender label per method  (male / female / institution / unknown)
  - Numeric confidence per method      (0.0 – 1.0 where derivable)
  - Per-row majority label across methods
  - Inter-annotator agreement fraction (IAA): fraction of answering methods
    that agree on the majority label
  - Certainty tier (cert):
      high    – IAA ≥ 0.75  and  at least 2 methods answered
      low     – IAA ≥ 0.50  and  at least 2 methods answered
      unknown – IAA < 0.50  or   fewer than 2 methods answered

Output: data/output/gender_summary.csv

Run from project root:
    python scripts/aggregate_results.py
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

RESULTS_DIR = Path("data/results")
INPUT_CSV = Path("data/input/schleiermacher_persons.csv")
OUTPUT_DIR = Path("data/output")
OUTPUT_CSV = OUTPUT_DIR / "gender_summary.csv"

# ---------------------------------------------------------------------------
# Parenthetical qualifier gender (rule-based, derived from name field)
# ---------------------------------------------------------------------------

_PAREN_PAT = re.compile(r"\(([^)]+)\)", re.IGNORECASE)

# Relationship keywords that unambiguously signal gender / group
_PAREN_FEMALE: frozenset[str] = frozenset(
    {
        "frau",
        "tochter",
        "töchter",
        "mutter",
        "schwester",
        "schwestern",
        "fräulein",
        "mädchen",
        "witwe",
        "enkelin",
        "nichte",
        "großmutter",
        "stiefmutter",
    }
)
_PAREN_MALE: frozenset[str] = frozenset(
    {
        "mann",
        "sohn",
        "söhne",
        "vater",
        "bruder",
        "brüder",
        "onkel",
        "enkel",
        "neffe",
        "großvater",
        "herr",
        "stiefvater",
    }
)
# Family-group keywords: entry is a person (or persons) but gender cannot be
# assigned to the group as a whole → pqg returns "unknown".
_PAREN_GROUP_FAMILY: frozenset[str] = frozenset(
    {
        "familie",
        "kinder",
        "kind",
        "geschwister",
        "stiefgeschwister",
        "eltern",
        "ehepaar",
        "gebrüder",
    }
)
# Commercial/organisational keywords: entry is a corporate body → "institution".
_PAREN_GROUP_ORG: frozenset[str] = frozenset(
    {
        "weinhandlung",
        "bankier",
        "bankiers",
        "kaufleute",
        "firma",
    }
)


def _qualifier_gender(surname, forename, note=None) -> str | None:
    """
    Scan parenthetical expressions in surname/forename AND the first word(s)
    of the note field for relationship keywords.  Returns a canonical label
    or None if no qualifier found.

    Return values:
      "female" / "male"  – individual relational keyword (Frau des, Sohn des …;
                           or note starts with Nichte, Schwester, Witwe …)
      "unknown"          – family-group keyword (Familie, Kinder, Ehepaar …)
      "institution"      – commercial/org keyword (Firma, Weinhandlung …)
      None               – no qualifier matched

    For name fields: any parenthetical match is used (first-word beats any-word).
    For the note field: only the FIRST WORD is checked (prevents false matches
    on words like 'Mann' or 'Frau' buried deep in a sentence).
    """
    # -- name-field scan (parenthetical) --------------------------------------
    for text in (surname, forename):
        if not text or (isinstance(text, float)):
            continue
        for m in _PAREN_PAT.finditer(str(text)):
            content = m.group(1).strip()
            w_list = [w.rstrip(".,").lower() for w in content.split()]
            if not w_list:
                continue
            w_set = set(w_list)
            fw = w_list[0]
            # First-word match (highest confidence)
            if fw in _PAREN_FEMALE:
                return "female"
            if fw in _PAREN_MALE:
                return "male"
            if fw in _PAREN_GROUP_FAMILY:
                return "unknown"
            if fw in _PAREN_GROUP_ORG:
                return "institution"
            # Any-word match (catches 'erste Tochter des X' etc.)
            if w_set & _PAREN_FEMALE:
                return "female"
            if w_set & _PAREN_MALE:
                return "male"
            if w_set & _PAREN_GROUP_FAMILY:
                return "unknown"
            if w_set & _PAREN_GROUP_ORG:
                return "institution"
    # -- note-field scan (first word only) ------------------------------------
    if note and not (isinstance(note, float)):
        note_words = [w.rstrip(".,").lower() for w in str(note).split()]
        if note_words:
            fw = note_words[0]
            if fw in _PAREN_FEMALE:
                return "female"
            if fw in _PAREN_MALE:
                return "male"
            if fw in _PAREN_GROUP_FAMILY:
                return "unknown"
    return None


# ---------------------------------------------------------------------------
# Label normalisation
# ---------------------------------------------------------------------------

# Values that mean "method gave no answer for this person"
NO_ANSWER_LABELS: set[str] = {"no_name", "no_gnd", "nan", ""}


def normalise_gender(raw) -> str | None:
    """Map a raw method label to a canonical label, or None if no answer."""
    if raw is None:
        return None
    if isinstance(raw, float) and np.isnan(raw):
        return None
    v = str(raw).strip().lower()
    if v in NO_ANSWER_LABELS:
        return None
    if v in ("male", "mostly_male"):
        return "male"
    if v in ("female", "mostly_female"):
        return "female"
    if v in ("organisation", "institution"):
        return "institution"
    # andy, conflict, uncertain, unisex, unknown → unknown
    return "unknown"


# ---------------------------------------------------------------------------
# Confidence derivation helpers
# ---------------------------------------------------------------------------

# Map hivoto text certainty tokens to float scores
_HIVOTO_MAP: dict[str, float] = {
    "sicher": 1.0,
    "mittlere sicherheit": 0.5,
}


def _parse_hivoto_certainty(val) -> float | None:
    """Convert pipe-separated hivoto certainty text to a mean float score."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    v = str(val).strip()
    if not v:
        return None
    parts = [s.strip().lower() for s in v.split("|") if s.strip()]
    scores = [_HIVOTO_MAP.get(p, 0.25) for p in parts]
    return round(sum(scores) / len(scores), 3) if scores else None


def _parse_proba_confidence(val) -> float | None:
    """
    Pipe-separated P(female) values → scalar confidence in [0, 1].

    Confidence is defined as 2 * |mean(P_female) − 0.5|, i.e. how far the
    mean probability sits from the decision boundary.  A result of 1.0 means
    the model is maximally confident; 0.0 means it sits exactly on the fence.
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    raw = str(val).strip()
    if not raw:
        return None
    try:
        probs = [
            float(p) for p in raw.split("|") if p.strip() not in ("", "nan", "NaN")
        ]
    except ValueError:
        return None
    if not probs:
        return None
    mean_pgf = sum(probs) / len(probs)
    return round(abs(mean_pgf - 0.5) * 2, 3)


# Derived confidence for gender_guesser (no numeric confidence column)
_GG_CONFIDENCE: dict[str, float] = {
    "male": 1.0,
    "female": 1.0,
    "mostly_male": 0.75,
    "mostly_female": 0.75,
    "andy": 0.5,
    "conflict": 0.5,
    "unknown": 0.5,
}

# Derived confidence for wiki_gendersort (no numeric confidence column)
_WGS_CONFIDENCE: dict[str, float] = {
    "male": 1.0,
    "female": 1.0,
    "conflict": 0.5,
    "unisex": 0.5,
    "unknown": 0.5,
}

# Derived confidence for NQG uncertain/conflict (no separate confidence column)
_NQG_CONFIDENCE: dict[str, float] = {
    "male": 1.0,
    "female": 1.0,
    "uncertain": 0.5,
    "conflict": 0.5,
    "unknown": 0.5,
}


# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------
# Each entry describes one method result file and how to extract gender/confidence.
#
# Keys:
#   file          CSV filename (relative to RESULTS_DIR)
#   short         short identifier used for output column names
#   gender_col    column holding the raw gender label
#   conf_type     how to derive the confidence:
#                   "column"        – numeric column named by conf_source
#                   "hivoto_text"   – pipe-separated hivoto text → float
#                   "proba_pfemale" – pipe-separated P(female) values
#                   "label_map"     – look up raw label in a static dict
#                   None            – no confidence available
#   conf_source   column name (for "column" and "proba_pfemale") or
#                 dict (for "label_map")
#   optional      if True, silently skip when file doesn't exist yet

METHODS: list[dict] = [
    {
        "file": "gender_guesser_results.csv",
        "short": "gg",
        "gender_col": "gg_gender",
        "conf_type": "label_map",
        "conf_source": _GG_CONFIDENCE,
        "optional": False,
    },
    {
        "file": "gnd_gender_results.csv",
        "short": "gnd",
        "gender_col": "gnd_gender_mapped",
        "conf_type": None,  # authority lookup – treat as 1.0 when present
        "conf_source": None,
        "optional": False,
        # GND 'unknown' means the authority record exists but carries no gender
        # statement – treat as no answer rather than an affirmative unknown vote.
        "no_vote_labels": {"unknown"},
    },
    {
        "file": "hf_gender_classification_results.csv",
        "short": "hfgc",
        "gender_col": "hfgc_gender",
        "conf_type": "column",
        "conf_source": "hfgc_confidence",
        "optional": False,
    },
    {
        "file": "hf_genderize_results.csv",
        "short": "hfg",
        "gender_col": "hfg_gender",
        "conf_type": "column",
        "conf_source": "hfg_confidence",
        "optional": False,
    },
    {
        "file": "hivoto_results.csv",
        "short": "hv",
        "gender_col": "hv_gender",
        "conf_type": "hivoto_text",
        "conf_source": "hv_certainty",
        "optional": False,
    },
    {
        "file": "hivoto_xgboost_results.csv",
        "short": "xgb",
        "gender_col": "xgb_gender",
        "conf_type": "proba_pfemale",
        "conf_source": "xgb_proba",
        "optional": False,
        "enabled": False,  # experimental – set True to include in vote
    },
    {
        "file": "nqg_results.csv",
        "short": "nqg",
        "gender_col": "nqg_gender",
        "conf_type": "label_map",
        "conf_source": _NQG_CONFIDENCE,
        "optional": False,
    },
    {
        "file": "wiki_gendersort_results.csv",
        "short": "wgs",
        "gender_col": "wgs_gender",
        "conf_type": "label_map",
        "conf_source": _WGS_CONFIDENCE,
        "optional": False,
    },
    {
        "file": "llm_gender_results.csv",
        "short": "llm",
        "gender_col": "llm_gender",
        "conf_type": "column",
        "conf_source": "llm_confidence",
        "extra_cols": ["llm_cert"],  # discrete cert tier from new LLM runs
        "optional": True,  # not yet available until LLM run completes
    },
]


# ---------------------------------------------------------------------------
# Agreement and certainty helpers
# ---------------------------------------------------------------------------


def _majority_and_agreement(labels: list[str]) -> tuple[str | None, float]:
    """
    Given a list of canonical gender labels (already None-filtered),
    return (majority_label, agreement_fraction).

    Tiebreak rule: when 'unknown' ties with a substantive label
    (male / female / institution), the substantive label wins.
    'unknown' from name-lookup methods means "can't determine from name",
    not "this person's gender is unknown" — so it should never beat a
    substantive answer of equal vote count.
    """
    if not labels:
        return None, 0.0
    counts = Counter(labels)
    majority_label, majority_count = counts.most_common(1)[0]
    # If the top label is unknown, check whether a substantive label ties it
    if majority_label == "unknown":
        best_sub = max(
            ((lbl, cnt) for lbl, cnt in counts.items() if lbl != "unknown"),
            key=lambda x: x[1],
            default=(None, 0),
        )
        if best_sub[0] is not None and best_sub[1] == majority_count:
            majority_label = best_sub[0]
            majority_count = best_sub[1]
    agreement = majority_count / len(labels)
    return majority_label, round(agreement, 3)


def _cert(majority_label: str | None, agreement: float, n_answering: int) -> str:
    """
    Derive certainty tier from agreement statistics.

    high      – ≥ 2 methods answered, IAA ≥ 0.75
    low       – ≥ 2 methods answered, IAA ≥ 0.50
    contested – ≥ 2 methods answered, IAA < 0.50  (methods genuinely disagree)
    single    – LLM only, llm_cert = high  (clear signal, no corroboration)
    uncertain – LLM only, llm_cert = low or uncertain  (weak/no evidence)
    no_data   – no method produced a label at all
    """
    if n_answering == 0:
        return "no_data"
    if n_answering == 1:
        return "single"  # refined later in row_stats using llm_cert
    if agreement >= 0.75:
        return "high"
    if agreement >= 0.50:
        return "low"
    return "contested"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Load person register (name columns) ────────────────────────────────
    persons = pd.read_csv(
        INPUT_CSV,
        dtype=str,
        usecols=["xml_id", "surname", "forename", "note"],
    )
    persons["name"] = (
        persons["surname"].fillna("").str.strip()
        + ", "
        + persons["forename"].fillna("").str.strip()
    ).str.strip(", ")
    # Normalise note: collapse line-breaks and repeated whitespace
    persons["note"] = (
        persons["note"]
        .str.replace(r"[\r\n]+", " ", regex=True)
        .str.replace(r"\s{2,}", " ", regex=True)
        .str.strip()
    )
    base = persons[["xml_id", "name", "note"]].copy()
    loaded_methods: list[dict] = []

    # ── 1b. Parenthetical qualifier gender (rule-based pseudo-method) ─────────
    persons["pqg_gender"] = persons.apply(
        lambda r: _qualifier_gender(r["surname"], r["forename"], r.get("note")), axis=1
    )
    persons["pqg_confidence"] = persons["pqg_gender"].apply(
        lambda v: 1.0 if v is not None else None
    )
    base = base.merge(
        persons[["xml_id", "pqg_gender", "pqg_confidence"]], on="xml_id", how="left"
    )
    loaded_methods.append(
        {"short": "pqg", "gender_col": "pqg_gender", "confidence_col": "pqg_confidence"}
    )
    n_pqg = persons["pqg_gender"].notna().sum()
    print(f"  [ok]   parenthetical qualifier gender ({n_pqg:,} rows matched)")

    # ── 2. Load and merge each method ─────────────────────────────────────────
    for m in METHODS:
        if not m.get("enabled", True):
            print(f"  [skip] {m['file']} (disabled)")
            continue
        path = RESULTS_DIR / m["file"]
        if not path.exists():
            if m.get("optional"):
                print(f"  [skip] {m['file']} not found (optional)")
                continue
            print(f"  [WARN] {m['file']} not found – skipping")
            continue

        # Columns to load: xml_id + gender + optional confidence source + extra_cols
        use_cols = ["xml_id", m["gender_col"]]
        if m["conf_type"] in ("column", "hivoto_text", "proba_pfemale"):
            use_cols.append(m["conf_source"])
        use_cols.extend(m.get("extra_cols", []))

        df = pd.read_csv(path, dtype=str, usecols=lambda c: c in use_cols)

        short = m["short"]
        gender_out = f"{short}_gender"
        confidence_out = f"{short}_confidence"

        # Normalise gender label
        df[gender_out] = df[m["gender_col"]].apply(normalise_gender)

        # Treat method-specific no-vote labels as no answer
        no_vote = m.get("no_vote_labels", set())
        if no_vote:
            df.loc[df[gender_out].isin(no_vote), gender_out] = None

        # Derive confidence
        if m["conf_type"] == "column":
            df[confidence_out] = pd.to_numeric(df[m["conf_source"]], errors="coerce")
        elif m["conf_type"] == "hivoto_text":
            df[confidence_out] = df[m["conf_source"]].apply(_parse_hivoto_certainty)
        elif m["conf_type"] == "proba_pfemale":
            df[confidence_out] = df[m["conf_source"]].apply(_parse_proba_confidence)
        elif m["conf_type"] == "label_map":
            raw_col = m["gender_col"]
            label_map: dict = m["conf_source"]
            df[confidence_out] = df[raw_col].apply(
                lambda v: label_map.get(str(v).strip().lower()) if pd.notna(v) else None
            )
            # No confidence for no_name rows
            df.loc[df[gender_out].isna(), confidence_out] = None
        else:
            # GND-style: 1.0 when gender is present, None otherwise
            df[confidence_out] = df[gender_out].apply(
                lambda v: 1.0 if v is not None else None
            )

        # Round confidence to 3 d.p.
        df[confidence_out] = pd.to_numeric(df[confidence_out], errors="coerce").round(3)

        keep = ["xml_id", gender_out, confidence_out]
        # Also carry through any declared extra columns (e.g. llm_cert)
        for col in m.get("extra_cols", []):
            if col in df.columns:
                keep.append(col)
        base = base.merge(df[keep], on="xml_id", how="left")
        loaded_methods.append(
            {"short": short, "gender_col": gender_out, "confidence_col": confidence_out}
        )
        print(f"  [ok]   {m['file']}")

    # ── 3. Per-row agreement and certainty ────────────────────────────────────
    # All method gender columns excluding pqg and gnd (used separately as overrides)
    gender_cols = [
        m["gender_col"]
        for m in loaded_methods
        if m["gender_col"] not in ("pqg_gender", "gnd_gender")
    ]

    def row_stats(row):
        # Override priority (highest first):
        #   1. pqg  – deterministic structural rule (e.g. "Frau des X")
        #   2. gnd  – authoritative external registry
        #   3. vote – majority of remaining statistical methods
        pqg = row["pqg_gender"] if pd.notna(row.get("pqg_gender")) else None
        gnd = row["gnd_gender"] if pd.notna(row.get("gnd_gender")) else None

        labels = [
            row[c] for c in gender_cols if pd.notna(row[c]) and row[c] is not None
        ]
        majority, agreement = _majority_and_agreement(labels)
        cert = _cert(majority, agreement, len(labels))

        if pqg is not None:
            maj_out = pqg
            # pqg is a deterministic rule – always high confidence.
            # Record IAA as fraction of other methods that agree (informational),
            # but do not let their structural blindness to qualifiers downgrade cert.
            all_labels = labels + ([gnd] if gnd else [])
            pqg_agree = sum(1 for l in all_labels if l == pqg)
            pqg_iaa = round(pqg_agree / len(all_labels), 3) if all_labels else 1.0
            cert = "high"
            n_total = len(all_labels) + 1
            iaa_out = pqg_iaa
        elif gnd is not None:
            maj_out = gnd
            # GND is authoritative – always high confidence.
            # Record how many statistical methods agree (informational).
            gnd_agree = sum(1 for l in labels if l == gnd)
            gnd_iaa = round(gnd_agree / len(labels), 3) if labels else 1.0
            cert = "high"
            n_total = len(labels) + 1
            iaa_out = gnd_iaa
        elif len(labels) == 0:
            maj_out = "no_data"
            n_total = 0
            iaa_out = None
        elif majority is None:
            maj_out = "unknown"
            n_total = len(labels)
            iaa_out = agreement if labels else None
        else:
            maj_out = majority
            n_total = len(labels)
            iaa_out = agreement if labels else None

        return pd.Series(
            {
                "predicted_gender": maj_out,
                "n_methods_answered": n_total,
                "iaa": iaa_out,
                "cert": cert,
            }
        )

    stats = base.apply(row_stats, axis=1)
    base = pd.concat([base, stats], axis=1)

    # ── 3b. Refine cert=single using llm_cert (if available) ─────────────────
    # llm_cert is the LLM's own discrete confidence tier (high/low/uncertain).
    # For rows where the LLM was the only method, use it to subdivide 'single'.
    if "llm_cert" in base.columns:
        single_mask = base["cert"] == "single"
        base.loc[single_mask & (base["llm_cert"] == "high"), "cert"] = "single"
        base.loc[single_mask & (base["llm_cert"] == "low"), "cert"] = "uncertain"
        base.loc[single_mask & (base["llm_cert"] == "uncertain"), "cert"] = "uncertain"

    # ── 4. Order columns: xml_id, name, [method gender+conf pairs], stats ────
    meta_cols = ["xml_id", "name", "note"]
    method_pairs = []
    for m in loaded_methods:
        method_pairs += [m["gender_col"], m["confidence_col"]]
    # Include llm_cert right after llm_confidence if present
    if "llm_cert" in base.columns:
        llm_conf_idx = method_pairs.index("llm_confidence") + 1
        method_pairs.insert(llm_conf_idx, "llm_cert")
    summary_cols = ["predicted_gender", "n_methods_answered", "iaa", "cert"]

    final_cols = meta_cols + method_pairs + summary_cols
    result = base[final_cols]

    # ── 5. Write output ───────────────────────────────────────────────────────
    result.to_csv(OUTPUT_CSV, index=False)
    print(
        f"\nWrote {len(result):,} rows × {len(result.columns)} columns → {OUTPUT_CSV}"
    )

    # Brief stats
    print("\nCert distribution:")
    print(result["cert"].value_counts().to_string())
    print("\nPredicted gender distribution:")
    print(result["predicted_gender"].value_counts().to_string())


if __name__ == "__main__":
    main()
