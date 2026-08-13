"""Canonical human-review contracts."""

from enum import StrEnum


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
