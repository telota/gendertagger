"""Application transaction boundary contracts."""

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self, TypeAlias

from gendertagger.services.ports.aggregation_repository import AggregationRepository
from gendertagger.services.ports.artifact_repository import ArtifactRepository
from gendertagger.services.ports.auth_repository import AuthRepository
from gendertagger.services.ports.dispatch_repository import DispatchRepository
from gendertagger.services.ports.evaluation_repository import EvaluationRepository
from gendertagger.services.ports.export_repository import ExportRepository
from gendertagger.services.ports.game_repository import GameRepository
from gendertagger.services.ports.project_access_repository import ProjectAccessRepository
from gendertagger.services.ports.project_repository import ProjectRepository
from gendertagger.services.ports.review_repository import ReviewRepository
from gendertagger.services.ports.run_repository import RunRepository
from gendertagger.services.ports.settings_repository import SettingsRepository
from gendertagger.services.ports.team_repository import TeamRepository
from gendertagger.services.ports.user_preferences_repository import UserPreferencesRepository
from gendertagger.services.ports.user_repository import UserRepository


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

    @property
    def games(self) -> GameRepository:
        """Return game-round persistence bound to the current transaction."""
        ...

    @property
    def settings(self) -> SettingsRepository:
        """Return deployment settings persistence bound to the current transaction."""
        ...

    @property
    def teams(self) -> TeamRepository:
        """Return team persistence bound to the current transaction."""
        ...

    @property
    def user_preferences(self) -> UserPreferencesRepository:
        """Return account preferences persistence bound to the current transaction."""
        ...

    def commit(self) -> None:
        """Commit all repository writes in the current transaction."""
        ...

    def rollback(self) -> None:
        """Roll back all repository writes in the current transaction."""
        ...


UnitOfWorkFactory: TypeAlias = Callable[[], UnitOfWork]
