"""Application-level persistence and resource-state failures."""


class ResourceNotFoundError(LookupError):
    """Raised when a command targets a resource that does not exist."""


class DuplicateUsernameError(ValueError):
    """Raised when local-account provisioning reuses an existing normalized username."""


class InvalidResourceStateError(RuntimeError):
    """Raised when a resource cannot perform the requested state transition."""


class ImmutableResourceError(InvalidResourceStateError):
    """Raised before attempting to mutate an immutable persisted resource."""


class ReviewConflictError(InvalidResourceStateError):
    """Raised when an annotation command uses a stale review revision."""

    def __init__(self, *, expected_revision: int, current_revision: int) -> None:
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__(
            f"stale review revision {expected_revision}; current revision is {current_revision}"
        )
