"""Canonical contracts for synchronous on-demand name classification."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from gendertagger.models.aggregation import AggregationOutcome, OverrideSource, VoteCounts
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    PredictionStatus,
)
from gendertagger.models.method import METHOD_NAME_PATTERN

MAX_CLASSIFY_BATCH_SIZE = 1000


class ClassifyNamesRequest(BaseModel):
    """Payload for on-demand synchronous name classification."""

    model_config = ConfigDict(extra="forbid")

    names: list[str] = Field(
        min_length=1,
        max_length=MAX_CLASSIFY_BATCH_SIZE,
        description="One or more non-blank names to classify.",
    )
    methods: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of registered method names to evaluate. "
            "Defaults to all runnable methods on this server."
        ),
    )
    method_configs: dict[str, dict[str, JsonValue]] | None = Field(
        default=None,
        description="Optional per-method configuration overrides.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_single_name(cls, data: Any) -> Any:
        if isinstance(data, dict):
            copied = dict(data)
            if "name" in copied:
                single_name = copied.pop("name")
                if "names" not in copied:
                    copied["names"] = [single_name]
            if isinstance(copied.get("names"), str):
                copied["names"] = [copied["names"]]
            return copied
        return data

    @field_validator("names")
    @classmethod
    def _validate_names(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values]
        if any(not v for v in cleaned):
            msg = "names must not contain empty or blank values"
            raise ValueError(msg)
        return cleaned

    @field_validator("methods")
    @classmethod
    def _validate_methods(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        for method in values:
            if not re.fullmatch(METHOD_NAME_PATTERN, method):
                msg = f"method name {method!r} is not a valid snake-case identifier"
                raise ValueError(msg)
        return values


class MethodClassification(BaseModel):
    """Outcome of one method for one name."""

    model_config = ConfigDict(extra="forbid")

    label: CanonicalLabel | None = Field(
        default=None,
        description="Canonical label ('male', 'female', 'unknown', 'institution') or null on abstain/error.",
    )
    status: PredictionStatus = Field(
        description="Outcome status: 'success', 'abstain', or 'error'."
    )
    method_confidence: float | None = Field(
        default=None,
        description="Method-specific confidence value, if reported by the method.",
    )
    raw_label: str | None = Field(
        default=None,
        description="Unnormalized raw label emitted by the adapter.",
    )
    error_message: str | None = Field(
        default=None,
        description="Diagnostic explanation when status is 'error'.",
    )


class AggregatedClassification(BaseModel):
    """Aggregated decision and certainty rating derived from method predictions."""

    model_config = ConfigDict(extra="forbid")

    label: CanonicalLabel | None = Field(
        default=None,
        description="Consensus canonical label or null when no consensus is reached.",
    )
    outcome: AggregationOutcome = Field(
        description="Aggregation outcome: 'decided', 'unresolved_tie', or 'no_data'.",
    )
    certainty_tier: CertaintyTier | None = Field(
        default=None,
        description="Certainty tier rating ('high', 'medium', 'low') derived from agreement and rater certainty.",
    )
    agreement_tier: AgreementTier | None = Field(
        default=None,
        description="Agreement tier: 'unanimous', 'strong', 'moderate', 'low', 'single_rater', 'no_consensus', 'no_answer'.",
    )
    agreement_score: float | None = Field(
        default=None,
        description="Agreement score rounded to three decimal places.",
    )
    vote_counts: VoteCounts = Field(
        description="Vote counts across pooled classification methods.",
    )
    override_source: OverrideSource | None = Field(
        default=None,
        description="Source of priority override if parenthetical qualifier or GND overrode the vote.",
    )


class NameClassificationResult(BaseModel):
    """Classification outcomes across methods for one input name."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="The input name string.")
    classifications: dict[str, MethodClassification] = Field(
        description="Map of method name to its classification result."
    )
    aggregated: AggregatedClassification = Field(
        description="Ensemble aggregation decision and certainty rating."
    )


class ClassifyNamesResponse(BaseModel):
    """Container for synchronous name classification results."""

    model_config = ConfigDict(extra="forbid")

    results: list[NameClassificationResult] = Field(
        description="Classification results in input name order."
    )
