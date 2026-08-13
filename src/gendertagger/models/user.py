"""Canonical authenticated-user contracts."""

from enum import StrEnum


class Role(StrEnum):
    """Global v1 authorization role assigned to a user."""

    viewer = "viewer"
    reviewer = "reviewer"
    operator = "operator"
    admin = "admin"
