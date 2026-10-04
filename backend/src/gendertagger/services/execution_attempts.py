"""Positive delivery-attempt bounds shared by asynchronous artifact executors."""


def execution_attempt_may_retry(attempt_count: int, max_attempts: int) -> bool:
    """Validate one-based attempt bounds and return the unclassified-error retry budget.

    Attempts beyond the configured maximum remain terminal, as on duplicate or
    delayed deliveries. Resource-specific permanent failures, retry exceptions,
    rollback scopes, and fresh terminal claims stay with each executor.
    """
    if attempt_count <= 0:
        msg = "attempt_count must be positive"
        raise ValueError(msg)
    if max_attempts <= 0:
        msg = "max_attempts must be positive"
        raise ValueError(msg)
    return attempt_count < max_attempts
