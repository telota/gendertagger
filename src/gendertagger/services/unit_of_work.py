"""Application transaction boundary contracts."""

from types import TracebackType
from typing import Protocol, Self

from gendertagger.services.aggregation_repository import AggregationRepository
from gendertagger.services.artifact_repository import ArtifactRepository
from gendertagger.services.project_repository import ProjectRepository
from gendertagger.services.review_repository import ReviewRepository
from gendertagger.services.run_repository import RunRepository
from gendertagger.services.user_repository import UserRepository


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

    @property
    def projects(self) -> ProjectRepository:
        """Return project persistence bound to the current transaction."""
        ...

    @property
    def runs(self) -> RunRepository:
        """Return execution persistence bound to the current transaction."""
        ...

    @property
    def aggregations(self) -> AggregationRepository:
        """Return aggregation persistence bound to the current transaction."""
        ...

    @property
    def artifacts(self) -> ArtifactRepository:
        """Return artifact persistence bound to the current transaction."""
        ...

    @property
    def users(self) -> UserRepository:
        """Return user persistence bound to the current transaction."""
        ...

    @property
    def reviews(self) -> ReviewRepository:
        """Return review persistence bound to the current transaction."""
        ...

    def commit(self) -> None:
        """Commit all repository writes in the current transaction."""
        ...

    def rollback(self) -> None:
        """Roll back all repository writes in the current transaction."""
        ...
