"""PostgreSQL engine and SQLAlchemy session composition."""

from collections.abc import Callable
from typing import TypeAlias

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

SessionFactory: TypeAlias = Callable[[], Session]


def create_database_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create the supported PostgreSQL engine without opening a connection."""
    engine = create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )
    if engine.dialect.name != "postgresql":
        engine.dispose()
        msg = "gendertagger persistence requires a PostgreSQL database URL"
        raise ValueError(msg)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create transaction sessions whose lifecycle is owned by a unit of work."""
    if engine.dialect.name != "postgresql":
        msg = "gendertagger persistence requires a PostgreSQL engine"
        raise ValueError(msg)
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
