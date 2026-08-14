"""Shared loading and batch inference plumbing for Hugging Face name classifiers.

Two published methods (``hf_distilbert``, ``hf_genderize``) each wrap a
distinct fine-tuned sequence-classification model applied to one forename
token at a time, consistent with every other name-based classifier adapter.
Only tokenize/forward/argmax plumbing is shared here; per-model index-to-label
polarity and normalization stay adapter-owned. See ADR-0012 and ADR-0024.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol, cast

from gendertagger.methods.base import MethodDependencyError


class HfTransformerBackend(Protocol):
    """Batch argmax classification over one loaded sequence-classification model."""

    def classify_many(self, names: Sequence[str]) -> list[int]:
        """Return the argmax class index for each input name, in order."""
        ...


BackendFactory = Callable[[Path], HfTransformerBackend]


class _TransformersBackend:
    """Deterministic batch inference over a locally materialized model directory."""

    def __init__(self, directory: Path) -> None:
        try:
            import torch  # pyright: ignore[reportMissingImports]
            from transformers import (  # pyright: ignore[reportMissingImports]
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as error:  # pragma: no cover - exercised only without the extra
            msg = (
                "hf transformer methods require the 'transformers' extra "
                "(install transformers, torch)"
            )
            raise MethodDependencyError(msg) from error
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            directory,
            local_files_only=True,
        )
        self._model.eval()

    def classify_many(self, names: Sequence[str]) -> list[int]:
        """Return the deterministic argmax label index for each input name."""
        if not names:
            return []
        inputs = self._tokenizer(
            list(names),
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        with self._torch.no_grad():
            logits = self._model(**inputs).logits
        return [int(index) for index in logits.argmax(dim=-1).tolist()]


def default_backend_factory(directory: Path) -> HfTransformerBackend:
    """Load a locally materialized model directory as a batch classification backend.

    Raises:
        MethodDependencyError: If the ``transformers`` extra is not installed.
    """
    return cast(HfTransformerBackend, _TransformersBackend(directory))
