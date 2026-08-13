"""Canonical classification contracts."""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CanonicalLabel(StrEnum):
    """Normalized labels shared by every classification method."""

    male = "male"
    female = "female"
    unknown = "unknown"
    institution = "institution"


class PredictionStatus(StrEnum):
    """Outcome status of one method prediction."""

    success = "success"
    abstain = "abstain"
    error = "error"


class CertaintyTier(StrEnum):
    """Reference-pipeline certainty assigned to an aggregated result."""

    high = "high"
    low = "low"
    contested = "contested"
    single = "single"
    uncertain = "uncertain"
    no_data = "no_data"


class AgreementTier(StrEnum):
    """Categorical agreement among methods that supplied an answer."""

    unanimous = "unanimous"
    strong_majority = "strong_majority"
    weak_majority = "weak_majority"
    no_consensus = "no_consensus"
    single_rater = "single_rater"
    no_answer = "no_answer"


class PredictionResult(BaseModel):
    """Validated output from one method for one person.

    A successful result always has a canonical label, including the substantive
    ``unknown`` label. Abstentions and technical errors have no label. Confidence
    remains method-specific and is not globally calibrated.
    """

    model_config = ConfigDict(extra="forbid")

    label: CanonicalLabel | None
    status: PredictionStatus
    method_confidence: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description=(
            "Finite method-specific confidence in the method's declared range; "
            "not globally calibrated."
        ),
    )
    raw_label: str | None = Field(
        default=None,
        description="Unnormalized label returned by the classification method.",
    )
    raw_output: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw method output retained for audit and reproducibility.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Normalization and execution provenance for this result.",
    )

    @model_validator(mode="after")
    def _validate_status_label(self) -> Self:
        if self.status is PredictionStatus.success and self.label is None:
            msg = "a successful prediction requires a canonical label"
            raise ValueError(msg)
        if (
            self.status in {PredictionStatus.abstain, PredictionStatus.error}
            and self.label is not None
        ):
            msg = "an abstained or failed prediction must not have a label"
            raise ValueError(msg)
        return self
