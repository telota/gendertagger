"""FastAPI application composition root."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from importlib.metadata import version

from fastapi import FastAPI
from sqlalchemy import Engine

from gendertagger.api.authentication import (
    AuthenticationBackend,
    RejectAllAuthenticationBackend,
)
from gendertagger.api.router import create_api_router
from gendertagger.api.settings import AppSettings, load_settings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.services.unit_of_work import UnitOfWorkFactory


def create_app(
    *,
    settings: AppSettings | None = None,
    unit_of_work_factory: UnitOfWorkFactory | None = None,
    authentication_backend: AuthenticationBackend | None = None,
) -> FastAPI:
    """Compose the API without opening a database connection.

    Args:
        settings: Explicit settings, or environment-backed settings when omitted.
        unit_of_work_factory: Optional application boundary override for tests.
        authentication_backend: Provider-neutral authentication implementation.

    Returns:
        A configured FastAPI application whose owned engine is disposed at shutdown.
    """
    resolved_settings = settings or load_settings()
    engine: Engine | None = None
    if unit_of_work_factory is None:
        engine = create_database_engine(
            resolved_settings.database_url.get_secret_value(),
            echo=resolved_settings.database_echo,
        )
        session_factory = create_session_factory(engine)
        unit_of_work_factory = partial(SqlAlchemyUnitOfWork, session_factory)
    if authentication_backend is None:
        authentication_backend = RejectAllAuthenticationBackend()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    application = FastAPI(
        title="gendertagger API",
        version=version("gendertagger"),
        lifespan=lifespan,
    )
    application.include_router(create_api_router())
    application.state.settings = resolved_settings
    application.state.unit_of_work_factory = unit_of_work_factory
    application.state.authentication_backend = authentication_backend
    return application
