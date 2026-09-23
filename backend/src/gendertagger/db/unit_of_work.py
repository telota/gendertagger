"""SQLAlchemy implementation of the application unit-of-work contract."""

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from gendertagger.db.repositories.aggregation_repository import SqlAlchemyAggregationRepository
from gendertagger.db.repositories.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.db.repositories.auth_repository import SqlAlchemyAuthRepository
from gendertagger.db.repositories.dispatch_repository import SqlAlchemyDispatchRepository
from gendertagger.db.repositories.evaluation_repository import SqlAlchemyEvaluationRepository
from gendertagger.db.repositories.export_repository import SqlAlchemyExportRepository
from gendertagger.db.repositories.project_access_repository import SqlAlchemyProjectAccessRepository
from gendertagger.db.repositories.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.repositories.review_repository import SqlAlchemyReviewRepository
from gendertagger.db.repositories.run_repository import SqlAlchemyRunRepository
from gendertagger.db.repositories.user_repository import SqlAlchemyUserRepository
from gendertagger.db.session import SessionFactory
from gendertagger.services.ports.unit_of_work import UnitOfWork


class UnitOfWorkNotActiveError(RuntimeError):
    """Raised when transaction work is attempted outside an active context."""


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Own exactly one SQLAlchemy session and never commit implicitly."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Self:
        if self._session is not None:
            msg = "unit of work is already active"
            raise UnitOfWorkNotActiveError(msg)
        self._session = self._session_factory()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            session.rollback()
        finally:
            session.close()
            self._session = None

    @property
    def projects(self) -> SqlAlchemyProjectRepository:
        """Return project persistence bound to the active session."""
        return SqlAlchemyProjectRepository(self._require_session())

    @property
    def runs(self) -> SqlAlchemyRunRepository:
        """Return execution persistence bound to the active session."""
        return SqlAlchemyRunRepository(self._require_session())

    @property
    def aggregations(self) -> SqlAlchemyAggregationRepository:
        """Return aggregation persistence bound to the active session."""
        return SqlAlchemyAggregationRepository(self._require_session())

    @property
    def artifacts(self) -> SqlAlchemyArtifactRepository:
        """Return artifact persistence bound to the active session."""
        return SqlAlchemyArtifactRepository(self._require_session())

    @property
    def dispatches(self) -> SqlAlchemyDispatchRepository:
        """Return durable dispatch persistence bound to the active session."""
        return SqlAlchemyDispatchRepository(self._require_session())

    @property
    def evaluations(self) -> SqlAlchemyEvaluationRepository:
        """Return evaluation persistence bound to the active session."""
        return SqlAlchemyEvaluationRepository(self._require_session())

    @property
    def exports(self) -> SqlAlchemyExportRepository:
        """Return export persistence bound to the active session."""
        return SqlAlchemyExportRepository(self._require_session())

    @property
    def access(self) -> SqlAlchemyProjectAccessRepository:
        """Return project ownership and membership persistence bound to the active session."""
        return SqlAlchemyProjectAccessRepository(self._require_session())

    @property
    def users(self) -> SqlAlchemyUserRepository:
        """Return user persistence bound to the active session."""
        return SqlAlchemyUserRepository(self._require_session())

    @property
    def auth(self) -> SqlAlchemyAuthRepository:
        """Return local-account credential and session persistence bound to the active session."""
        return SqlAlchemyAuthRepository(self._require_session())

    @property
    def reviews(self) -> SqlAlchemyReviewRepository:
        """Return review persistence bound to the active session."""
        return SqlAlchemyReviewRepository(self._require_session())

    def commit(self) -> None:
        """Commit every repository write made through the active session."""
        self._require_session().commit()

    def rollback(self) -> None:
        """Roll back every repository write made through the active session."""
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            msg = "unit of work is not active"
            raise UnitOfWorkNotActiveError(msg)
        return self._session
