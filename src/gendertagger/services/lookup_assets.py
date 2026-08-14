"""Application services for registered content-addressed method lookup assets."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from pydantic import JsonValue

from gendertagger.methods.base import MethodDependencyError
from gendertagger.models.artifact import Artifact, ArtifactCreate
from gendertagger.services.artifact_repository import AmbiguousArtifactError
from gendertagger.services.artifact_storage import ArtifactStorage
from gendertagger.services.unit_of_work import UnitOfWorkFactory


class LookupAssetRegistrationService:
    """Store and register immutable method source or lookup files."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        artifact_storage: ArtifactStorage,
        max_byte_size: int,
    ) -> None:
        if max_byte_size <= 0:
            msg = "lookup artifact byte limit must be positive"
            raise ValueError(msg)
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_storage = artifact_storage
        self._max_byte_size = max_byte_size

    def register_file(
        self,
        path: Path,
        *,
        logical_type: str,
        media_type: str,
        metadata: dict[str, JsonValue] | None = None,
    ) -> Artifact:
        """Store exact bytes and idempotently register their global metadata."""
        with path.open("rb") as source:
            stored = self._artifact_storage.store(
                source,
                max_byte_size=self._max_byte_size,
            )
        with self._unit_of_work_factory() as unit_of_work:
            existing = unit_of_work.artifacts.get_artifact_by_sha256(
                logical_type,
                stored.sha256,
            )
            if existing is not None:
                return existing
            artifact = unit_of_work.artifacts.add_artifact(
                ArtifactCreate(
                    logical_type=logical_type,
                    storage_uri=stored.storage_uri,
                    sha256=stored.sha256,
                    byte_size=stored.byte_size,
                    media_type=media_type,
                    metadata={} if metadata is None else metadata,
                )
            )
            unit_of_work.commit()
            return artifact

    def materialize(self, artifact: Artifact) -> Path:
        """Return the verified immutable bytes registered for ``artifact``."""
        return self._artifact_storage.materialize(artifact.storage_uri)


class RegisteredLookupAssetResolver:
    """Resolve registered lookup digests to verified process-local paths."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_storage = artifact_storage
        self._paths: dict[tuple[str, str], Path] = {}
        self._lock = Lock()

    def materialize(self, logical_type: str, sha256: str) -> Path:
        """Resolve and verify an artifact once per process.

        Raises:
            MethodDependencyError: If no matching registration exists or the
                registered bytes cannot be materialized with integrity.
        """
        cache_key = (logical_type, sha256)
        cached = self._paths.get(cache_key)
        if cached is not None:
            return cached

        with self._lock:
            cached = self._paths.get(cache_key)
            if cached is not None:
                return cached
            try:
                with self._unit_of_work_factory() as unit_of_work:
                    artifact = unit_of_work.artifacts.get_artifact_by_sha256(
                        logical_type,
                        sha256,
                    )
            except AmbiguousArtifactError as error:
                raise MethodDependencyError(str(error)) from error
            if artifact is None:
                msg = f"registered lookup artifact {logical_type}:{sha256} does not exist"
                raise MethodDependencyError(msg)
            try:
                path = self._artifact_storage.materialize(artifact.storage_uri)
            except (OSError, RuntimeError) as error:
                msg = f"registered lookup artifact {logical_type}:{sha256} is unavailable"
                raise MethodDependencyError(msg) from error
            self._paths[cache_key] = path
            return path
