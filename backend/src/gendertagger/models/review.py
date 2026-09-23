"""Canonical human-review contracts."""

from enum import StrEnum
from typing import Self, TypeVar
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

_VocabularyT = TypeVar("_VocabularyT", bound=StrEnum)


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


class AttributedAnnotation(Annotation):
    """An immutable annotation with its reviewer's display name for attribution."""

    reviewer_display_name: str = Field(min_length=1, max_length=200)


class AnnotationHistory(ReviewState):
    """One person's current review state and complete annotation chain, newest first.

    The chain holds every annotation that ever applied to the person, so the first entry is
    the current head and each entry supersedes the one after it. ``revision`` is the value a
    client sends as ``expected_revision`` to append the next decision.
    """

    annotations: list[AttributedAnnotation]

    @model_validator(mode="after")
    def _validate_chain(self) -> Self:
        revisions = [annotation.resulting_revision for annotation in self.annotations]
        if revisions != list(range(self.revision, 0, -1)):
            msg = "annotations must hold every revision of the stream, newest first"
            raise ValueError(msg)
        if self.annotations and self.annotations[0].id != self.current_annotation_id:
            msg = "the newest annotation must be the current annotation"
            raise ValueError(msg)
        return self


class ReviewItemSort(StrEnum):
    """Server-side ordering available to the review queue.

    ``uncertainty`` applies the versioned ``review_triage_v1`` policy, which
    returns contested, weakly supported, thinly evidenced, conflicting, and
    failed records before confident ones. ``tei_id`` returns the plain register
    order for predictable full traversal.
    """

    uncertainty = "uncertainty"
    tei_id = "tei_id"


class ReviewItemQuery(BaseModel):
    """Server-side filters, ordering, and cursor controls for one aggregation.

    The three collection filters match a result whose value is any of the listed values, and an
    empty collection matches every value. Their values are kept in vocabulary order, so a cursor
    stays valid whichever order a client lists them in.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    aggregation_id: UUID
    final_label: CanonicalLabel | None = None
    certainty_tiers: tuple[CertaintyTier, ...] = Field(
        default=(),
        description="Match results in any of these certainty tiers; empty matches every tier.",
    )
    agreement_tiers: tuple[AgreementTier, ...] = Field(
        default=(),
        description="Match results in any of these agreement tiers; empty matches every tier.",
    )
    workflow_states: tuple[ReviewWorkflowState, ...] = Field(
        default=(),
        description="Match people in any of these review states; empty matches every state.",
    )
    has_authority_conflict: bool | None = None
    method_name: str | None = Field(default=None, pattern=METHOD_NAME_PATTERN)
    method_label: CanonicalLabel | None = None
    prediction_status: PredictionStatus | None = None
    has_prediction_error: bool | None = None
    q: str | None = Field(default=None, min_length=1, max_length=200)
    sort: ReviewItemSort = ReviewItemSort.uncertainty
    limit: int = Field(default=100, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)

    @field_validator("certainty_tiers", "agreement_tiers", "workflow_states")
    @classmethod
    def _order_alternatives(cls, values: tuple[_VocabularyT, ...]) -> tuple[_VocabularyT, ...]:
        if len(set(values)) != len(values):
            msg = "filter values must not repeat"
            raise ValueError(msg)
        return tuple(sorted(values, key=_vocabulary_position))

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


class ReviewSummaryGroup(BaseModel):
    """Number of one aggregation's results that share a tier, label, and review-state combination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    certainty_tier: CertaintyTier
    agreement_tier: AgreementTier
    workflow_state: ReviewWorkflowState
    final_label: CanonicalLabel | None = Field(
        default=None,
        description=(
            "The same latest-human-annotation-otherwise-machine-label resolution as the "
            "human_overrides export policy, so a label count matches what that export would write."
        ),
    )
    review_action: ReviewAction | None = Field(
        default=None,
        description="The current annotation's action, or null for a person nobody has annotated.",
    )
    result_count: int = Field(ge=1)

    @model_validator(mode="after")
    def _validate_review_state_consistency(self) -> Self:
        if self.workflow_state is ReviewWorkflowState.unreviewed:
            if self.review_action is not None:
                msg = "an unreviewed group must not carry a review action"
                raise ValueError(msg)
        elif self.review_action is None:
            msg = "a reviewed or deferred group requires a review action"
            raise ValueError(msg)
        elif self.workflow_state is ReviewWorkflowState.deferred:
            if self.review_action is not ReviewAction.defer:
                msg = "a deferred group's review action must be defer"
                raise ValueError(msg)
        elif self.review_action not in (ReviewAction.verify, ReviewAction.correct):
            msg = "a reviewed group's review action must be verify or correct"
            raise ValueError(msg)
        if self.workflow_state is ReviewWorkflowState.reviewed and self.final_label is None:
            msg = "a reviewed group requires a final label"
            raise ValueError(msg)
        return self


class ReviewSummary(BaseModel):
    """Result counts of one completed aggregation by certainty, agreement, and review state.

    ``groups`` lists every combination that has results exactly once, in the declaration order of
    the three vocabularies, so a combination that is absent has none. Certainty and agreement
    are immutable for a completed aggregation; the review states are those at read time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    aggregation_execution_id: UUID
    result_count: int = Field(ge=0)
    last_annotated_at: UtcDatetime | None = Field(
        default=None,
        description="Most recent review activity among the aggregation's people, or null before it.",
    )
    groups: list[ReviewSummaryGroup]

    @model_validator(mode="after")
    def _validate_groups(self) -> Self:
        combinations = [
            (
                group.certainty_tier,
                group.agreement_tier,
                group.workflow_state,
                group.final_label,
                group.review_action,
            )
            for group in self.groups
        ]
        if len(set(combinations)) != len(combinations):
            msg = "review summary groups must not repeat a combination"
            raise ValueError(msg)
        if sum(group.result_count for group in self.groups) != self.result_count:
            msg = "review summary groups must add up to result_count"
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


def _vocabulary_position(member: StrEnum) -> int:
    """Return a member's position in its vocabulary's declaration order."""
    return list(type(member)).index(member)
