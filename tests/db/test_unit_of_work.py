import pytest
from sqlalchemy.orm import Session

from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork, UnitOfWorkNotActiveError


class TrackingSession(Session):
    def __init__(self) -> None:
        super().__init__()
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.close_count += 1


class TrackingSessionFactory:
    def __init__(self, session: TrackingSession) -> None:
        self.session = session
        self.call_count = 0

    def __call__(self) -> Session:
        self.call_count += 1
        return self.session


def test_unit_of_work_never_commits_implicitly() -> None:
    session = TrackingSession()
    factory = TrackingSessionFactory(session)

    with SqlAlchemyUnitOfWork(factory):
        pass

    assert factory.call_count == 1
    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert session.close_count == 1


def test_unit_of_work_commits_only_on_explicit_request() -> None:
    session = TrackingSession()
    unit_of_work = SqlAlchemyUnitOfWork(TrackingSessionFactory(session))

    with unit_of_work:
        unit_of_work.commit()

    assert session.commit_count == 1
    assert session.rollback_count == 1
    assert session.close_count == 1


def test_unit_of_work_rejects_calls_outside_active_context() -> None:
    unit_of_work = SqlAlchemyUnitOfWork(TrackingSessionFactory(TrackingSession()))

    with pytest.raises(UnitOfWorkNotActiveError, match="not active"):
        unit_of_work.commit()
    with pytest.raises(UnitOfWorkNotActiveError, match="not active"):
        unit_of_work.rollback()


def test_unit_of_work_rejects_nested_entry() -> None:
    unit_of_work = SqlAlchemyUnitOfWork(TrackingSessionFactory(TrackingSession()))

    with unit_of_work, pytest.raises(UnitOfWorkNotActiveError, match="already active"):
        unit_of_work.__enter__()


def test_session_composition_accepts_only_postgresql() -> None:
    engine = create_database_engine("postgresql+psycopg://user:password@localhost/gendertagger")
    try:
        factory = create_session_factory(engine)
        session = factory()
        try:
            assert session.autoflush is False
            assert session.expire_on_commit is False
        finally:
            session.close()
    finally:
        engine.dispose()


@pytest.mark.parametrize("database_url", ["sqlite+pysqlite:///:memory:", "sqlite://"])
def test_engine_composition_rejects_non_postgresql(database_url: str) -> None:
    with pytest.raises(ValueError, match="requires a PostgreSQL database URL"):
        create_database_engine(database_url)


def test_session_factory_rejects_non_postgresql_engine() -> None:
    from sqlalchemy import create_engine

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with pytest.raises(ValueError, match="requires a PostgreSQL engine"):
            create_session_factory(engine)
    finally:
        engine.dispose()
