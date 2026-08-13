"""Application transaction boundary contracts."""

from types import TracebackType
from typing import Protocol, Self


class UnitOfWork(Protocol):
    """Caller-controlled transaction spanning application repositories."""

    def __enter__(self) -> Self:
        """Open one transaction-scoped repository context."""
        ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back uncommitted work and close the transaction context."""
        ...

    def commit(self) -> None:
        """Commit all repository writes in the current transaction."""
        ...

    def rollback(self) -> None:
        """Roll back all repository writes in the current transaction."""
        ...
