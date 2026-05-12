"""
HuggingFace 'padmajabfrl/Gender-Classification' lookup for Schleiermacher persons.

For each person in the input CSV the forename field is split into tokens
(same rules as gender_guesser_lookup.py / nqg_lookup.py / hf_genderize_lookup.py)
and each token is classified individually by the DistilBERT-based model.

The model returns logits for two classes:
  0 → male
  1 → female
Confidence is taken from the softmax probability of the predicted class.
Tokens that raise an exception are recorded as 'unknown' with confidence 0.

Consensus across tokens: same as other classifiers:
  male / female  >  unknown  >  no_name
  conflicting male + female tokens → conflict

Output columns:
  xml_id           – Schleiermacher register ID (primary/foreign key)
  forename         – original forename string
  hfgc_tokens      – pipe-separated tokens actually submitted to the model
  hfgc_results     – pipe-separated categorical label per token (male/female/unknown)
  hfgc_confidence  – pipe-separated softmax confidence per token
  hfgc_gender      – consensus gender across all tokens

Usage:
    python methods/hf_gender_classification.py
"""

import re
from pathlib import Path

import pandas as pd
import torch
from tqdm import tqdm
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

INPUT_CSV = Path("data/input/schleiermacher_persons.csv")
OUTPUT_DIR = Path("data/results")
OUTPUT_CSV = OUTPUT_DIR / "hf_gender_classification_results.csv"

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

MODEL_NAME = "padmajabfrl/Gender-Classification"

# Label mapping confirmed from HuggingFaceGenderClassifier in gender.py
LABEL_MAP = {0: "male", 1: "female"}

# ---------------------------------------------------------------------------
# Consensus  (mirrors the other lookup scripts)
# ---------------------------------------------------------------------------

PRIORITY = ["no_name", "unknown", "male", "female"]
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
# Per-token prediction
# ---------------------------------------------------------------------------


def predict_token(
    token: str,
    model: AutoModelForSequenceClassification,
    tokenizer: AutoTokenizer,
) -> tuple[str, float]:
    """Run the model on a single token.  Returns (label, confidence)."""
    try:
        inputs = tokenizer(token, return_tensors="pt")
        with torch.no_grad():
            logits = model(**inputs).logits
            predicted_idx = logits.argmax(dim=-1).item()
            probs = torch.nn.functional.softmax(logits, dim=-1)[0]
            confidence = probs[predicted_idx].item()
        label = LABEL_MAP.get(predicted_idx, "unknown")
        return label, round(confidence, 4)
    except Exception:
        return "unknown", 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print(
        "HuggingFace Gender-Classification lookup  (padmajabfrl/Gender-Classification)"
    )
    print("=" * 75)

    print(f"Loading model '{MODEL_NAME}' …", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    model.eval()
    print("Model loaded.\n")

    persons = pd.read_csv(INPUT_CSV, dtype=str)
    print(f"Input: {len(persons):,} persons from {INPUT_CSV}")

    rows = []
    for _, person in tqdm(persons.iterrows(), total=len(persons), desc="Classifying"):
        xml_id = person["xml_id"]
        forename = person.get("forename", "")

        tokens = usable_tokens(forename)

        if not tokens:
            rows.append(
                {
                    "xml_id": xml_id,
                    "forename": forename,
                    "hfgc_tokens": "",
                    "hfgc_results": "",
                    "hfgc_confidence": "",
                    "hfgc_gender": "no_name",
                }
            )
            continue

        results = []
        confidences = []
        for t in tokens:
            label, conf = predict_token(t, model, tokenizer)
            results.append(label)
            confidences.append(str(conf))

        rows.append(
            {
                "xml_id": xml_id,
                "forename": forename,
                "hfgc_tokens": "|".join(tokens),
                "hfgc_results": "|".join(results),
                "hfgc_confidence": "|".join(confidences),
                "hfgc_gender": consensus(results),
            }
        )

    result = pd.DataFrame(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved {len(result):,} rows → {OUTPUT_CSV}")

    print("\nGender distribution:")
    counts = result["hfgc_gender"].value_counts()
    for label, n in counts.items():
        print(f"  {label:<16} {n:>6,}  ({n / len(result) * 100:.1f}%)")

    multi = result[result["hfgc_tokens"].str.contains(r"\|", na=False)]
    print(f"\nPersons with multiple tokens checked: {len(multi):,}")


if __name__ == "__main__":
    main()
