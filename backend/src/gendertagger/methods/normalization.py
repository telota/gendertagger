"""Pure, versioned raw-label normalization for method adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from gendertagger.models.classification import (
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)


class NormalizationReason(StrEnum):
    """Provenance reason for the status produced during normalization."""

    mapped = "mapped"
    missing_raw_label = "missing_raw_label"
    no_input = "no_input"
    technical_error = "technical_error"
    unparseable = "unparseable"


@dataclass(frozen=True, slots=True)
class LabelNormalizationProfile:
    """Immutable adapter-owned mapping from raw labels to canonical outcomes."""

    method_name: str
    normalization_version: str
    label_map: Mapping[str, CanonicalLabel]
    abstain_labels: frozenset[str] = frozenset()
    error_labels: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """Validate and defensively freeze profile values."""
        if not self.method_name.strip():
            msg = "normalization profile method_name must not be blank"
            raise ValueError(msg)
        if not self.normalization_version.strip():
            msg = "normalization profile version must not be blank"
            raise ValueError(msg)

        label_map = dict(self.label_map)
        abstain_labels = frozenset(self.abstain_labels)
        error_labels = frozenset(self.error_labels)
        all_keys = set(label_map) | abstain_labels | error_labels
        noncanonical_keys = sorted(key for key in all_keys if key != _normalization_key(key))
        if noncanonical_keys:
            msg = (
                f"normalization profile keys must be stripped and case-folded: {noncanonical_keys}"
            )
            raise ValueError(msg)

        overlap = (set(label_map) & abstain_labels) | (set(label_map) & error_labels)
        overlap |= abstain_labels & error_labels
        if overlap:
            msg = f"normalization profile outcomes overlap for: {sorted(overlap)}"
            raise ValueError(msg)

        object.__setattr__(self, "label_map", MappingProxyType(label_map))
        object.__setattr__(self, "abstain_labels", abstain_labels)
        object.__setattr__(self, "error_labels", error_labels)


def normalize_raw_label(
    profile: LabelNormalizationProfile,
    raw_label: str | None,
    *,
    method_confidence: float | None = None,
    raw_output: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> PredictionResult:
    """Normalize one adapter label without mutating supplied evidence.

    Known ambiguous labels are successful substantive ``unknown`` predictions.
    Missing, no-input, and unparseable values abstain. Explicit technical-error
    sentinels become error results. Comparison strips and case-folds strings,
    while ``raw_label`` preserves the adapter's exact value.

    Args:
        profile: Versioned mapping owned by the method adapter.
        raw_label: Exact label emitted by the adapter, or ``None`` when absent.
        method_confidence: Optional method-specific confidence to preserve.
        raw_output: Additional raw method evidence to copy into the result.
        metadata: Additional provenance to copy into the result.

    Returns:
        A canonical prediction result with normalization provenance.
    """
    if raw_label is None:
        label = None
        status = PredictionStatus.abstain
        reason = NormalizationReason.missing_raw_label
    else:
        key = _normalization_key(raw_label)
        if key in profile.error_labels:
            label = None
            status = PredictionStatus.error
            reason = NormalizationReason.technical_error
        elif key in profile.abstain_labels:
            label = None
            status = PredictionStatus.abstain
            reason = NormalizationReason.no_input
        elif key in profile.label_map:
            label = profile.label_map[key]
            status = PredictionStatus.success
            reason = NormalizationReason.mapped
        else:
            label = None
            status = PredictionStatus.abstain
            reason = NormalizationReason.unparseable

    result_metadata = dict(metadata) if metadata is not None else {}
    result_metadata["normalization_version"] = profile.normalization_version
    result_metadata["normalization_reason"] = reason.value

    return PredictionResult(
        label=label,
        status=status,
        method_confidence=method_confidence,
        raw_label=raw_label,
        raw_output=dict(raw_output) if raw_output is not None else {},
        metadata=result_metadata,
    )


def _normalization_key(value: str) -> str:
    return value.strip().casefold()


_COMMON_ABSTAIN_LABELS = frozenset({"", "nan", "no_answer", "no_gnd", "no_name"})
_COMMON_ERROR_LABELS = frozenset({"error"})
_BINARY_LABELS = {
    "female": CanonicalLabel.female,
    "male": CanonicalLabel.male,
}

PARENTHETICAL_QUALIFIER_NORMALIZATION = LabelNormalizationProfile(
    method_name="parenthetical_qualifier",
    normalization_version="parenthetical_qualifier_v1",
    label_map={
        **_BINARY_LABELS,
        "institution": CanonicalLabel.institution,
        "unknown": CanonicalLabel.unknown,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS,
    error_labels=_COMMON_ERROR_LABELS,
)

GND_NORMALIZATION = LabelNormalizationProfile(
    method_name="gnd",
    normalization_version="gnd_v1",
    label_map={
        **_BINARY_LABELS,
        "institution": CanonicalLabel.institution,
        "männlich": CanonicalLabel.male,
        "organisation": CanonicalLabel.institution,
        "unbekannt": CanonicalLabel.unknown,
        "unknown": CanonicalLabel.unknown,
        "weiblich": CanonicalLabel.female,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS,
    error_labels=_COMMON_ERROR_LABELS,
)

GENDER_GUESSER_NORMALIZATION = LabelNormalizationProfile(
    method_name="gender_guesser",
    normalization_version="gender_guesser_v1",
    label_map={
        **_BINARY_LABELS,
        "andy": CanonicalLabel.unknown,
        "conflict": CanonicalLabel.unknown,
        "mostly_female": CanonicalLabel.female,
        "mostly_male": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS,
    error_labels=_COMMON_ERROR_LABELS,
)

WIKI_GENDERSORT_NORMALIZATION = LabelNormalizationProfile(
    method_name="wiki_gendersort",
    normalization_version="wiki_gendersort_v1",
    label_map={
        **_BINARY_LABELS,
        "conflict": CanonicalLabel.unknown,
        "f": CanonicalLabel.female,
        "m": CanonicalLabel.male,
        "uni": CanonicalLabel.unknown,
        "unisex": CanonicalLabel.unknown,
        "unk": CanonicalLabel.unknown,
        "unknown": CanonicalLabel.unknown,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS | {"ini"},
    error_labels=_COMMON_ERROR_LABELS,
)

HIVOTO_NORMALIZATION = LabelNormalizationProfile(
    method_name="hivoto",
    normalization_version="hivoto_v1",
    label_map={
        **_BINARY_LABELS,
        "andy": CanonicalLabel.unknown,
        "conflict": CanonicalLabel.unknown,
        "mostly_female": CanonicalLabel.female,
        "mostly_male": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS,
    error_labels=_COMMON_ERROR_LABELS,
)

NOMQUAMGENDER_NORMALIZATION = LabelNormalizationProfile(
    method_name="nomquamgender",
    normalization_version="nomquamgender_v1",
    label_map={
        **_BINARY_LABELS,
        "conflict": CanonicalLabel.unknown,
        "uncertain": CanonicalLabel.unknown,
        "unknown": CanonicalLabel.unknown,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS,
    error_labels=_COMMON_ERROR_LABELS,
)

HF_DISTILBERT_NORMALIZATION = LabelNormalizationProfile(
    method_name="hf_distilbert",
    normalization_version="hf_distilbert_v1",
    label_map={
        **_BINARY_LABELS,
        "0": CanonicalLabel.male,
        "1": CanonicalLabel.female,
        "conflict": CanonicalLabel.unknown,
        "label_0": CanonicalLabel.male,
        "label_1": CanonicalLabel.female,
        "unknown": CanonicalLabel.unknown,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS,
    error_labels=_COMMON_ERROR_LABELS,
)

HF_GENDERIZE_NORMALIZATION = LabelNormalizationProfile(
    method_name="hf_genderize",
    normalization_version="hf_genderize_v1",
    label_map={
        **_BINARY_LABELS,
        "0": CanonicalLabel.female,
        "1": CanonicalLabel.male,
        "conflict": CanonicalLabel.unknown,
        "label_0": CanonicalLabel.female,
        "label_1": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS,
    error_labels=_COMMON_ERROR_LABELS,
)

LOCAL_LLM_NORMALIZATION = LabelNormalizationProfile(
    method_name="local_llm",
    normalization_version="local_llm_v1",
    label_map={
        **_BINARY_LABELS,
        "institution": CanonicalLabel.institution,
        "organisation": CanonicalLabel.institution,
        "unknown": CanonicalLabel.unknown,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS,
    error_labels=_COMMON_ERROR_LABELS,
)

HIVOTO_XGBOOST_NORMALIZATION = LabelNormalizationProfile(
    method_name="hivoto_xgboost",
    normalization_version="hivoto_xgboost_v1",
    label_map={
        **_BINARY_LABELS,
        "andy": CanonicalLabel.unknown,
        "conflict": CanonicalLabel.unknown,
        "mostly_female": CanonicalLabel.female,
        "mostly_male": CanonicalLabel.male,
        "unknown": CanonicalLabel.unknown,
    },
    abstain_labels=_COMMON_ABSTAIN_LABELS,
    error_labels=_COMMON_ERROR_LABELS,
)

NORMALIZATION_PROFILES: Mapping[str, LabelNormalizationProfile] = MappingProxyType(
    {
        profile.method_name: profile
        for profile in (
            PARENTHETICAL_QUALIFIER_NORMALIZATION,
            GND_NORMALIZATION,
            GENDER_GUESSER_NORMALIZATION,
            WIKI_GENDERSORT_NORMALIZATION,
            HIVOTO_NORMALIZATION,
            NOMQUAMGENDER_NORMALIZATION,
            HF_DISTILBERT_NORMALIZATION,
            HF_GENDERIZE_NORMALIZATION,
            LOCAL_LLM_NORMALIZATION,
            HIVOTO_XGBOOST_NORMALIZATION,
        )
    }
)
