"""SQLAlchemy implementation of the application unit-of-work contract."""

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from gendertagger.db.project_repository import SqlAlchemyProjectRepository
from gendertagger.db.run_repository import SqlAlchemyRunRepository
from gendertagger.db.session import SessionFactory
from gendertagger.services.unit_of_work import UnitOfWork


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
