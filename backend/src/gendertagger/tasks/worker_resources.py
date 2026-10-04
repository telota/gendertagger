"""Lazy worker infrastructure with explicit process, fork, and shutdown ownership.

Task constructors remain in their defining modules. Only their database pool,
artifact storage, and classification assets are shared here; every unit of work
creates its own session, including public-classification heartbeat threads.
"""

from __future__ import annotations

import atexit
import os
from dataclasses import dataclass
from threading import RLock
from typing import Any

from celery.signals import worker_process_init, worker_process_shutdown, worker_shutdown
from sqlalchemy.orm import Session

from gendertagger.config.settings import ClassificationRuntimeSettings, RuntimeSettings
from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.models.run import WorkerProvenance
from gendertagger.services.classification import DirectClassificationService
from gendertagger.services.lookup_assets import RegisteredLookupAssetResolver
from gendertagger.services.method_registry import MethodRegistry, default_method_registry
from gendertagger.services.model_assets import RegisteredModelDirectoryResolver
from gendertagger.services.runtime_provenance import capture_worker_provenance
from gendertagger.storage.local import LocalArtifactStorage


@dataclass(frozen=True, slots=True)
class WorkerClassificationResources:
    """Classification-only assets and evidence captured in the executing process."""

    settings: ClassificationRuntimeSettings
    lookup_resolver: RegisteredLookupAssetResolver
    model_resolver: RegisteredModelDirectoryResolver
    method_registry: MethodRegistry
    worker_provenance: WorkerProvenance


class WorkerResources:
    """Own one lazy worker's pool and reject inherited or disposed resource use."""

    def __init__(self, settings: RuntimeSettings) -> None:
        self._process_id = os.getpid()
        self._closed = False
        self._settings = settings
        self._engine = create_database_engine(settings.database_url.get_secret_value())
        self._session_factory = create_session_factory(self._engine)
        self._artifact_storage: LocalArtifactStorage | None = None
        self._classification: WorkerClassificationResources | None = None
        self._direct_classification_service: DirectClassificationService | None = None

    def _require_owned_process(self) -> None:
        if self._process_id != os.getpid():
            msg = "worker resources cannot be used in an inherited process"
            raise RuntimeError(msg)
        if self._closed:
            msg = "worker resources have been shut down"
            raise RuntimeError(msg)

    @property
    def settings(self) -> RuntimeSettings:
        """Return the runtime snapshot without requiring classification build settings."""
        with _resource_lock:
            self._require_owned_process()
            return self._settings

    def create_unit_of_work(self) -> SqlAlchemyUnitOfWork:
        """Create a fresh transaction scope, never a shared or thread-local session."""
        with _resource_lock:
            self._require_owned_process()
            return SqlAlchemyUnitOfWork(self._create_session)

    def _create_session(self) -> Session:
        with _resource_lock:
            self._require_owned_process()
            return self._session_factory()

    @property
    def artifact_storage(self) -> LocalArtifactStorage:
        """Share local storage only among task families that actually use artifacts."""
        with _resource_lock:
            self._require_owned_process()
            if self._artifact_storage is None:
                self._artifact_storage = LocalArtifactStorage(self._settings.artifact_root)
            return self._artifact_storage

    @property
    def classification(self) -> WorkerClassificationResources:
        """Lazily require build identity and capture actual worker process evidence."""
        with _resource_lock:
            self._require_owned_process()
            if self._classification is None:
                # Pin shared runtime values to this owner's snapshot. Only the
                # classification build identity is loaded when it is first needed.
                settings = ClassificationRuntimeSettings(**self._settings.model_dump())
                lookup_resolver = RegisteredLookupAssetResolver(
                    unit_of_work_factory=self.create_unit_of_work,
                    artifact_storage=self.artifact_storage,
                )
                model_resolver = RegisteredModelDirectoryResolver(
                    lookup_asset_resolver=lookup_resolver,
                    cache_root=settings.model_cache_root,
                )
                self._classification = WorkerClassificationResources(
                    settings=settings,
                    lookup_resolver=lookup_resolver,
                    model_resolver=model_resolver,
                    method_registry=default_method_registry(lookup_resolver, model_resolver),
                    worker_provenance=capture_worker_provenance(
                        code_git_commit=settings.code_git_commit,
                        dependency_lock_sha256=settings.dependency_lock_sha256,
                        container_image_digest=settings.container_image_digest,
                    ),
                )
            return self._classification

    @property
    def direct_classification_service(self) -> DirectClassificationService:
        """Retain the bounded public prediction cache only when that family is used."""
        with _resource_lock:
            self._require_owned_process()
            if self._direct_classification_service is None:
                self._direct_classification_service = DirectClassificationService(
                    method_registry=self.classification.method_registry,
                    unit_of_work_factory=self.create_unit_of_work,
                )
            return self._direct_classification_service

    def _dispose(self) -> None:
        if not self._closed:
            self._closed = True
            # In a child, replace the inherited pool without closing connections
            # that are still live in the parent. Owned shutdown closes idle pools.
            self._engine.dispose(close=self._process_id == os.getpid())
            self._classification = None
            self._artifact_storage = None
            self._direct_classification_service = None


_resource_lock = RLock()
_resources: WorkerResources | None = None


def get_worker_resources() -> WorkerResources:
    """Return the single process owner, safely initializing it across task threads."""
    global _resources
    with _resource_lock:
        if _resources is not None and _resources._process_id != os.getpid():
            _resources._dispose()
            _resources = None
        if _resources is None:
            settings = RuntimeSettings()  # type: ignore[call-arg]  # Environment sources.
            _resources = WorkerResources(settings)
        return _resources


def reset_worker_resources() -> None:
    """Dispose the current owner once and permit clean lazy reinitialization.

    Call only after worker operations and heartbeat threads have stopped. Celery
    shutdown and process-init signals use this same boundary; tests reset it after
    stopping their in-process worker rather than clearing executor caches.
    """
    global _resources
    with _resource_lock:
        resources = _resources
        _resources = None
        if resources is not None:
            resources._dispose()


def _prepare_worker_fork() -> None:
    # Do not fork midway through owner or classification-resource initialization.
    _resource_lock.acquire()


def _finish_worker_fork() -> None:
    _resource_lock.release()


def _reset_after_fork() -> None:
    global _resource_lock
    # An inherited lock can belong to a thread that does not exist in the child.
    _resource_lock = RLock()
    reset_worker_resources()


def _initialize_worker_process(**_signal_arguments: Any) -> None:
    reset_worker_resources()


def _shutdown_worker_resources(**_signal_arguments: Any) -> None:
    reset_worker_resources()


os.register_at_fork(
    before=_prepare_worker_fork,
    after_in_parent=_finish_worker_fork,
    after_in_child=_reset_after_fork,
)
atexit.register(reset_worker_resources)
worker_process_init.connect(_initialize_worker_process, weak=False)
worker_process_shutdown.connect(_shutdown_worker_resources, weak=False)
worker_shutdown.connect(_shutdown_worker_resources, weak=False)
