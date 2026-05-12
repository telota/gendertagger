"""
Gender classification module - integrates multiple gender classifiers
"""

from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional
import pandas as pd


class GenderClassifier(ABC):
    """Abstract base class for gender classification."""

    @abstractmethod
    def predict(self, person_data: Dict[str, str]) -> Tuple[str, float]:
        """
        Predict gender from person data.

        Args:
            person_data: Dictionary containing person information with keys:
                - name: Full name or first name
                - forename: First name (optional)
                - surname: Last name (optional)
                - birth_date: Birth date (optional)
                - death_date: Death date (optional)
                - notes: Additional notes (optional)
                - gnd_id: GND identifier (optional)

        Returns:
            Tuple of (predicted_gender, confidence_score) where:
                - predicted_gender: 'male', 'female', 'unknown', or 'institution'
                - confidence_score: Float between 0.0 and 1.0
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the classifier name."""
        pass


class GenderGuesserClassifier(GenderClassifier):
    """Gender classifier using the gender-guesser library."""

    def __init__(self):
        """Initialize the gender guesser detector."""
        import gender_guesser.detector as gender

        self.detector = gender.Detector()

    @property
    def name(self) -> str:
        return "gender-guesser"

    def predict(self, person_data: Dict[str, str]) -> Tuple[str, float]:
        """Predict gender using gender-guesser library."""
        # Extract forename(s)
        forename = person_data.get("forename", "")
        surname = person_data.get("surname", "")
        name = person_data.get("name", "")

        # Get all forenames
        if forename:
            forenames = forename.strip().split()
        elif name:
            # If no forename field, extract likely given names from full name
            # Strategy: take all words except the last one (likely surname)
            # or if there's a known surname, exclude it
            words = name.strip().split()
            if surname and words:
                # Remove surname from the end if present
                if words[-1] == surname:
                    forenames = words[:-1]
                else:
                    forenames = words[:-1] if len(words) > 1 else words
            elif len(words) > 1:
                # Assume last word is surname, take everything before
                forenames = words[:-1]
            else:
                forenames = words
        else:
            forenames = []

        if not forenames:
            return ("unknown", 0.0)

        # Check each forename and aggregate results
        gender_map = {
            "male": ("male", 0.95),
            "female": ("female", 0.95),
            "mostly_male": ("male", 0.70),
            "mostly_female": ("female", 0.70),
            "andy": ("unknown", 0.50),
            "unknown": ("unknown", 0.0),
        }

        results = []
        for fname in forenames:
            result = self.detector.get_gender(fname)
            gender, conf = gender_map.get(result, ("unknown", 0.0))
            if gender != "unknown":  # Only include non-unknown results
                results.append((gender, conf))

        if not results:
            return ("unknown", 0.0)

        # Aggregate: weighted average by confidence
        male_score = sum(conf for g, conf in results if g == "male")
        female_score = sum(conf for g, conf in results if g == "female")

        if male_score == 0 and female_score == 0:
            return ("unknown", 0.0)

        # Return gender with highest score and normalized confidence
        total_score = male_score + female_score
        if female_score > male_score:
            return ("female", female_score / total_score)
        else:
            return ("male", male_score / total_score)


class NomquamClassifier(GenderClassifier):
    """Gender classifier using the nomquamgender library."""

    def __init__(self):
        """Initialize the nomquam classifier."""
        try:
            import nomquamgender as nq

            self.nq = nq
        except ImportError:
            raise ImportError("nomquamgender library is not installed")

    @property
    def name(self) -> str:
        return "nomquamgender"

    def predict(self, person_data: Dict[str, str]) -> Tuple[str, float]:
        """Predict gender using nomquamgender library."""
        # Extract forename(s)
        forename = person_data.get("forename", "")
        surname = person_data.get("surname", "")
        name = person_data.get("name", "")

        # Get all forenames
        if forename:
            forenames = forename.strip().split()
        elif name:
            # If no forename field, extract likely given names from full name
            words = name.strip().split()
            if surname and words:
                # Remove surname from the end if present
                if words[-1] == surname:
                    forenames = words[:-1]
                else:
                    forenames = words[:-1] if len(words) > 1 else words
            elif len(words) > 1:
                # Assume last word is surname, take everything before
                forenames = words[:-1]
            else:
                forenames = words
        else:
            forenames = []

        if not forenames:
            return ("unknown", 0.0)

        try:
            # Create model once
            model = self.nq.NBGC()

            # Check each forename
            results = []
            for fname in forenames:
                # Annotate with surname if available for better context
                test_name = f"{fname} {surname}".strip() if surname else fname
                result = model.annotate([test_name])

                if result and len(result) > 0:
                    annotation = result[0]
                    if len(annotation) >= 5:
                        p_gf = annotation[4]  # probability gendered female

                        if p_gf is not None and not (
                            isinstance(p_gf, float) and pd.isna(p_gf)
                        ):
                            # Store p(gf) for aggregation
                            results.append(p_gf)

            if not results:
                return ("unknown", 0.0)

            # Aggregate: average p(gf) across all forenames
            avg_p_gf = sum(results) / len(results)

            # Convert to gender classification
            if avg_p_gf > 0.5:
                return ("female", float(avg_p_gf))
            else:
                return ("male", float(1.0 - avg_p_gf))

        except Exception:
            return ("unknown", 0.0)


class HuggingFaceGenderClassifier(GenderClassifier):
    """Gender classifier using Hugging Face transformers (from notebook)."""

    def __init__(self, model_name: str = "padmajabfrl/Gender-Classification"):
        """
        Initialize the Hugging Face classifier.

        Args:
            model_name: Name of the pre-trained model to use
        """
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch

        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()
        self.torch = torch

        # Label mapping (0=male, 1=female based on testing in notebook)
        self.label_map = {0: "male", 1: "female"}

    @property
    def name(self) -> str:
        return f"hf-{self.model_name.split('/')[-1]}"

    def predict(self, person_data: Dict[str, str]) -> Tuple[str, float]:
        """Predict gender using Hugging Face model."""
        # Use full name for this model (it can handle multi-word names)
        forename = person_data.get("forename", "")
        surname = person_data.get("surname", "")
        name = person_data.get("name", "")

        # Build full name
        if forename and surname:
            full_name = f"{forename} {surname}".strip()
        elif forename:
            full_name = forename.strip()
        elif name:
            full_name = name.strip()
        else:
            full_name = ""

        if not full_name:
            return ("unknown", 0.0)

        try:
            # Tokenize and prepare input with full name
            inputs = self.tokenizer(
                full_name,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=128,  # Increased to handle longer full names
            )

            # Get prediction
            with self.torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits[0]
                predicted_label = logits.argmax().item()

                # Get confidence using softmax
                probs = self.torch.nn.functional.softmax(logits, dim=0)
                confidence = probs[predicted_label].item()

            gender = self.label_map.get(predicted_label, "unknown")
            return (gender, confidence)

        except Exception:
            return ("unknown", 0.0)


class GNDClassifier(GenderClassifier):
    """
    Gender classifier that fetches data from GND API.
    Based on notebook implementation.
    """

    def __init__(self):
        """Initialize GND classifier with session."""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        self.session = requests.Session()
        retry_strategy = Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    @property
    def name(self) -> str:
        return "gnd-api"

    def predict(self, person_data: Dict[str, str]) -> Tuple[str, float]:
        """Fetch gender from GND API if GND ID is available."""
        gnd_id = person_data.get("gnd_id")

        if not gnd_id:
            return ("unknown", 0.0)

        try:
            # Extract GND ID from URI if needed
            if "/" in gnd_id:
                gnd_id = gnd_id.rstrip("/").split("/")[-1]

            # Use lobid-gnd API
            api_url = f"https://lobid.org/gnd/{gnd_id}.json"
            response = self.session.get(api_url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if "gender" in data:
                    gender_info = data["gender"]

                    if isinstance(gender_info, list) and gender_info:
                        gender_info = gender_info[0]

                    if isinstance(gender_info, dict):
                        gender_id = gender_info.get("id", "")
                    else:
                        gender_id = str(gender_info)

                    # Map GND gender URIs to our format
                    if "male" in gender_id.lower() or gender_id == "1":
                        return ("male", 1.0)
                    elif "female" in gender_id.lower() or gender_id == "2":
                        return ("female", 1.0)
                    elif "divers" in gender_id.lower():
                        return ("unknown", 1.0)

                # Check for organization
                if "type" in data:
                    types = (
                        data["type"]
                        if isinstance(data["type"], list)
                        else [data["type"]]
                    )
                    if any("CorporateBody" in t or "Organization" in t for t in types):
                        return ("institution", 1.0)

            return ("unknown", 0.0)

        except Exception as e:
            return ("unknown", 0.0)


class HuggingFaceGenderizeClassifier(GenderClassifier):
    """Gender classifier using the HuggingFace 'genderize' model."""

    def __init__(self):
        """Initialize the genderize model."""
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch

        self.model_name = "imranali291/genderize"
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model.eval()
        self.torch = torch

        # Label mapping: 0=Female, 1=Male
        self.label_map = {0: "female", 1: "male"}

    @property
    def name(self) -> str:
        """Return classifier name."""
        return "hf_genderize"

    def predict(self, person_data: Dict[str, str]) -> Tuple[str, float]:
        """Predict gender using HF genderize model."""
        # Extract forename or name
        forename = person_data.get("forename", "")
        name = person_data.get("name", "")

        # Get the first name only (this model works best with single first names)
        if forename:
            # If we have a forename field, use the first word
            first_name = str(forename).strip().split()[0] if forename else ""
        elif name:
            # If we have a name field, extract all but the last word (surname), then take first
            words = str(name).strip().split()
            if len(words) > 1:
                # Remove last word (assumed surname), take first of remaining
                first_name = words[0]
            else:
                first_name = words[0] if words else ""
        else:
            first_name = ""

        if not first_name or pd.isna(first_name):
            return ("unknown", 0.0)

        try:
            # Tokenize and predict
            inputs = self.tokenizer(
                first_name,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=32,
            )

            with self.torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                predicted_label = logits.argmax(dim=-1).item()

                # Get confidence from softmax probabilities
                probs = self.torch.nn.functional.softmax(logits, dim=-1)[0]
                confidence = probs[predicted_label].item()

            gender = self.label_map.get(predicted_label, "unknown")
            return (gender, confidence)

        except Exception as e:
            return ("unknown", 0.0)


class OllamaLLMClassifier(GenderClassifier):
    """Gender classifier using Ollama LLM."""

    def __init__(
        self,
        model_name: str = "gpt-oss:120b",
        api_url: str = "http://localhost:11434/api/generate",
    ):
        """
        Initialize the Ollama LLM classifier.

        Args:
            model_name: The Ollama model to use
            api_url: The Ollama API endpoint URL
        """
        self.model_name = model_name
        self.api_url = api_url

        # JSON schema for structured output
        self.schema = {
            "type": "object",
            "properties": {
                "gender": {
                    "type": "string",
                    "enum": ["male", "female", "unknown", "organisation"],
                },
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "reasoning": {"type": "string"},
            },
            "required": ["gender", "confidence"],
        }

    @property
    def name(self) -> str:
        """Return classifier name."""
        model_safe = (
            self.model_name.replace(":", "_").replace(".", "_").replace("-", "_")
        )
        return f"llm_{model_safe}"

    def predict(self, person_data: Dict[str, str]) -> Tuple[str, float]:
        """Predict gender using Ollama LLM."""
        import requests
        import json

        forename = person_data.get("forename", "") or person_data.get("name", "")
        surname = person_data.get("surname", "")

        if not forename:
            return ("unknown", 0.0)

        # Construct prompt
        full_name = f"{forename} {surname}".strip()

        prompt = f"""Classify the gender of the person with the given name.

Name: {full_name}

Instructions:
1. Analyze the name carefully
2. Return a JSON object with:
   - "gender": one of ["male", "female", "unknown", "organisation"]
   - "confidence": a number between 0.0 and 1.0
   - "reasoning": brief explanation

Examples:
{{"gender": "female", "confidence": 0.95, "reasoning": "Maria is a traditional female name"}}
{{"gender": "male", "confidence": 0.90, "reasoning": "Friedrich is a German male name"}}
{{"gender": "unknown", "confidence": 0.3, "reasoning": "Ambiguous or rare name"}}

Return only valid JSON, no other text.
"""

        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }

            response = requests.post(self.api_url, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "")

                if response_text:
                    # Parse JSON response
                    try:
                        parsed = json.loads(response_text)
                        gender = parsed.get("gender", "unknown")
                        confidence = parsed.get("confidence", 0.0)

                        # Validate gender value
                        if gender not in ["male", "female", "unknown", "organisation"]:
                            gender = "unknown"

                        # Ensure confidence is in valid range
                        confidence = max(0.0, min(1.0, float(confidence)))

                        return (gender, confidence)
                    except json.JSONDecodeError:
                        return ("unknown", 0.0)

            return ("unknown", 0.0)

        except requests.exceptions.RequestException as e:
            return ("unknown", 0.0)
        except Exception as e:
            return ("unknown", 0.0)


def run_classifiers(person: Dict, classifiers: list) -> Dict[str, Tuple[str, float]]:
    """
    Run all classifiers on a person.

    Args:
        person: Person dictionary
        classifiers: List of classifier instances

    Returns:
        Dictionary mapping classifier name to (gender, confidence)
    """
    results = {}

    for classifier in classifiers:
        try:
            gender, confidence = classifier.predict(person)
            results[classifier.name] = (gender, confidence)
        except Exception as e:
            print(f"Error running {classifier.name}: {e}")
            results[classifier.name] = ("unknown", 0.0)

    return results


def get_available_classifiers() -> list:
    """
    Get list of available classifiers that can be instantiated.

    Returns:
        List of classifier instances
    """
    classifiers = []

    # Try gender-guesser
    try:
        classifiers.append(GenderGuesserClassifier())
    except Exception as e:
        print(f"Could not load gender-guesser: {e}")

    # Try nomquam
    try:
        classifiers.append(NomquamClassifier())
    except Exception as e:
        print(f"Could not load nomquamgender: {e}")

    # Try HuggingFace genderize model
    try:
        classifiers.append(HuggingFaceGenderizeClassifier())
    except Exception as e:
        print(f"Could not load HuggingFace genderize classifier: {e}")

    # Try HuggingFace Gender-Classification model (padmajabfrl/Gender-Classification)
    try:
        classifiers.append(HuggingFaceGenderClassifier())
    except Exception as e:
        print(f"Could not load HuggingFace Gender-Classification classifier: {e}")

    # GND API is always available
    classifiers.append(GNDClassifier())

    # Note: OllamaLLMClassifier is not auto-loaded as it requires
    # a running Ollama server and model specification
    # Users can instantiate it manually: OllamaLLMClassifier(model_name="gpt-oss:120b")

    return classifiers


def classify_dataframe(
    df: pd.DataFrame, classifiers: Optional[list] = None
) -> pd.DataFrame:
    """
    Classify all persons in a dataframe.

    Args:
        df: DataFrame with person data (must have columns: forename, surname, etc.)
        classifiers: List of classifier instances (or None to use all available)

    Returns:
        DataFrame with added classifier prediction columns
    """
    if classifiers is None:
        classifiers = get_available_classifiers()

    # Add column for each classifier
    for classifier in classifiers:
        col_name = classifier.name
        col_confidence = f"{classifier.name}_confidence"

        df[col_name] = None
        df[col_confidence] = 0.0

    # Classify each person
    for idx, row in df.iterrows():
        person_data = {
            "name": row.get("name", ""),
            "forename": row.get("forename", ""),
            "surname": row.get("surname", ""),
            "birth_date": row.get("birth_date", ""),
            "death_date": row.get("death_date", ""),
            "notes": row.get("notes", ""),
            "gnd_id": row.get("gnd_id", "") or row.get("gnd_uri", ""),
        }

        results = run_classifiers(person_data, classifiers)

        for clf_name, (gender, confidence) in results.items():
            df.at[idx, clf_name] = gender
            df.at[idx, f"{clf_name}_confidence"] = confidence

    return df
