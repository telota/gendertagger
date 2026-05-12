"""
LLM-based gender classification via a local Ollama endpoint.

For each person in the input CSV the complete record (surname, forename, birth,
death, note, alt_names) is sent to a locally-hosted LLM through the Ollama
REST-API.  The model is asked to return structured JSON that is validated
against a Pydantic schema.  If validation fails, the prompt is retried up to
MAX_RETRIES times with the validation error fed back so the model can
self-correct.

Gender classes:
  male         – the person is male
  female       – the person is female
  organisation – the entry refers to a corporate body / institution
  unknown      – gender cannot be determined from the available data

Output columns:
  xml_id            – Schleiermacher register ID (primary/foreign key)
  forename          – original forename string
  llm_gender        – classified gender (male / female / organisation / unknown)
  llm_confidence    – model's self-reported confidence (0.0 – 1.0)
  llm_reasoning     – short free-text reasoning the model gave
  llm_retries       – how many retries were needed (0 = first attempt OK)
  llm_model         – model name used for the run

Usage:
    python methods/llm.py
    python methods/llm.py --model gemma3:12b
    python methods/llm.py --base-url http://localhost:11434
"""

from __future__ import annotations

import argparse
import json
import time
from enum import Enum
from pathlib import Path

import pandas as pd
import requests
from pydantic import BaseModel, Field, ValidationError
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

INPUT_CSV = Path("data/input/schleiermacher_persons.csv")
OUTPUT_DIR = Path("data/results")
OUTPUT_CSV = OUTPUT_DIR / "llm_gender_results.csv"

# ---------------------------------------------------------------------------
# Ollama config
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gpt-oss:20b"
DEFAULT_BASE_URL = "http://localhost:11434"
MAX_RETRIES = 3
REQUEST_TIMEOUT = 120  # seconds per API call

# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------


class GenderLabel(str, Enum):
    male = "male"
    female = "female"
    organisation = "organisation"
    unknown = "unknown"


class LLMCert(str, Enum):
    high = "high"
    low = "low"
    uncertain = "uncertain"


class GenderClassification(BaseModel):
    """Schema for the structured JSON response from the LLM."""

    gender: GenderLabel = Field(
        ...,
        description=(
            "The classified gender of the person. Must be one of: "
            "male, female, organisation, unknown."
        ),
    )
    cert: LLMCert = Field(
        ...,
        description=(
            "Your confidence tier in the classification. "
            '"high": clear, unambiguous signal (explicit name, title, relational term, or note). '
            '"low": some signal but ambiguous or indirect. '
            '"uncertain": little or no evidence; classification is a guess.'
        ),
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Your confidence in the classification as a float between "
            "0.0 (no confidence) and 1.0 (fully confident)."
        ),
    )
    reasoning: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="A short explanation of why you chose this gender class.",
    )


# ---------------------------------------------------------------------------
# JSON schema string for inclusion in the prompt
# ---------------------------------------------------------------------------

_SCHEMA_JSON = json.dumps(GenderClassification.model_json_schema(), indent=2)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert historical-prosopographical assistant specialising in \
18th/19th-century German-speaking Europe.  Your task is to determine the \
gender of a person described in a scholarly person-register entry.

You MUST reply with a single JSON object – no markdown fences, no extra text – \
that conforms EXACTLY to this JSON-Schema:

{schema}

Gender classes:
  • "male"         – the person is male
  • "female"       – the person is female
  • "organisation" – the entry refers to a corporate body, institution, \
society, academy, church, or similar non-person entity
  • "unknown"      – gender cannot be determined from the data provided

Guidelines:
  1. Use ALL available fields (surname, forename, birth, death, note, \
alternative names) to make your decision.
  2. German-language notes are common; read them carefully for pronouns, \
role descriptions (e.g. "Pastorin", "Kaufmann"), and family relations \
(e.g. "Frau des", "Tochter", "Sohn").
  3. Entries with forenames like "(Frau)" or "(Kinder des …)" hint at \
female or unknown respectively.
  4. If a note says "Nichte" (niece), "Schwester" (sister), "Witwe" (widow) \
→ female.  "Neffe" (nephew), "Bruder" (brother) → male.
  5. Entries whose name contains family-group qualifiers such as \
"(Familie des …)", "(Kinder des …)", "(Geschwister …)", or "(Ehepaar …)" \
are PERSONS (or groups of persons) in the register – do NOT classify them \
as "organisation".  Because no single gender can be assigned to a group, \
always use "unknown" for such entries.
  6. Only use "organisation" for genuine non-person entries such as \
academies, churches, companies, or societies.
  7. If no reliable signal exists, choose "unknown" with low confidence.
  8. The "confidence" value must honestly reflect your certainty.
  9. For the "cert" field choose exactly one of:
       "high"      – unambiguous evidence: explicit gendered forename, title \
(Frau, Herr, Pastorin, Graf …), clear relational term in name or note \
(Nichte, Sohn, Witwe …), or GND-style factual statement.
       "low"       – some signal, but indirect or ambiguous: androgynous \
forename, foreign name of uncertain origin, weakly gendered occupational \
title, partial note.
       "uncertain" – almost no evidence: surname only, initials only, \
abbreviations, entries where even an expert would be guessing.
""".format(
    schema=_SCHEMA_JSON
)


def build_user_prompt(row: pd.Series) -> str:
    """Render the person record into a user-prompt string."""
    parts = []
    for col in ("surname", "forename", "birth", "death", "note", "alt_names"):
        value = row.get(col, "")
        if pd.notna(value) and str(value).strip():
            parts.append(f"{col}: {value}")
    return "Classify the gender of this person:\n" + "\n".join(parts)


def build_retry_user_prompt(row: pd.Series, previous_answer: str, error: str) -> str:
    """Build a follow-up prompt that includes the validation error."""
    base = build_user_prompt(row)
    return (
        f"{base}\n\n"
        f"--- IMPORTANT ---\n"
        f"Your previous answer was invalid.  Here is what you returned:\n"
        f"{previous_answer}\n\n"
        f"Validation error:\n{error}\n\n"
        f"Please try again.  Reply ONLY with a corrected JSON object."
    )


# ---------------------------------------------------------------------------
# Ollama API helper
# ---------------------------------------------------------------------------


def call_ollama(
    model: str,
    system: str,
    user: str,
    base_url: str,
) -> str:
    """Send a chat-completion request to the Ollama REST API and return the
    assistant message content as a raw string."""
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
        },
    }
    resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


# ---------------------------------------------------------------------------
# Parse + validate with retries
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """Strip common wrapping (markdown fences, leading prose) to find JSON."""
    text = text.strip()
    # Remove markdown code fences
    if text.startswith("```"):
        # Remove opening fence (possibly ```json)
        first_nl = text.index("\n")
        text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    # If the model prefixed prose before the JSON, try to find the object
    if not text.startswith("{"):
        brace = text.find("{")
        if brace != -1:
            text = text[brace:]
            # find matching closing brace
            depth = 0
            for i, ch in enumerate(text):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        text = text[: i + 1]
                        break
    return text


def classify_with_retries(
    row: pd.Series,
    model: str,
    base_url: str,
) -> tuple[GenderClassification | None, int, str | None]:
    """Try to classify a person, retrying on validation failures.

    Returns (classification | None, retries_used, last_raw_answer).
    """
    user_prompt = build_user_prompt(row)
    last_raw: str | None = None
    raw: str = "(no response)"

    for attempt in range(MAX_RETRIES + 1):
        try:
            raw = call_ollama(model, SYSTEM_PROMPT, user_prompt, base_url)
            last_raw = raw
            cleaned = _extract_json(raw)
            parsed = json.loads(cleaned)
            result = GenderClassification.model_validate(parsed)
            return result, attempt, raw
        except (json.JSONDecodeError, ValidationError) as exc:
            error_msg = str(exc)
            # On retry, feed the error back
            if attempt < MAX_RETRIES:
                user_prompt = build_retry_user_prompt(
                    row,
                    previous_answer=raw,
                    error=error_msg,
                )
        except requests.RequestException as exc:
            # Network / timeout errors – wait briefly then retry
            last_raw = f"REQUEST_ERROR: {exc}"
            if attempt < MAX_RETRIES:
                time.sleep(2)

    return None, MAX_RETRIES, last_raw


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="LLM-based gender classification via Ollama"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Ollama base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only the first N persons (0 = all, useful for testing)",
    )
    args = parser.parse_args()

    model = args.model
    base_url = args.base_url.rstrip("/")

    print("LLM gender classification via Ollama")
    print(f"  Model   : {model}")
    print(f"  Endpoint: {base_url}")
    print("=" * 75)

    # Verify Ollama is reachable
    try:
        health = requests.get(f"{base_url}/api/tags", timeout=10)
        health.raise_for_status()
        available = [m["name"] for m in health.json().get("models", [])]
        print(f"  Available models: {', '.join(available) or '(none listed)'}")
        if model not in available and f"{model}:latest" not in available:
            print(
                f"  ⚠  Model '{model}' not found locally – Ollama will pull it on first request."
            )
    except requests.RequestException as exc:
        print(f"  ERROR: Cannot reach Ollama at {base_url}: {exc}")
        print("  Make sure Ollama is running (`ollama serve`).")
        return

    persons = pd.read_csv(INPUT_CSV, dtype=str)
    if args.limit > 0:
        persons = persons.head(args.limit)
    print(f"\nInput: {len(persons):,} persons from {INPUT_CSV}\n")

    rows: list[dict] = []
    failed = 0

    pbar = tqdm(persons.iterrows(), total=len(persons), desc="Classifying")
    for _, person in pbar:
        xml_id = person["xml_id"]
        surname = person.get("surname", "")
        forename = person.get("forename", "")
        surname = "" if pd.isna(surname) else str(surname)
        forename = "" if pd.isna(forename) else str(forename)
        display_name = f"{forename} {surname}".strip() or xml_id

        pbar.set_postfix_str(f"→ {display_name}", refresh=True)

        result, retries, raw = classify_with_retries(person, model, base_url)

        if result is not None:
            retry_info = f" (retries: {retries})" if retries > 0 else ""
            tqdm.write(
                f"  {display_name:<40} → {result.gender.value:<14} "
                f"cert={result.cert.value:<10} (conf: {result.confidence:.2f}){retry_info}"
            )
            rows.append(
                {
                    "xml_id": xml_id,
                    "forename": forename,
                    "llm_gender": result.gender.value,
                    "llm_cert": result.cert.value,
                    "llm_confidence": round(result.confidence, 4),
                    "llm_reasoning": result.reasoning,
                    "llm_retries": retries,
                    "llm_model": model,
                }
            )
        else:
            failed += 1
            tqdm.write(f"  {display_name:<40} → ERROR after {retries} retries")
            rows.append(
                {
                    "xml_id": xml_id,
                    "forename": forename,
                    "llm_gender": "error",
                    "llm_cert": "uncertain",
                    "llm_confidence": 0.0,
                    "llm_reasoning": f"Failed after {MAX_RETRIES} retries. Last response: {raw}",
                    "llm_retries": retries,
                    "llm_model": model,
                }
            )

    result_df = pd.DataFrame(rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(result_df):,} rows → {OUTPUT_CSV}")

    if failed:
        print(f"  ⚠  {failed} person(s) could not be classified after retries.")

    print("\nGender distribution:")
    counts = result_df["llm_gender"].value_counts()
    for label, n in counts.items():
        print(f"  {label:<16} {n:>6,}  ({n / len(result_df) * 100:.1f}%)")

    retried = result_df[result_df["llm_retries"] > 0]
    print(f"\nPersons that needed retries: {len(retried):,}")
    print(
        f"  Mean retries (when > 0): {retried['llm_retries'].mean():.2f}"
        if len(retried)
        else ""
    )


if __name__ == "__main__":
    main()
