"""Application transaction boundary contracts."""

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self, TypeAlias

from gendertagger.services.aggregation_repository import AggregationRepository
from gendertagger.services.artifact_repository import ArtifactRepository
from gendertagger.services.auth_repository import AuthRepository
from gendertagger.services.dispatch_repository import DispatchRepository
from gendertagger.services.evaluation_repository import EvaluationRepository
from gendertagger.services.export_repository import ExportRepository
from gendertagger.services.project_access_repository import ProjectAccessRepository
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
    def dispatches(self) -> DispatchRepository:
        """Return durable dispatch persistence bound to the current transaction."""
        ...

    @property
    def evaluations(self) -> EvaluationRepository:
        """Return evaluation persistence bound to the current transaction."""
        ...

    @property
    def exports(self) -> ExportRepository:
        """Return export persistence bound to the current transaction."""
        ...

    @property
    def access(self) -> ProjectAccessRepository:
        """Return project ownership and membership persistence bound to the current transaction."""
        ...

    @property
    def users(self) -> UserRepository:
        """Return user persistence bound to the current transaction."""
        ...

    @property
    def auth(self) -> AuthRepository:
        """Return local-account credential and session persistence bound to the current transaction."""
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


UnitOfWorkFactory: TypeAlias = Callable[[], UnitOfWork]
