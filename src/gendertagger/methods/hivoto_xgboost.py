"""Adapter for the experimental HIVOTO-XGBoost character-n-gram classifier.

For each usable forename token, checks the same compiled HIVOTO lookup the
plain HIVOTO adapter uses; only tokens absent from that lookup fall back to a
trained TF-IDF(char_wb, n=2..5) + XGBClassifier model reconstructed from
pickle-free files. Consensus across a person's tokens is bespoke, ported from
the legacy reference script, not the shared ``consensus_label``. Excluded from
the reference vote (``REFERENCE_IGNORED_METHODS``). See ADR-0023, ADR-0024,
and ADR-0025.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from statistics import fmean
from typing import Final, Protocol, cast

from gendertagger.methods.base import LookupMethodConfig, MethodDependencyError
from gendertagger.methods.hivoto import HivotoLookup, SqliteHivotoLookup
from gendertagger.methods.model_manifest import (
    ModelDirectoryResolver,
    UnavailableModelDirectoryResolver,
)
from gendertagger.methods.name_tokens import NO_NAME_LABEL, usable_forename_tokens
from gendertagger.methods.normalization import HIVOTO_XGBOOST_NORMALIZATION, normalize_raw_label
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput

HIVOTO_XGBOOST_MODEL_MANIFEST_LOGICAL_TYPE: Final = "hivoto_xgboost_model_manifest"
HIVOTO_XGBOOST_MODEL_FILE_LOGICAL_TYPE: Final = "hivoto_xgboost_model_file"
HIVOTO_XGBOOST_MODEL_SCHEMA_VERSION: Final = "hivoto_xgboost_model_v1"
HIVOTO_XGBOOST_MODEL_COMPILER_VERSION: Final = "hivoto_xgboost_model_manifest_compiler_v1"

LOOKUP_MEMBER_RELATIVE_PATH: Final = "hivoto_lookup.sqlite3"
VOCABULARY_MEMBER_RELATIVE_PATH: Final = "vocabulary.json"
IDF_MEMBER_RELATIVE_PATH: Final = "idf.json"
VECTORIZER_CONFIG_MEMBER_RELATIVE_PATH: Final = "vectorizer_config.json"
MODEL_MEMBER_RELATIVE_PATH: Final = "model.json"

# Placeholder probability the legacy script assigns a lookup hit when averaging
# it alongside model-predicted probabilities; "unknown" (any hit outside this
# map) falls back to 0.5 via .get() below.
_HARD_LABELS_TO_PROBA: Final[dict[str, float]] = {
    "male": 0.0,
    "female": 1.0,
    "mostly_male": 0.2,
    "mostly_female": 0.8,
    "andy": 0.5,
}
_DEFAULT_PROBA: Final = 0.5


class HivotoXgboostConfig(LookupMethodConfig):
    """Resolved configuration selecting a materialized HIVOTO-XGBoost bundle by digest."""


class TokenProbabilityModel(Protocol):
    """Batch P(female) inference over character n-gram features."""

    def predict_female_probability(self, tokens: Sequence[str]) -> list[float]:
        """Return P(female) for each input token, in the same order."""
        ...


ModelFactory = Callable[[Path], TokenProbabilityModel]
LookupFactory = Callable[[Path], HivotoLookup]


class _SklearnXgboostModel:
    """Deterministic batch inference reconstructed without ever calling ``.fit()``.

    Rebuilds the vectorizer from its known fixed configuration and its two
    pieces of learned state (``vocabulary_``, ``idf_``), and loads the
    classifier from XGBoost's own non-pickle export. See
    ``data/models/hivoto_xgboost/PROVENANCE.md`` for the conversion and its
    round-trip verification against the original fitted objects.
    """

    def __init__(self, directory: Path) -> None:
        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer
            from xgboost import XGBClassifier
        except ImportError as error:  # pragma: no cover - exercised only without the extra
            msg = (
                "hivoto_xgboost requires the 'hivoto-xgboost' extra (install scikit-learn, xgboost)"
            )
            raise MethodDependencyError(msg) from error

        config = json.loads(
            (directory / VECTORIZER_CONFIG_MEMBER_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        vocabulary = json.loads(
            (directory / VOCABULARY_MEMBER_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        idf_by_index = json.loads(
            (directory / IDF_MEMBER_RELATIVE_PATH).read_text(encoding="utf-8")
        )

        vectorizer = TfidfVectorizer(
            **{**config, "ngram_range": tuple(config["ngram_range"]), "dtype": np.float32}
        )
        vectorizer.vocabulary_ = vocabulary
        vectorizer.idf_ = np.asarray(idf_by_index, dtype=np.float32)
        self._vectorizer = vectorizer

        model = XGBClassifier()
        model.load_model(str(directory / MODEL_MEMBER_RELATIVE_PATH))
        self._model = model

    def predict_female_probability(self, tokens: Sequence[str]) -> list[float]:
        """Return P(female) for each token via the reconstructed vectorizer+model."""
        if not tokens:
            return []
        features = self._vectorizer.transform(list(tokens))
        return [float(value) for value in self._model.predict_proba(features)[:, 1]]


def default_model_factory(directory: Path) -> TokenProbabilityModel:
    """Load a locally materialized HIVOTO-XGBoost bundle as an inference backend.

    Raises:
        MethodDependencyError: If the ``hivoto-xgboost`` extra is not installed.
    """
    return cast(TokenProbabilityModel, _SklearnXgboostModel(directory))


def _lookup_key(token: str) -> str:
    """Normalize a token for querying the reused ``hivoto_lookup`` artifact.

    Matches ``HivotoMethod``'s own query normalization, since this reads the
    identical compiled artifact that adapter queries.
    """
    return token.lower().rstrip(".,;:)\"'")


def _model_key(token: str) -> str:
    """Normalize a token for the reconstructed model, matching training preprocessing.

    The legacy training data lowercased and stripped only trailing periods
    (not the broader punctuation set ``_lookup_key`` strips); fidelity to the
    model's trained input distribution takes priority here over consistency
    with the unrelated lookup-query convention. The vectorizer's own
    ``lowercase=True`` makes the explicit ``.lower()`` redundant but harmless.
    """
    return token.lower().rstrip(".")


def _consensus(labels: Sequence[str], probabilities: Sequence[float]) -> str:
    """Port of the legacy ``hivoto_xgboost`` consensus reduction.

    A "hard" vote is any label that is not the lookup's ``andy``/``unknown``
    category; model-predicted tokens are always male/female, so they are
    always hard and only ever get out-voted (never excluded) by hard lookup
    hits. Ties among hard labels break toward whichever value first appears in
    token order, matching ``collections.Counter``/``max`` iteration order
    exactly as the legacy script relied on.
    """
    hard = [label for label in labels if label not in ("andy", "unknown")]
    if hard:
        counts = Counter(hard)
        winner = max(counts, key=lambda label: counts[label])
        if winner in ("mostly_male", "male"):
            return "male"
        if winner in ("mostly_female", "female"):
            return "female"
        return winner
    if all(label == "andy" for label in labels):
        return "andy"
    if probabilities:
        return "female" if fmean(probabilities) >= 0.5 else "male"
    return "unknown"


class HivotoXgboostMethod:
    """Experimental character-n-gram HIVOTO extension; excluded from the reference vote."""

    descriptor = MethodDescriptor(
        name="hivoto_xgboost",
        implementation_version="hivoto_xgboost_v1",
        normalization_version=HIVOTO_XGBOOST_NORMALIZATION.normalization_version,
    )
    config_model = HivotoXgboostConfig

    def __init__(
        self,
        *,
        model_directory_resolver: ModelDirectoryResolver | None = None,
        lookup_factory: LookupFactory | None = None,
        model_factory: ModelFactory | None = None,
    ) -> None:
        self._model_directory_resolver = (
            model_directory_resolver or UnavailableModelDirectoryResolver()
        )
        self._lookup_factory = lookup_factory or SqliteHivotoLookup
        self._model_factory = model_factory or default_model_factory
        self._bundles: dict[str, tuple[HivotoLookup, TokenProbabilityModel]] = {}

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: HivotoXgboostConfig,
    ) -> list[PredictionResult]:
        """Classify each person from its forename tokens in input order."""
        lookup, model = self._get_bundle(config.lookup_sha256)

        token_lists = [usable_forename_tokens(person.forenames) for person in people]
        flat_tokens = [token for tokens in token_lists for token in tokens]
        hits = lookup.get_many([_lookup_key(token) for token in flat_tokens])

        missing_tokens = [token for token in flat_tokens if _lookup_key(token) not in hits]
        unique_missing = list(dict.fromkeys(missing_tokens))
        probabilities = model.predict_female_probability([_model_key(t) for t in unique_missing])
        proba_by_token = dict(zip(unique_missing, probabilities, strict=True))

        return [self._predict_one(tokens, hits, proba_by_token) for tokens in token_lists]

    def _get_bundle(self, lookup_sha256: str) -> tuple[HivotoLookup, TokenProbabilityModel]:
        bundle = self._bundles.get(lookup_sha256)
        if bundle is None:
            directory = self._model_directory_resolver.materialize_directory(
                manifest_logical_type=HIVOTO_XGBOOST_MODEL_MANIFEST_LOGICAL_TYPE,
                member_logical_type=HIVOTO_XGBOOST_MODEL_FILE_LOGICAL_TYPE,
                manifest_sha256=lookup_sha256,
                expected_method_name="hivoto_xgboost",
            )
            lookup = self._lookup_factory(directory / LOOKUP_MEMBER_RELATIVE_PATH)
            model = self._model_factory(directory)
            bundle = (lookup, model)
            self._bundles[lookup_sha256] = bundle
        return bundle

    @staticmethod
    def _predict_one(
        tokens: list[str],
        hits: dict[str, tuple[str, str]],
        proba_by_token: dict[str, float],
    ) -> PredictionResult:
        labels: list[str] = []
        probabilities: list[float] = []
        for token in tokens:
            hit = hits.get(_lookup_key(token))
            if hit is not None:
                raw_gender = hit[0]
                labels.append(raw_gender if raw_gender in _HARD_LABELS_TO_PROBA else "unknown")
                probabilities.append(_HARD_LABELS_TO_PROBA.get(raw_gender, _DEFAULT_PROBA))
            else:
                proba = proba_by_token[token]
                labels.append("female" if proba >= 0.5 else "male")
                probabilities.append(proba)

        raw_label = _consensus(labels, probabilities) if tokens else NO_NAME_LABEL
        return normalize_raw_label(
            HIVOTO_XGBOOST_NORMALIZATION,
            raw_label,
            raw_output={
                "tokens": tokens,
                "token_results": labels,
                "token_probabilities": [round(value, 4) for value in probabilities],
            },
        )
