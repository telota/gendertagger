"""FastAPI application composition root."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import partial
from importlib.metadata import version
from platform import python_version

from fastapi import FastAPI
from sqlalchemy import Engine

from gendertagger.api.authentication import (
    AuthenticationBackend,
    RejectAllAuthenticationBackend,
)
from gendertagger.api.errors import install_error_handlers
from gendertagger.api.request_ids import RequestIdMiddleware, generate_request_id
from gendertagger.api.router import create_api_router
from gendertagger.api.settings import AppSettings, load_settings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.method_registry import MethodRegistry
from gendertagger.services.projects import ProjectService
from gendertagger.services.runs import RunProvenance, RunService
from gendertagger.services.unit_of_work import UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage


def create_app(
    *,
    settings: AppSettings | None = None,
    unit_of_work_factory: UnitOfWorkFactory | None = None,
    authentication_backend: AuthenticationBackend | None = None,
    request_id_factory: Callable[[], str] | None = None,
) -> FastAPI:
    """Compose the API without opening a database connection.

    Args:
        settings: Explicit settings, or environment-backed settings when omitted.
        unit_of_work_factory: Optional application boundary override for tests.
        authentication_backend: Provider-neutral authentication implementation.
        request_id_factory: Optional server-owned correlation-ID generator.

    Returns:
        A configured FastAPI application whose owned engine is disposed at shutdown.
    """
    resolved_settings = settings or load_settings()
    application_version = version("gendertagger")
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
    project_service = ProjectService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(resolved_settings.artifact_root),
        parser=TeiPersonParser(),
        clock=partial(datetime.now, UTC),
        max_upload_bytes=resolved_settings.max_tei_upload_bytes,
        import_batch_record_count=resolved_settings.tei_import_batch_record_count,
    )
    method_registry = MethodRegistry()
    run_service = RunService(
        unit_of_work_factory=unit_of_work_factory,
        method_registry=method_registry,
        provenance=RunProvenance(
            code_git_commit=resolved_settings.code_git_commit,
            application_version=application_version,
            python_version=python_version(),
            dependency_lock_sha256=resolved_settings.dependency_lock_sha256,
            container_image_digest=resolved_settings.container_image_digest,
        ),
    )
    aggregation_service = AggregationService(unit_of_work_factory)
    annotation_service = AnnotationService(unit_of_work_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    application = FastAPI(
        title="gendertagger API",
        version=application_version,
        lifespan=lifespan,
    )
    application.add_middleware(
        RequestIdMiddleware,
        request_id_factory=request_id_factory or generate_request_id,
    )
    install_error_handlers(application)
    application.include_router(create_api_router())
    application.state.settings = resolved_settings
    application.state.unit_of_work_factory = unit_of_work_factory
    application.state.authentication_backend = authentication_backend
    application.state.project_service = project_service
    application.state.aggregation_service = aggregation_service
    application.state.annotation_service = annotation_service
    application.state.method_registry = method_registry
    application.state.run_service = run_service
    return application
