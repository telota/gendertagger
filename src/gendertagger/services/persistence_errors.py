"""Application-level persistence and resource-state failures."""


class ResourceNotFoundError(LookupError):
    """Raised when a command targets a resource that does not exist."""


class InvalidResourceStateError(RuntimeError):
    """Raised when a resource cannot perform the requested state transition."""


class ImmutableResourceError(InvalidResourceStateError):
    """Raised before attempting to mutate an immutable persisted resource."""
