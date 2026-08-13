"""Canonical contracts for reference aggregation decisions."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
)


class AggregationOutcome(StrEnum):
    """Decision state produced by reference aggregation before certainty assignment."""

    decided = "decided"
    unresolved_tie = "unresolved_tie"
    no_data = "no_data"


class OverrideSource(StrEnum):
    """Authority source that superseded the pooled reference vote."""

    parenthetical_qualifier = "parenthetical_qualifier"
    gnd = "gnd"


class VoteCounts(BaseModel):
    """Complete counts for the four canonical labels in the pooled vote."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    male: int = Field(default=0, ge=0)
    female: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)
    institution: int = Field(default=0, ge=0)

    @property
    def total(self) -> int:
        """Return the number of pooled methods that cast a vote."""
        return self.male + self.female + self.unknown + self.institution

    def for_label(self, label: CanonicalLabel) -> int:
        """Return the pooled vote count for ``label``."""
        if label is CanonicalLabel.male:
            return self.male
        if label is CanonicalLabel.female:
            return self.female
        if label is CanonicalLabel.unknown:
            return self.unknown
        return self.institution


class ReferenceAggregationDecision(BaseModel):
    """Immutable priority, vote, and tie outcome for ``reference_v1``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: AggregationOutcome
    label: CanonicalLabel | None
    pooled_vote_counts: VoteCounts = Field(default_factory=VoteCounts)
    tied_labels: tuple[CanonicalLabel, ...] = ()
    override_source: OverrideSource | None = None
    override_agreeing_count: int | None = Field(default=None, ge=0)
    override_comparison_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_decision_invariants(self) -> Self:
        if len(set(self.tied_labels)) != len(self.tied_labels):
            msg = "tied_labels must not contain duplicates"
            raise ValueError(msg)

        if self.outcome is AggregationOutcome.decided:
            if self.label is None:
                msg = "a decided aggregation requires a canonical label"
                raise ValueError(msg)
            if self.tied_labels:
                msg = "a decided aggregation must not contain tied_labels"
                raise ValueError(msg)
        else:
            if self.label is not None:
                msg = "an unresolved or empty aggregation must not contain a label"
                raise ValueError(msg)
            if self.override_source is not None:
                msg = "only a decided aggregation may have an override source"
                raise ValueError(msg)

        if self.outcome is AggregationOutcome.unresolved_tie:
            if len(self.tied_labels) < 2:
                msg = "an unresolved tie requires at least two tied labels"
                raise ValueError(msg)
            if self.pooled_vote_counts.total == 0:
                msg = "an unresolved tie requires pooled votes"
                raise ValueError(msg)
        elif self.tied_labels:
            msg = "tied_labels are only valid for an unresolved tie"
            raise ValueError(msg)

        if self.outcome is AggregationOutcome.no_data and self.pooled_vote_counts.total != 0:
            msg = "a no-data aggregation must not contain pooled votes"
            raise ValueError(msg)
        if (
            self.outcome is AggregationOutcome.decided
            and self.override_source is None
            and self.pooled_vote_counts.total == 0
        ):
            msg = "a non-override decision requires pooled votes"
            raise ValueError(msg)

        agreeing_count = self.override_agreeing_count
        comparison_count = self.override_comparison_count
        if self.override_source is None:
            if agreeing_count is not None or comparison_count is not None:
                msg = "override support counts require an override source"
                raise ValueError(msg)
        else:
            if agreeing_count is None or comparison_count is None:
                msg = "an override source requires both support counts"
                raise ValueError(msg)
            if agreeing_count > comparison_count:
                msg = "override agreeing count must not exceed comparison count"
                raise ValueError(msg)

        return self


class ReferenceAggregationResult(ReferenceAggregationDecision):
    """Fully assessed ``reference_v1`` result with agreement and certainty."""

    agreement_score: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    agreement_tier: AgreementTier
    certainty_tier: CertaintyTier

    @model_validator(mode="after")
    def _validate_assessment_invariants(self) -> Self:
        if self.outcome is AggregationOutcome.no_data:
            if self.agreement_score is not None:
                msg = "a no-data result must not have an agreement score"
                raise ValueError(msg)
            if self.agreement_tier is not AgreementTier.no_answer:
                msg = "a no-data result requires the no-answer agreement tier"
                raise ValueError(msg)
            if self.certainty_tier is not CertaintyTier.no_data:
                msg = "a no-data result requires the no-data certainty tier"
                raise ValueError(msg)
            return self

        if self.agreement_score is None:
            msg = "a result with usable evidence requires an agreement score"
            raise ValueError(msg)
        if self.agreement_tier is AgreementTier.no_answer:
            msg = "a result with usable evidence must not use the no-answer agreement tier"
            raise ValueError(msg)
        if self.outcome is AggregationOutcome.unresolved_tie:
            if self.agreement_tier is not AgreementTier.no_consensus:
                msg = "an unresolved tie requires the no-consensus agreement tier"
                raise ValueError(msg)
            if self.certainty_tier is not CertaintyTier.contested:
                msg = "an unresolved tie requires the contested certainty tier"
                raise ValueError(msg)
        if self.override_source is not None and self.certainty_tier is not CertaintyTier.high:
            msg = "a reference authority override requires high certainty"
            raise ValueError(msg)
        return self
