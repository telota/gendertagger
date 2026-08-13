"""Canonical human-review contracts."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.common import UtcDatetime


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
