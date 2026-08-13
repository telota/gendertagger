"""Canonical human-review contracts."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gendertagger.models.aggregation import AggregationOutcome, OverrideSource
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    CertaintyTier,
    PredictionStatus,
)
from gendertagger.models.common import UtcDatetime
from gendertagger.models.method import METHOD_NAME_PATTERN


class ReviewAction(StrEnum):
    """Append-only editorial action recorded by an annotation."""

    verify = "verify"
    correct = "correct"
    defer = "defer"


class ReviewWorkflowState(StrEnum):
    """Current rebuildable workflow projection for a review stream."""

    unreviewed = "unreviewed"
    reviewed = "reviewed"
    deferred = "deferred"


class AnnotationCreate(BaseModel):
    """Optimistically concurrent command that appends one human decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    tei_id: str = Field(min_length=1)
    action: ReviewAction
    label: CanonicalLabel | None = None
    comment: str | None = None
    aggregated_result_id: UUID | None = None
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_action_label(self) -> Self:
        _validate_review_action_label(self.action, self.label)
        return self


class Annotation(BaseModel):
    """Canonical read model for one immutable human annotation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    snapshot_id: UUID
    person_record_id: UUID
    tei_id: str
    action: ReviewAction
    label: CanonicalLabel | None = None
    reviewer_user_id: UUID
    comment: str | None = None
    aggregated_result_id: UUID | None = None
    supersedes_annotation_id: UUID | None = None
    resulting_revision: int = Field(gt=0)
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_action_label(self) -> Self:
        _validate_review_action_label(self.action, self.label)
        return self


class ReviewState(BaseModel):
    """Canonical read model for a rebuildable review concurrency projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    person_record_id: UUID
    tei_id: str
    revision: int = Field(ge=0)
    workflow_state: ReviewWorkflowState
    current_annotation_id: UUID | None = None

    @model_validator(mode="after")
    def _validate_revision_head(self) -> Self:
        if self.revision == 0:
            if self.current_annotation_id is not None:
                msg = "an unreviewed state must not have a current annotation"
                raise ValueError(msg)
            if self.workflow_state is not ReviewWorkflowState.unreviewed:
                msg = "revision zero requires the unreviewed workflow state"
                raise ValueError(msg)
        elif self.current_annotation_id is None:
            msg = "a reviewed revision requires a current annotation"
            raise ValueError(msg)
        elif self.workflow_state is ReviewWorkflowState.unreviewed:
            msg = "a reviewed revision must not use the unreviewed workflow state"
            raise ValueError(msg)
        return self


class ReviewItemQuery(BaseModel):
    """Server-side filters and cursor controls for one exact aggregation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    aggregation_id: UUID
    final_label: CanonicalLabel | None = None
    certainty_tier: CertaintyTier | None = None
    agreement_tier: AgreementTier | None = None
    workflow_state: ReviewWorkflowState | None = None
    has_authority_conflict: bool | None = None
    method_name: str | None = Field(default=None, pattern=METHOD_NAME_PATTERN)
    method_label: CanonicalLabel | None = None
    prediction_status: PredictionStatus | None = None
    has_prediction_error: bool | None = None
    q: str | None = Field(default=None, min_length=1, max_length=200)
    limit: int = Field(default=100, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)

    @field_validator("q")
    @classmethod
    def _normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            msg = "q must not be blank"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _validate_method_filters(self) -> Self:
        if self.method_name is None and (
            self.method_label is not None or self.prediction_status is not None
        ):
            msg = "method_label and prediction_status require method_name"
            raise ValueError(msg)
        return self


class ReviewMethodResult(BaseModel):
    """Selected method outcome included in a review-item summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_name: str = Field(pattern=METHOD_NAME_PATTERN)
    status: PredictionStatus
    label: CanonicalLabel | None = None


class ReviewItem(BaseModel):
    """Queryable person, machine decision, and current review projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    aggregation_execution_id: UUID
    aggregated_result_id: UUID
    snapshot_id: UUID
    person_record_id: UUID
    tei_id: str
    surname: str | None = None
    forenames: list[str] = Field(default_factory=list)
    aggregation_outcome: AggregationOutcome
    machine_label: CanonicalLabel | None = None
    final_label: CanonicalLabel | None = None
    agreement_tier: AgreementTier
    certainty_tier: CertaintyTier
    override_source: OverrideSource | None = None
    has_authority_conflict: bool
    has_prediction_error: bool
    workflow_state: ReviewWorkflowState
    review_revision: int = Field(ge=0)
    current_annotation_id: UUID | None = None
    selected_method_result: ReviewMethodResult | None = None


def _validate_review_action_label(
    action: ReviewAction,
    label: CanonicalLabel | None,
) -> None:
    if action in {ReviewAction.verify, ReviewAction.correct} and label is None:
        msg = "verify and correct actions require a canonical label"
        raise ValueError(msg)
    if action is ReviewAction.defer and label is not None:
        msg = "a defer action must not have a label"
        raise ValueError(msg)
