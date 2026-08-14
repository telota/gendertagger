"""Adapter for the Hugging Face ``imranali291/genderize`` BERT-cased model.

Provisioning registers every model file plus a manifest that pins them by
content into one immutable multi-file artifact. Workers materialize that
manifest once per digest, classify each usable forename token through the
model, and reduce per-token labels with the shared name-token consensus. The
raw label is normalized against the frozen ``hf_genderize_v1`` profile. See
ADR-0012, ADR-0023, and ADR-0024.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from gendertagger.methods.base import LookupMethodConfig
from gendertagger.methods.hf_transformer import (
    BackendFactory,
    HfTransformerBackend,
    default_backend_factory,
)
from gendertagger.methods.model_manifest import (
    ModelDirectoryResolver,
    UnavailableModelDirectoryResolver,
)
from gendertagger.methods.name_tokens import consensus_label, usable_forename_tokens
from gendertagger.methods.normalization import HF_GENDERIZE_NORMALIZATION, normalize_raw_label
from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput

HF_GENDERIZE_MODEL_MANIFEST_LOGICAL_TYPE: Final = "hf_genderize_model_manifest"
HF_GENDERIZE_MODEL_FILE_LOGICAL_TYPE: Final = "hf_genderize_model_file"
HF_GENDERIZE_MODEL_SCHEMA_VERSION: Final = "hf_genderize_model_v1"
HF_GENDERIZE_MODEL_COMPILER_VERSION: Final = "hf_model_manifest_compiler_v1"

_PRIORITY: Final[tuple[str, ...]] = ("male", "female")
_MALE_LABELS: Final[frozenset[str]] = frozenset({"male"})
_FEMALE_LABELS: Final[frozenset[str]] = frozenset({"female"})
# imranali291/genderize: label/index 0 is female, index 1 is male.
_INDEX_LABELS: Final[tuple[str, str]] = ("female", "male")


class HfGenderizeConfig(LookupMethodConfig):
    """Resolved configuration selecting a materialized genderize model by digest."""


class HfGenderizeMethod:
    """Classify forename tokens through the ``imranali291/genderize`` model."""

    descriptor = MethodDescriptor(
        name="hf_genderize",
        implementation_version="hf_genderize_v1",
        normalization_version=HF_GENDERIZE_NORMALIZATION.normalization_version,
    )
    config_model = HfGenderizeConfig

    def __init__(
        self,
        *,
        model_directory_resolver: ModelDirectoryResolver | None = None,
        backend_factory: BackendFactory | None = None,
    ) -> None:
        self._model_directory_resolver = (
            model_directory_resolver or UnavailableModelDirectoryResolver()
        )
        self._backend_factory = backend_factory or default_backend_factory
        self._backends: dict[str, HfTransformerBackend] = {}

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: HfGenderizeConfig,
    ) -> list[PredictionResult]:
        """Classify each person from its forename tokens in input order."""
        backend = self._get_backend(config.lookup_sha256)
        token_lists = [usable_forename_tokens(person.forenames) for person in people]
        flat_tokens = [token for tokens in token_lists for token in tokens]
        indices = backend.classify_many(flat_tokens) if flat_tokens else []
        labels = iter(_INDEX_LABELS[index] for index in indices)
        results: list[PredictionResult] = []
        for tokens in token_lists:
            token_results = [next(labels) for _ in tokens]
            raw_label = consensus_label(
                token_results,
                priority=_PRIORITY,
                male_labels=_MALE_LABELS,
                female_labels=_FEMALE_LABELS,
            )
            results.append(
                normalize_raw_label(
                    HF_GENDERIZE_NORMALIZATION,
                    raw_label,
                    raw_output={"tokens": tokens, "token_results": token_results},
                )
            )
        return results

    def _get_backend(self, lookup_sha256: str) -> HfTransformerBackend:
        backend = self._backends.get(lookup_sha256)
        if backend is None:
            directory = self._model_directory_resolver.materialize_directory(
                manifest_logical_type=HF_GENDERIZE_MODEL_MANIFEST_LOGICAL_TYPE,
                member_logical_type=HF_GENDERIZE_MODEL_FILE_LOGICAL_TYPE,
                manifest_sha256=lookup_sha256,
                expected_method_name="hf_genderize",
            )
            backend = self._backend_factory(directory)
            self._backends[lookup_sha256] = backend
        return backend
