"""Application use cases for projects and source-preserving TEI imports."""

from collections.abc import Callable
from datetime import datetime
from typing import BinaryIO
from uuid import UUID

from gendertagger.ingestion.tei import TeiImportError, TeiPersonParser
from gendertagger.models.api import CursorPage
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.person import PersonInput, PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
    SnapshotImportRequest,
    TeiImportProfile,
)
from gendertagger.services.artifact_storage import ArtifactStorage
from gendertagger.services.pagination import CursorCodec
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.unit_of_work import UnitOfWorkFactory


class ProjectService:
    """Orchestrate project resources and synchronous Phase 3 TEI imports."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        artifact_storage: ArtifactStorage,
        parser: TeiPersonParser,
        cursor_codec: CursorCodec,
        clock: Callable[[], datetime],
        max_upload_bytes: int,
        import_batch_record_count: int,
    ) -> None:
        if max_upload_bytes <= 0:
            msg = "max_upload_bytes must be positive"
            raise ValueError(msg)
        if import_batch_record_count <= 0:
            msg = "import_batch_record_count must be positive"
            raise ValueError(msg)
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_storage = artifact_storage
        self._parser = parser
        self._cursor_codec = cursor_codec
        self._clock = clock
        self._max_upload_bytes = max_upload_bytes
        self._import_batch_record_count = import_batch_record_count

    def create_project(self, command: ProjectCreate) -> Project:
        """Create one long-lived editorial project and commit it atomically."""
        with self._unit_of_work_factory() as unit_of_work:
            project = unit_of_work.projects.add_project(command)
            unit_of_work.commit()
        return project

    def get_project(self, project_id: UUID) -> Project:
        """Return one project or raise a resource-level not-found failure."""
        with self._unit_of_work_factory() as unit_of_work:
            project = unit_of_work.projects.get_project(project_id)
        if project is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        return project

    def get_snapshot(self, snapshot_id: UUID) -> DatasetSnapshot:
        """Return one dataset snapshot or raise a resource-level not-found failure."""
        with self._unit_of_work_factory() as unit_of_work:
            snapshot = unit_of_work.projects.get_snapshot(snapshot_id)
        if snapshot is None:
            msg = f"dataset snapshot {snapshot_id} does not exist"
            raise ResourceNotFoundError(msg)
        return snapshot

    def list_people(
        self,
        snapshot_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[PersonRecord]:
        """Return one stable opaque-cursor page of snapshot people."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot.status is not DatasetSnapshotStatus.ready:
            msg = f"dataset snapshot {snapshot_id} is not ready"
            raise InvalidResourceStateError(msg)
        resource = f"snapshot_people:{snapshot_id}"
        position = (
            self._cursor_codec.decode(cursor, expected_resource=resource)
            if cursor is not None
            else None
        )
        with self._unit_of_work_factory() as unit_of_work:
            records = unit_of_work.projects.list_person_records(
                snapshot_id,
                limit=limit + 1,
                after_tei_id=position.sort_value if position is not None else None,
                after_person_record_id=position.id if position is not None else None,
            )
        has_more = len(records) > limit
        items = list(records[:limit])
        next_cursor = None
        if has_more:
            last_item = items[-1]
            next_cursor = self._cursor_codec.encode(
                resource=resource,
                sort_value=last_item.tei_id,
                resource_id=last_item.id,
            )
        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    def import_snapshot(
        self,
        *,
        project_id: UUID,
        source: BinaryIO,
        command: SnapshotImportRequest,
    ) -> DatasetSnapshot:
        """Preserve, parse, and persist an uploaded TEI source as one immutable snapshot.

        The Phase 3 transport waits for this implementation to finish but still returns the
        persisted command resource. Later Celery execution can call the same lifecycle steps.
        A parser failure is persisted as a failed snapshot rather than partially becoming ready.
        """
        self.get_project(project_id)
        stored_artifact = self._artifact_storage.store(
            source,
            max_byte_size=self._max_upload_bytes,
        )

        with self._unit_of_work_factory() as unit_of_work:
            artifact = unit_of_work.artifacts.add_artifact(
                ArtifactCreate(
                    logical_type="source_tei",
                    storage_uri=stored_artifact.storage_uri,
                    sha256=stored_artifact.sha256,
                    byte_size=stored_artifact.byte_size,
                    media_type="application/tei+xml",
                    project_id=project_id,
                    metadata={"import_profile": command.profile.value},
                )
            )
            snapshot = unit_of_work.projects.add_snapshot(
                DatasetSnapshotCreate(
                    project_id=project_id,
                    source_artifact_id=artifact.id,
                    source_sha256=artifact.sha256,
                    parser_version=self._parser.version_for_profile(command.profile),
                    import_config=command.model_dump(mode="json"),
                )
            )
            unit_of_work.commit()

        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.projects.begin_snapshot_import(snapshot.id)
            unit_of_work.commit()

        try:
            self._import_people(snapshot.id, artifact.storage_uri, command.profile)
        except TeiImportError as error:
            with self._unit_of_work_factory() as unit_of_work:
                failed_snapshot = unit_of_work.projects.fail_snapshot_import(
                    snapshot.id,
                    failure_diagnostic=str(error),
                )
                unit_of_work.commit()
            return failed_snapshot

        with self._unit_of_work_factory() as unit_of_work:
            ready_snapshot = unit_of_work.projects.complete_snapshot_import(
                snapshot.id,
                ready_at=self._clock(),
            )
            unit_of_work.commit()
        return ready_snapshot

    def _import_people(
        self,
        snapshot_id: UUID,
        storage_uri: str,
        profile: TeiImportProfile,
    ) -> None:
        batch: list[PersonInput] = []
        with self._artifact_storage.open(storage_uri) as source:
            for person in self._parser.iter_people(source, profile=profile):
                batch.append(person)
                if len(batch) == self._import_batch_record_count:
                    self._persist_person_batch(snapshot_id, batch)
                    batch.clear()
        if batch:
            self._persist_person_batch(snapshot_id, batch)

    def _persist_person_batch(self, snapshot_id: UUID, batch: list[PersonInput]) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.projects.add_person_records(snapshot_id, batch)
            unit_of_work.commit()
