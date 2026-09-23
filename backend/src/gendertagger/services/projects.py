"""Application use cases for projects and durable snapshot-import acceptance."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import PurePosixPath
from typing import BinaryIO
from uuid import UUID

from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.api import CursorPage
from gendertagger.models.artifact import ArtifactCreate
from gendertagger.models.dispatch import SnapshotDispatchCreate
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.person import PersonRecord
from gendertagger.models.project import (
    AccessibleProject,
    DatasetSnapshot,
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotImportRequest,
    SnapshotImportTaskMessage,
    SnapshotSourceMember,
    SnapshotSourceMemberCreate,
    SnapshotUploadLimits,
    SourceFormat,
    SourceManifestMember,
    SourceManifestV1,
    SourcePackaging,
    import_profile_for_source_format,
    normalize_source_member_logical_name,
)
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.models.user import ProjectRole
from gendertagger.services.pagination import (
    CursorCodec,
    decode_creation_position,
    newest_first_page,
)
from gendertagger.services.ports.artifact_storage import ArtifactStorage
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

_MANIFEST_MEDIA_TYPE = "application/vnd.gendertagger.source-manifest+json"


@dataclass(frozen=True, slots=True)
class SnapshotUpload:
    """One request-bound upload part with its untrusted client filename."""

    source: BinaryIO
    filename: str
    media_type: str | None = None


class InvalidSnapshotSourceError(ValueError):
    """Raised when upload parts do not match the declared source contract."""


class SnapshotUploadTooLargeError(ValueError):
    """Raised when a valid source collection exceeds its aggregate upload limit."""


@dataclass(frozen=True, slots=True)
class _StagedUpload:
    logical_name: str
    media_type: str
    storage_uri: str
    sha256: str
    byte_size: int


class ProjectService:
    """Orchestrate projects and durably accept asynchronous snapshot imports."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        artifact_storage: ArtifactStorage,
        parser: TeiPersonParser,
        cursor_codec: CursorCodec,
        clock: Callable[[], datetime],
        max_upload_bytes: int,
        max_total_upload_bytes: int | None = None,
        import_limits: SnapshotImportLimits | None = None,
    ) -> None:
        if max_upload_bytes <= 0:
            msg = "max_upload_bytes must be positive"
            raise ValueError(msg)
        resolved_total_upload_bytes = (
            max_upload_bytes if max_total_upload_bytes is None else max_total_upload_bytes
        )
        if resolved_total_upload_bytes <= 0:
            msg = "max_total_upload_bytes must be positive"
            raise ValueError(msg)
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_storage = artifact_storage
        self._parser = parser
        self._cursor_codec = cursor_codec
        self._clock = clock
        self._max_upload_bytes = max_upload_bytes
        self._max_total_upload_bytes = resolved_total_upload_bytes
        self._import_limits = import_limits or SnapshotImportLimits(
            max_member_count=128,
            max_member_expanded_bytes=max_upload_bytes,
            max_total_expanded_bytes=resolved_total_upload_bytes,
            max_compression_ratio=100.0,
            max_record_count=1_000_000,
            max_cell_bytes=1024 * 1024,
        )

    def upload_limits(self) -> SnapshotUploadLimits:
        """Return the upload and import bounds this service enforces on every snapshot import."""
        return SnapshotUploadLimits(
            max_upload_part_bytes=self._max_upload_bytes,
            max_total_upload_bytes=self._max_total_upload_bytes,
            import_limits=self._import_limits,
        )

    def create_project(self, command: ProjectCreate, *, creator_user_id: UUID) -> AccessibleProject:
        """Create one editorial project with its creator as operator, atomically (ADR-0033)."""
        with self._unit_of_work_factory() as unit_of_work:
            project = unit_of_work.projects.add_project(command)
            unit_of_work.access.set_member_role(project.id, creator_user_id, ProjectRole.operator)
            unit_of_work.commit()
        return AccessibleProject(**project.model_dump(), current_user_role=ProjectRole.operator)

    def get_project(self, project_id: UUID) -> Project:
        """Return one project or raise a resource-level not-found failure."""
        with self._unit_of_work_factory() as unit_of_work:
            project = unit_of_work.projects.get_project(project_id)
        if project is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        return project

    def set_working_aggregation(
        self,
        project_id: UUID,
        *,
        aggregation_execution_id: UUID | None,
    ) -> Project:
        """Point a project at one of its own completed aggregations, or clear the pointer.

        The project's review queue and dashboard summarize this aggregation
        (ADR-0035); auto-creating the default aggregation does not set it.
        """
        with self._unit_of_work_factory() as unit_of_work:
            project = unit_of_work.projects.set_working_aggregation(
                project_id,
                aggregation_execution_id=aggregation_execution_id,
            )
            unit_of_work.commit()
        return project

    def get_snapshot(self, snapshot_id: UUID) -> DatasetSnapshot:
        """Return one dataset snapshot or raise a resource-level not-found failure."""
        with self._unit_of_work_factory() as unit_of_work:
            snapshot = unit_of_work.projects.get_snapshot(snapshot_id)
        if snapshot is None:
            msg = f"dataset snapshot {snapshot_id} does not exist"
            raise ResourceNotFoundError(msg)
        return snapshot

    def list_snapshot_source_members(
        self,
        snapshot_id: UUID,
    ) -> Sequence[SnapshotSourceMember]:
        """Return one snapshot's source members in canonical ordinal order."""
        self.get_snapshot(snapshot_id)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.projects.list_snapshot_source_members(snapshot_id)

    def list_snapshots(
        self,
        project_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[DatasetSnapshot]:
        """Return one newest-first opaque-cursor page of a project's snapshots."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        self.get_project(project_id)
        resource = f"project_snapshots:{project_id}"
        after = decode_creation_position(self._cursor_codec, cursor, resource=resource)
        with self._unit_of_work_factory() as unit_of_work:
            snapshots = unit_of_work.projects.list_snapshots(
                project_id,
                limit=limit + 1,
                after=after,
            )
        return newest_first_page(self._cursor_codec, snapshots, limit=limit, resource=resource)

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
                after_tei_id=position.sort_values[0] if position is not None else None,
                after_person_record_id=position.id if position is not None else None,
            )
        has_more = len(records) > limit
        items = list(records[:limit])
        next_cursor = None
        if has_more:
            last_item = items[-1]
            next_cursor = self._cursor_codec.encode(
                resource=resource,
                sort_values=(last_item.tei_id,),
                resource_id=last_item.id,
            )
        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    def import_snapshot(
        self,
        *,
        project_id: UUID,
        command: SnapshotImportRequest,
        source: BinaryIO | None = None,
        sources: tuple[SnapshotUpload, ...] | list[SnapshotUpload] | None = None,
    ) -> DatasetSnapshot:
        """Durably stage exact sources and atomically accept an asynchronous import."""
        self.get_project(project_id)
        uploads = self._resolve_uploads(source=source, sources=sources, command=command)
        staged_uploads = self._stage_uploads(uploads, command=command)
        manifest = SourceManifestV1(
            source_format=command.source_format,
            packaging=command.packaging,
            members=tuple(
                SourceManifestMember(
                    logical_name=staged.logical_name,
                    sha256=staged.sha256,
                    byte_size=staged.byte_size,
                    media_type=staged.media_type,
                )
                for staged in staged_uploads
            ),
        )
        staged_manifest = (
            self._artifact_storage.store(
                BytesIO(manifest.canonical_bytes()),
                max_byte_size=self._max_upload_bytes,
            )
            if command.packaging is SourcePackaging.loose
            else None
        )
        import_config = SnapshotImportConfig(
            **command.model_dump(),
            profile=import_profile_for_source_format(command.source_format),
            limits=self._import_limits,
        )

        with self._unit_of_work_factory() as unit_of_work:
            member_artifacts = [
                unit_of_work.artifacts.add_artifact(
                    ArtifactCreate(
                        logical_type=self._source_logical_type(command),
                        storage_uri=staged.storage_uri,
                        sha256=staged.sha256,
                        byte_size=staged.byte_size,
                        media_type=staged.media_type,
                        project_id=project_id,
                        metadata={
                            "import_profile": import_config.profile.value,
                            "logical_name": staged.logical_name,
                            "ordinal": ordinal,
                            "packaging": command.packaging.value,
                            "source_format": command.source_format.value,
                        },
                    )
                )
                for ordinal, staged in enumerate(staged_uploads)
            ]
            if staged_manifest is None:
                primary_artifact = member_artifacts[0]
            else:
                primary_artifact = unit_of_work.artifacts.add_artifact(
                    ArtifactCreate(
                        logical_type="source_manifest",
                        storage_uri=staged_manifest.storage_uri,
                        sha256=staged_manifest.sha256,
                        byte_size=staged_manifest.byte_size,
                        media_type=_MANIFEST_MEDIA_TYPE,
                        project_id=project_id,
                        metadata={
                            "manifest_version": manifest.version,
                            "member_count": len(manifest.members),
                            "packaging": command.packaging.value,
                            "source_format": command.source_format.value,
                        },
                    )
                )
            snapshot = unit_of_work.projects.add_snapshot(
                DatasetSnapshotCreate(
                    project_id=project_id,
                    source_artifact_id=primary_artifact.id,
                    source_sha256=primary_artifact.sha256,
                    parser_version=self._importer_version(command),
                    import_config=import_config.model_dump(mode="json"),
                )
            )
            unit_of_work.projects.add_snapshot_source_members(
                snapshot.id,
                [
                    SnapshotSourceMemberCreate(
                        artifact_id=artifact.id,
                        ordinal=ordinal,
                        logical_name=member.logical_name,
                        sha256=member.sha256,
                        byte_size=member.byte_size,
                        media_type=member.media_type,
                    )
                    for ordinal, (artifact, member) in enumerate(
                        zip(member_artifacts, manifest.members, strict=True)
                    )
                ],
            )
            unit_of_work.dispatches.ensure_dispatch(
                SnapshotDispatchCreate(
                    dataset_snapshot_id=snapshot.id,
                    queue_name=CPU_QUEUE,
                    payload=SnapshotImportTaskMessage(dataset_snapshot_id=snapshot.id),
                    available_at=self._clock(),
                )
            )
            unit_of_work.commit()
        return snapshot

    def _resolve_uploads(
        self,
        *,
        source: BinaryIO | None,
        sources: tuple[SnapshotUpload, ...] | list[SnapshotUpload] | None,
        command: SnapshotImportRequest,
    ) -> tuple[SnapshotUpload, ...]:
        if source is not None and sources is not None:
            msg = "supply either source or sources, not both"
            raise InvalidSnapshotSourceError(msg)
        if sources is None:
            if source is None:
                msg = "at least one source upload is required"
                raise InvalidSnapshotSourceError(msg)
            sources = [
                SnapshotUpload(
                    source=source,
                    filename=self._default_filename(command),
                )
            ]
        resolved = tuple(sources)
        if not resolved:
            msg = "at least one source upload is required"
            raise InvalidSnapshotSourceError(msg)
        if len(resolved) > self._import_limits.max_member_count:
            msg = "source collection exceeds the configured member-count limit"
            raise InvalidSnapshotSourceError(msg)
        if command.packaging is SourcePackaging.loose:
            if command.source_format is not SourceFormat.tei:
                msg = "loose source packaging is supported only for TEI"
                raise InvalidSnapshotSourceError(msg)
        elif len(resolved) != 1:
            msg = f"packaging={command.packaging.value!r} requires exactly one source upload"
            raise InvalidSnapshotSourceError(msg)
        return resolved

    def _stage_uploads(
        self,
        uploads: tuple[SnapshotUpload, ...],
        *,
        command: SnapshotImportRequest,
    ) -> tuple[_StagedUpload, ...]:
        named_uploads: list[tuple[str, SnapshotUpload]] = []
        collision_keys: set[str] = set()
        basename_collision_keys: set[str] = set()
        for upload in uploads:
            try:
                logical_name = normalize_source_member_logical_name(upload.filename)
            except ValueError as error:
                raise InvalidSnapshotSourceError(str(error)) from error
            collision_key = logical_name.casefold()
            if collision_key in collision_keys:
                msg = "source member logical names collide after normalization"
                raise InvalidSnapshotSourceError(msg)
            collision_keys.add(collision_key)
            basename_collision_key = PurePosixPath(logical_name).name.casefold()
            if basename_collision_key in basename_collision_keys:
                msg = "source member basenames collide after normalization"
                raise InvalidSnapshotSourceError(msg)
            basename_collision_keys.add(basename_collision_key)
            if command.packaging is SourcePackaging.loose and not logical_name.casefold().endswith(
                ".xml"
            ):
                msg = "loose TEI source members must use an .xml logical name"
                raise InvalidSnapshotSourceError(msg)
            named_uploads.append((logical_name, upload))

        if command.packaging is SourcePackaging.loose:
            named_uploads.sort(key=lambda item: (item[0].casefold(), item[0]))

        staged: list[_StagedUpload] = []
        total_bytes = 0
        for logical_name, upload in named_uploads:
            stored = self._artifact_storage.store(
                upload.source,
                max_byte_size=self._max_upload_bytes,
            )
            total_bytes += stored.byte_size
            if total_bytes > self._max_total_upload_bytes:
                msg = (
                    "source collection exceeds the "
                    f"{self._max_total_upload_bytes}-byte aggregate upload limit"
                )
                raise SnapshotUploadTooLargeError(msg)
            staged.append(
                _StagedUpload(
                    logical_name=logical_name,
                    media_type=self._source_media_type(command),
                    storage_uri=stored.storage_uri,
                    sha256=stored.sha256,
                    byte_size=stored.byte_size,
                )
            )
        return tuple(staged)

    def _importer_version(self, command: SnapshotImportRequest) -> str:
        return version_for_snapshot_import(command)

    @staticmethod
    def _source_logical_type(command: SnapshotImportRequest) -> str:
        if command.packaging is SourcePackaging.zip:
            return "source_zip"
        if command.packaging is SourcePackaging.tar_gz:
            return "source_tar_gz"
        return f"source_{command.source_format.value}"

    @staticmethod
    def _source_media_type(command: SnapshotImportRequest) -> str:
        if command.packaging is SourcePackaging.zip:
            return "application/zip"
        if command.packaging is SourcePackaging.tar_gz:
            return "application/gzip"
        return {
            SourceFormat.tei: "application/tei+xml",
            SourceFormat.csv: "text/csv",
            SourceFormat.xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            SourceFormat.json: "application/json",
        }[command.source_format]

    @staticmethod
    def _default_filename(command: SnapshotImportRequest) -> str:
        if command.packaging is SourcePackaging.zip:
            return "source.zip"
        if command.packaging is SourcePackaging.tar_gz:
            return "source.tar.gz"
        return {
            SourceFormat.tei: "source.xml",
            SourceFormat.csv: "source.csv",
            SourceFormat.xlsx: "source.xlsx",
            SourceFormat.json: "source.json",
        }[command.source_format]
