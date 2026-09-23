"""FastAPI application composition root."""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from functools import partial
from importlib.metadata import version
from platform import python_version

from fastapi import FastAPI
from sqlalchemy import Engine

from gendertagger.api.authentication import (
    AuthenticationBackend,
    DatabaseAuthenticationBackend,
)
from gendertagger.api.errors import install_error_handlers
from gendertagger.api.request_ids import RequestIdMiddleware, generate_request_id
from gendertagger.api.router import (
    create_api_router,
    create_password_change_exempt_router,
    create_unauthenticated_router,
)
from gendertagger.api.settings import AppSettings, load_settings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.project import SnapshotImportLimits
from gendertagger.services.aggregations import AggregationService
from gendertagger.services.annotations import AnnotationService
from gendertagger.services.authentication import AuthenticationService, SessionLifetimePolicy
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.evaluations import EvaluationService
from gendertagger.services.execution import RunScheduler
from gendertagger.services.exports import ExportService
from gendertagger.services.lookup_assets import RegisteredLookupAssetResolver
from gendertagger.services.method_registry import default_method_registry
from gendertagger.services.model_assets import RegisteredModelDirectoryResolver
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.password_hashing import Argon2PasswordHasher
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory
from gendertagger.services.project_access import ProjectAccessService
from gendertagger.services.projects import ProjectService
from gendertagger.services.review_items import ReviewItemService
from gendertagger.services.runs import RunProvenance, RunService
from gendertagger.storage.local import LocalArtifactStorage
from gendertagger.utils.logging import configure_logging


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
    configure_logging()
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
    authentication_service = AuthenticationService(
        unit_of_work_factory=unit_of_work_factory,
        password_hasher=Argon2PasswordHasher(),
        clock=partial(datetime.now, UTC),
        session_lifetime=SessionLifetimePolicy(
            idle=timedelta(seconds=resolved_settings.session_idle_seconds),
            keep_signed_in_idle=timedelta(
                seconds=resolved_settings.session_keep_signed_in_idle_seconds
            ),
            max_lifetime=timedelta(seconds=resolved_settings.session_max_lifetime_seconds),
        ),
    )
    if authentication_backend is None:
        authentication_backend = DatabaseAuthenticationBackend(authentication_service)
    cursor_codec = CursorCodec()
    artifact_storage = LocalArtifactStorage(resolved_settings.artifact_root)
    project_access_service = ProjectAccessService(
        unit_of_work_factory=unit_of_work_factory,
        cursor_codec=cursor_codec,
    )
    project_service = ProjectService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=artifact_storage,
        parser=TeiPersonParser(),
        cursor_codec=cursor_codec,
        clock=partial(datetime.now, UTC),
        max_upload_bytes=resolved_settings.max_archive_member_bytes,
        max_total_upload_bytes=resolved_settings.max_snapshot_upload_bytes,
        import_limits=SnapshotImportLimits(
            max_member_count=resolved_settings.max_snapshot_source_files,
            max_member_expanded_bytes=resolved_settings.max_archive_member_bytes,
            max_total_expanded_bytes=resolved_settings.max_archive_expanded_bytes,
            max_compression_ratio=resolved_settings.max_archive_compression_ratio,
            max_record_count=resolved_settings.max_import_record_count,
            max_cell_bytes=resolved_settings.max_tabular_cell_bytes,
        ),
    )
    lookup_asset_resolver = RegisteredLookupAssetResolver(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=artifact_storage,
    )
    method_registry = default_method_registry(
        lookup_asset_resolver,
        RegisteredModelDirectoryResolver(
            lookup_asset_resolver=lookup_asset_resolver,
            cache_root=resolved_settings.model_cache_root,
        ),
    )
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
        cursor_codec=cursor_codec,
    )
    aggregation_service = AggregationService(
        unit_of_work_factory=unit_of_work_factory,
        cursor_codec=cursor_codec,
        clock=partial(datetime.now, UTC),
    )
    evaluation_service = EvaluationService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=artifact_storage,
        cursor_codec=cursor_codec,
        clock=partial(datetime.now, UTC),
    )
    export_service = ExportService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=artifact_storage,
        cursor_codec=cursor_codec,
        clock=partial(datetime.now, UTC),
    )
    annotation_service = AnnotationService(unit_of_work_factory)
    review_item_service = ReviewItemService(
        unit_of_work_factory=unit_of_work_factory,
        cursor_codec=cursor_codec,
    )
    run_scheduler = RunScheduler(
        unit_of_work_factory=unit_of_work_factory,
        method_registry=method_registry,
        clock=partial(datetime.now, UTC),
    )
    classification_service = DirectClassificationService(
        method_registry=method_registry,
        unit_of_work_factory=unit_of_work_factory,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
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
    application.include_router(create_password_change_exempt_router())
    application.include_router(create_unauthenticated_router())
    application.state.settings = resolved_settings
    application.state.database_engine = engine
    application.state.unit_of_work_factory = unit_of_work_factory
    application.state.authentication_backend = authentication_backend
    application.state.authentication_service = authentication_service
    application.state.project_service = project_service
    application.state.project_access_service = project_access_service
    application.state.aggregation_service = aggregation_service
    application.state.evaluation_service = evaluation_service
    application.state.export_service = export_service
    application.state.annotation_service = annotation_service
    application.state.method_registry = method_registry
    application.state.run_service = run_service
    application.state.review_item_service = review_item_service
    application.state.run_scheduler = run_scheduler
    application.state.classification_service = classification_service
    return application
