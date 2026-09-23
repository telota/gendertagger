"""Application use cases for independently rerunnable exports."""

from collections.abc import Callable
from uuid import UUID

from gendertagger.models.api import CursorPage
from gendertagger.models.common import UtcDatetime
from gendertagger.models.dispatch import ExportDispatchCreate
from gendertagger.models.export import (
    ExportCreateRequest,
    ExportExecution,
    ExportExecutionCreate,
    ExportFormat,
    ExportTaskMessage,
    TeiExportProfile,
)
from gendertagger.models.queues import CPU_QUEUE
from gendertagger.services.pagination import (
    CursorCodec,
    decode_creation_position,
    newest_first_page,
)
from gendertagger.services.ports.artifact_storage import ArtifactStorage
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.ports.unit_of_work import UnitOfWorkFactory

Clock = Callable[[], UtcDatetime]

_DEFAULT_TEI_EXPORT_PROFILE = TeiExportProfile.tei_p5_gender_v1


class ExportService:
    """Persist durable export commands and read immutable output bytes."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        artifact_storage: ArtifactStorage,
        cursor_codec: CursorCodec,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_storage = artifact_storage
        self._cursor_codec = cursor_codec
        self._clock = clock

    def create_export(self, command: ExportCreateRequest) -> ExportExecution:
        """Persist one export and its durable dispatch intent atomically."""
        resolved_tei_profile = (
            command.tei_profile or _DEFAULT_TEI_EXPORT_PROFILE
            if command.format is ExportFormat.tei
            else None
        )
        with self._unit_of_work_factory() as unit_of_work:
            export = unit_of_work.exports.add_export(
                ExportExecutionCreate(
                    run_id=command.run_id,
                    aggregation_execution_id=command.aggregation_execution_id,
                    format=command.format,
                    label_source_policy=command.label_source_policy,
                    tei_profile=resolved_tei_profile,
                    human_resp_id=command.human_resp_id,
                )
            )
            unit_of_work.dispatches.ensure_dispatch(
                ExportDispatchCreate(
                    export_id=export.id,
                    queue_name=CPU_QUEUE,
                    payload=ExportTaskMessage(export_id=export.id),
                    available_at=self._clock(),
                )
            )
            export = unit_of_work.exports.mark_export_queued(export.id)
            unit_of_work.commit()
        return export

    def get_export(self, export_id: UUID) -> ExportExecution:
        """Return one export execution or raise a not-found failure."""
        with self._unit_of_work_factory() as unit_of_work:
            export = unit_of_work.exports.get_export(export_id)
        if export is None:
            msg = f"export execution {export_id} does not exist"
            raise ResourceNotFoundError(msg)
        return export

    def list_exports(
        self,
        run_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[ExportExecution]:
        """Return one newest-first opaque-cursor page of a run's exports."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        resource = f"run_exports:{run_id}"
        after = decode_creation_position(self._cursor_codec, cursor, resource=resource)
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.runs.get_run(run_id) is None:
                msg = f"run {run_id} does not exist"
                raise ResourceNotFoundError(msg)
            exports = unit_of_work.exports.list_exports(
                run_id,
                limit=limit + 1,
                after=after,
            )
        return newest_first_page(self._cursor_codec, exports, limit=limit, resource=resource)

    def download_export(self, export_id: UUID) -> tuple[bytes, str]:
        """Return one completed export's primary bytes and media type.

        A single-output export (``json``, ``csv``, or ``tei`` over a
        single-file source) downloads that output directly. A multi-output
        export (``tei`` over a loose collection) downloads its manifest
        instead -- fetching every individual member output is not yet
        exposed as a separate resource.
        """
        export = self.get_export(export_id)
        if export.manifest_artifact_id is None:
            msg = f"export execution {export_id} has no output artifacts"
            raise ResourceNotFoundError(msg)
        with self._unit_of_work_factory() as unit_of_work:
            outputs = [
                artifact
                for artifact in unit_of_work.artifacts.list_artifacts_by_export(export_id)
                if artifact.id != export.manifest_artifact_id
            ]
            manifest = unit_of_work.artifacts.get_artifact(export.manifest_artifact_id)
        if manifest is None:
            msg = f"artifact {export.manifest_artifact_id} does not exist"
            raise ResourceNotFoundError(msg)
        target = outputs[0] if len(outputs) == 1 else manifest
        with self._artifact_storage.open(target.storage_uri) as source:
            return source.read(), target.media_type
