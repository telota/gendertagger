"""
Gender classifier trained on HIVOTO data using XGBoost + character n-grams.

Training data
-------------
hivoto v1.0.0 (2026-02-09) – full written-out forms (Abkürzungsstatus=ausgeschrieben)
with unambiguous gender labels:
    männlich (Q18) / männlich, vorwiegend (*)   → 0  (male)
    weiblich (Q17) / weiblich, vorwiegend (*)   → 1  (female)
Rows labelled uneindeutig / unsicher / mehrere are dropped from training
but can still be predicted.

Feature extraction
------------------
TF-IDF over character n-grams (n=2..5) on the Klassifizierte_Originalschreibung
column (lowercased, stripped).  char_wb mode pads each token with word boundaries,
which is essential for capturing prefix / suffix patterns.

Prediction (inference on persons)
----------------------------------
Identical token-splitting / filtering as hivoto.py.
For each token the model returns P(female).  Tokens matched in the HIVOTO lookup
index keep their deterministic label; unknown tokens are classified by the model.
Consensus across multi-token forenames:
  - If any token is a hard lookup hit → majority vote over hits
  - Otherwise → average P(female) across model predictions, threshold 0.5

Output columns (matches hivoto_results.csv convention, prefix xgb_)
  xml_id          – Schleiermacher register ID
  forename        – original forename string
  xgb_tokens      – pipe-separated tokens actually checked
  xgb_results     – pipe-separated per-token gender label
  xgb_proba       – pipe-separated P(female) per token (2 d.p.)
  xgb_gender      – consensus gender across all tokens

Usage
-----
    cd /mnt/data/userfiles/westphal/schleiermacher/gender/gender
    python methods/hivoto_xgboost.py

Optional flags passed as env vars:
    RETRAIN=1   – force retraining even if a saved model already exists
"""

from __future__ import annotations

import os
import re
import joblib
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from xgboost import XGBClassifier

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = BASE_DIR / "data/input/schleiermacher_persons.csv"
HIVOTO_CSV = BASE_DIR / "data/raw/HIVOTO/2026-02-09_hivoto_vs_1_0_0.csv"
OUTPUT_DIR = BASE_DIR / "data/results"
OUTPUT_CSV = OUTPUT_DIR / "hivoto_xgboost_results.csv"
MODEL_DIR = BASE_DIR / "output" / "models"
VECTORIZER_PATH = MODEL_DIR / "hivoto_xgb_vectorizer.joblib"
MODEL_PATH = MODEL_DIR / "hivoto_xgb_model.joblib"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Gender mapping for hivoto labels
# ---------------------------------------------------------------------------

_LABEL_MAP = {
    # clear female
    "weiblich (Q17)": "female",
    "weiblich, vorwiegend (Q1381599)": "female",
    "weiblich, vorwiegend (nur deutsche Vornamen) (Q1381598)": "female",
    # clear male
    "männlich (Q18)": "male",
    "männlich, vorwiegend (Q1381598)": "male",
    "männlich, vorwiegend (nur deutsche Vornamen) (Q1381599)": "male",
    # ambiguous – kept for lookup, dropped from training
    "uneindeutig (Q369534)": "andy",
    "unsicher": "unknown",
    "mehrere, gemischt": "unknown",
}

BINARY_CLASSES = {"male": 0, "female": 1}


def map_gender_label(raw: str) -> str:
    return _LABEL_MAP.get(str(raw).strip(), "unknown")


# ---------------------------------------------------------------------------
# Load & prepare HIVOTO training data
# ---------------------------------------------------------------------------


def load_hivoto(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", low_memory=False)
    df["gender"] = df["Namensgeschlecht"].apply(map_gender_label)
    df["name_clean"] = (
        df["Klassifizierte_Originalschreibung"]
        .astype(str)
        .str.strip()
        .str.rstrip(".")
        .str.lower()
    )
    return df


def build_training_data(hivoto: pd.DataFrame) -> tuple[list[str], list[int]]:
    """
    Filter to:
      - full written-out names (ausgeschrieben)
      - clear binary gender labels (male / female)
      - non-empty name field

    Returns (names, labels) as parallel lists.
    """
    mask = (
        (hivoto["Abkürzungsstatus"] == "ausgeschrieben")
        & (hivoto["gender"].isin(BINARY_CLASSES))
        & (hivoto["name_clean"].str.len() > 0)
    )
    subset = hivoto[mask].copy()
    names = subset["name_clean"].tolist()
    labels = [BINARY_CLASSES[g] for g in subset["gender"]]
    print(
        f"  Training rows: {len(names)}  "
        f"(male={sum(l==0 for l in labels)}, female={sum(l==1 for l in labels)})"
    )
    return names, labels


# ---------------------------------------------------------------------------
# Build deterministic lookup index (same as hivoto.py, used for known names)
# ---------------------------------------------------------------------------


def build_lookup_index(hivoto: pd.DataFrame) -> dict[str, str]:
    """
    token → consensus gender label (male/female/andy/unknown)
    Uses majority vote; ties broken by priority rank.
    """
    PRIORITY = ["unknown", "andy", "mostly_male", "mostly_female", "male", "female"]
    PRIORITY_RANK = {v: i for i, v in enumerate(PRIORITY)}

    records: dict[str, list[str]] = {}
    for _, row in hivoto.iterrows():
        orig = str(row["Originalschreibung"]).strip().lower()
        klas = str(row["Klassifizierte_Originalschreibung"]).strip().lower().rstrip(".")
        gender = map_gender_label(row["Namensgeschlecht"])
        # map mostly_* back if needed
        if gender == "female":
            g = "female"
        elif gender == "male":
            g = "male"
        elif "vorwiegend" in str(row["Namensgeschlecht"]):
            g = (
                "mostly_male"
                if "männlich" in str(row["Namensgeschlecht"])
                else "mostly_female"
            )
        elif "uneindeutig" in str(row["Namensgeschlecht"]):
            g = "andy"
        else:
            g = "unknown"

        for key in {orig, klas}:
            if key:
                records.setdefault(key, []).append(g)

    index = {}
    for key, genders in records.items():
        counts = Counter(genders)
        winner = max(counts, key=lambda g: (counts[g], PRIORITY_RANK.get(g, 0)))
        index[key] = winner
    return index


# ---------------------------------------------------------------------------
# Train / load model
# ---------------------------------------------------------------------------


def train_model(
    names: list[str], labels: list[int]
) -> tuple[TfidfVectorizer, XGBClassifier]:
    print("  Fitting TF-IDF vectorizer (char_wb, n=2..5) …")
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 5),
        min_df=3,
        sublinear_tf=True,
        max_features=25_000,
        dtype=np.float32,
    )
    X = vectorizer.fit_transform(names)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, labels, test_size=0.15, random_state=42, stratify=labels
    )
    print(f"  Train: {X_tr.shape[0]}, Test: {X_te.shape[0]}, Features: {X.shape[1]}")

    scale = sum(l == 0 for l in y_tr) / max(sum(l == 1 for l in y_tr), 1)
    print(f"  scale_pos_weight = {scale:.2f}")

    model = XGBClassifier(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.7,
        scale_pos_weight=scale,
        eval_metric="logloss",
        early_stopping_rounds=25,
        tree_method="hist",
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=50)

    y_pred = model.predict(X_te)
    print(classification_report(y_te, y_pred, target_names=["male", "female"]))
    return vectorizer, model


def get_model(hivoto: pd.DataFrame, force_retrain: bool = False):
    if not force_retrain and VECTORIZER_PATH.exists() and MODEL_PATH.exists():
        print("  Loading saved model …")
        vectorizer = joblib.load(VECTORIZER_PATH)
        model = joblib.load(MODEL_PATH)
        return vectorizer, model

    print("  Building training data …")
    names, labels = build_training_data(hivoto)
    print("  Training XGBoost model …")
    vectorizer, model = train_model(names, labels)
    joblib.dump(vectorizer, VECTORIZER_PATH)
    joblib.dump(model, MODEL_PATH)
    print(f"  Model saved → {MODEL_PATH}")
    return vectorizer, model


# ---------------------------------------------------------------------------
# Token splitting  (same rules as hivoto.py)
# ---------------------------------------------------------------------------

_SKIP_RE = re.compile(
    r"""
    ^\(          |   # bracketed token
    \)$          |
    ^\w\.$       |   # single-letter abbreviation, e.g. A.
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
}


def tokenise(forename: str) -> list[str]:
    if not isinstance(forename, str):
        return []
    tokens = re.split(r"[\s,;/]+", forename.strip())
    return [
        t
        for t in tokens
        if t and not _SKIP_RE.search(t) and t.lower() not in _PARTICLES
    ]


# ---------------------------------------------------------------------------
# Predict for a batch of tokens
# ---------------------------------------------------------------------------


def predict_tokens(
    tokens: list[str],
    vectorizer: TfidfVectorizer,
    model: XGBClassifier,
    lookup: dict[str, str],
) -> tuple[list[str], list[float]]:
    """
    Returns (labels, probas) where label is 'male'/'female'/'andy'/'unknown'
    and proba is P(female) in [0, 1].
    """
    labels: list[str] = []
    probas: list[float] = []

    for token in tokens:
        key = token.lower().rstrip(".")
        if key in lookup:
            hit = lookup[key]
            if hit == "male":
                labels.append("male")
                probas.append(0.0)
            elif hit == "female":
                labels.append("female")
                probas.append(1.0)
            elif hit in ("mostly_male",):
                labels.append("mostly_male")
                probas.append(0.2)
            elif hit in ("mostly_female",):
                labels.append("mostly_female")
                probas.append(0.8)
            elif hit == "andy":
                labels.append("andy")
                probas.append(0.5)
            else:
                labels.append("unknown")
                probas.append(0.5)
        else:
            # Model prediction
            X = vectorizer.transform([key])
            proba = float(model.predict_proba(X)[0, 1])
            label = "female" if proba >= 0.5 else "male"
            labels.append(label)
            probas.append(proba)

    return labels, probas


def consensus_gender(labels: list[str], probas: list[float]) -> str:
    """
    Determine a single consensus gender from per-token results.

    Strategy:
      - If any token is a hard lookup hit (male/female/mostly_*), use majority vote
        over those tokens only.
      - Otherwise average P(female) probabilities and threshold at 0.5.
      - If all tokens are andy/unknown, return 'andy'.
    """
    hard = [l for l in labels if l not in ("andy", "unknown")]
    if hard:
        counts = Counter(hard)
        winner = max(counts, key=lambda g: counts[g])
        # Normalise mostly_* to binary for the result column
        if winner in ("mostly_male", "male"):
            return "male"
        if winner in ("mostly_female", "female"):
            return "female"
        return winner

    if all(l == "andy" for l in labels):
        return "andy"

    if probas:
        return "female" if np.mean(probas) >= 0.5 else "male"

    return "unknown"


# ---------------------------------------------------------------------------
# Main: apply to Schleiermacher persons
# ---------------------------------------------------------------------------


def run(force_retrain: bool = False) -> pd.DataFrame:
    print("=== hivoto XGBoost Gender Classifier ===")

    print("\n[1] Loading HIVOTO data …")
    hivoto = load_hivoto(HIVOTO_CSV)

    print("\n[2] Building lookup index …")
    lookup = build_lookup_index(hivoto)
    print(f"  Lookup index size: {len(lookup):,}")

    print("\n[3] Getting model …")
    vectorizer, model = get_model(hivoto, force_retrain=force_retrain)

    print("\n[4] Loading persons data …")
    persons = pd.read_csv(INPUT_CSV)
    print(f"  {len(persons)} persons")

    print("\n[5] Predicting …")
    rows = []
    for _, person in persons.iterrows():
        xml_id = person["xml_id"]
        forename = person["forename"]
        tokens = tokenise(forename)

        if not tokens:
            rows.append(
                {
                    "xml_id": xml_id,
                    "forename": forename,
                    "xgb_tokens": None,
                    "xgb_results": None,
                    "xgb_proba": None,
                    "xgb_gender": "no_name",
                }
            )
            continue

        labels, probas = predict_tokens(tokens, vectorizer, model, lookup)
        gender = consensus_gender(labels, probas)

        rows.append(
            {
                "xml_id": xml_id,
                "forename": forename,
                "xgb_tokens": "|".join(tokens),
                "xgb_results": "|".join(labels),
                "xgb_proba": "|".join(f"{p:.2f}" for p in probas),
                "xgb_gender": gender,
            }
        )

    result = pd.DataFrame(rows)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"\n[6] Saved → {OUTPUT_CSV}")
    print("\nGender distribution:")
    print(result["xgb_gender"].value_counts().to_string())
    return result


if __name__ == "__main__":
    force_retrain = os.getenv("RETRAIN", "0") == "1"
    run(force_retrain=force_retrain)
