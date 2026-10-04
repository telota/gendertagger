"""Application orchestration for executable result exports."""

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from io import BytesIO
from uuid import UUID

from pydantic import ValidationError

from gendertagger.export.csv_analysis import CSV_ANALYSIS_MEDIA_TYPE, build_csv_analysis
from gendertagger.export.json_bundle import JSON_BUNDLE_MEDIA_TYPE, build_json_bundle
from gendertagger.export.manifest import build_export_manifest
from gendertagger.export.tei_profile import TeiExportError, inject_gender_annotations
from gendertagger.models.artifact import Artifact, ArtifactCreate
from gendertagger.models.export import (
    ExportExecution,
    ExportFormat,
    ExportInputs,
    ExportManifestOutput,
    ExportPersonRecord,
    ExportTaskMessage,
)
from gendertagger.models.lifecycle import ExportExecutionStatus
from gendertagger.services.diagnostics import sanitized_diagnostic
from gendertagger.services.execution_attempts import execution_attempt_may_retry
from gendertagger.services.ports.artifact_storage import ArtifactStorage
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

Clock = Callable[[], datetime]

DEFAULT_MAX_EXPORT_ATTEMPTS = 3
_EXPORT_MANIFEST_LOGICAL_TYPE = "export_manifest"
_EXPORT_MANIFEST_MEDIA_TYPE = "application/json"
_EXPORT_OUTPUT_TEI_LOGICAL_TYPE = "export_output_tei"
_EXPORT_OUTPUT_TEI_MEDIA_TYPE = "application/tei+xml"
_EXPORT_OUTPUT_JSON_LOGICAL_TYPE = "export_output_json"
_EXPORT_OUTPUT_CSV_LOGICAL_TYPE = "export_output_csv"
_JSON_BUNDLE_LOGICAL_NAME = "export.json"
_CSV_ANALYSIS_LOGICAL_NAME = "export.csv"


class TransientExportError(RuntimeError):
    """Raised when export execution should be retried after rollback."""


class ExportExecutor:
    """Assess and atomically persist one complete export's outputs and manifest.

    The claim, produced output artifacts, manifest artifact, and terminal
    lifecycle transition share one transaction. A worker crash therefore
    exposes either the prior claimable resource or the complete final export,
    never a committed partial export. The original source artifacts are only
    ever read, never mutated.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        artifact_storage: ArtifactStorage,
        max_output_bytes: int,
        clock: Clock,
    ) -> None:
        if max_output_bytes <= 0:
            msg = "export output byte limit must be positive"
            raise ValueError(msg)
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_storage = artifact_storage
        self._max_output_bytes = max_output_bytes
        self._clock = clock

    def execute(
        self,
        message: ExportTaskMessage,
        *,
        attempt_count: int,
        max_attempts: int = DEFAULT_MAX_EXPORT_ATTEMPTS,
    ) -> ExportExecution:
        """Idempotently execute one export with bounded retry policy.

        Invalid or incomplete persisted evidence is terminally persisted.
        Unclassified failures roll back and request a retry until the final
        attempt, when a fresh claim records the sanitized failure diagnostic.

        Args:
            message: Identifier-only task envelope.
            attempt_count: One-based delivery attempt number.
            max_attempts: Maximum attempts before an unclassified error becomes
                terminal.

        Returns:
            The completed, failed, or previously claimed export resource.

        Raises:
            TransientExportError: If an unclassified failure occurred and
                another attempt remains.
            ValueError: If attempt counts are not positive.
        """
        may_retry = execution_attempt_may_retry(attempt_count, max_attempts)

        try:
            return self._execute_once(message)
        except Exception as error:
            if may_retry:
                msg = f"export {message.export_execution_id} failed on attempt {attempt_count}"
                raise TransientExportError(msg) from error
            return self._fail_after_rollback(message, error)

    def _execute_once(self, message: ExportTaskMessage) -> ExportExecution:
        with self._unit_of_work_factory() as unit_of_work:
            export = unit_of_work.exports.claim_export(
                message.export_execution_id,
                started_at=self._clock(),
            )
            if export is None:
                return self._existing_export(unit_of_work, message)

            try:
                manifest_artifact = self._build_export(unit_of_work, export)
            except (
                TeiExportError,
                InvalidResourceStateError,
                ValidationError,
            ) as error:
                failed = self._mark_failed(unit_of_work, export.id, error)
                unit_of_work.commit()
                return failed

            completed = unit_of_work.exports.mark_export_finished(
                export.id,
                status=ExportExecutionStatus.completed,
                finished_at=self._clock(),
                manifest_artifact_id=manifest_artifact.id,
            )
            unit_of_work.commit()
            return completed

    def _fail_after_rollback(
        self,
        message: ExportTaskMessage,
        error: BaseException,
    ) -> ExportExecution:
        with self._unit_of_work_factory() as unit_of_work:
            export = unit_of_work.exports.claim_export(
                message.export_execution_id,
                started_at=self._clock(),
            )
            if export is None:
                return self._existing_export(unit_of_work, message)
            failed = self._mark_failed(unit_of_work, export.id, error)
            unit_of_work.commit()
            return failed

    def _build_export(self, unit_of_work: UnitOfWork, export: ExportExecution) -> Artifact:
        inputs = unit_of_work.exports.load_export_inputs(export.id)

        if export.format is ExportFormat.tei:
            outputs = self._build_tei_outputs(unit_of_work, export, inputs)
        elif export.format is ExportFormat.json:
            outputs = [
                self._store_output(
                    unit_of_work,
                    export,
                    build_json_bundle(inputs.records),
                    logical_type=_EXPORT_OUTPUT_JSON_LOGICAL_TYPE,
                    logical_name=_JSON_BUNDLE_LOGICAL_NAME,
                    media_type=JSON_BUNDLE_MEDIA_TYPE,
                )
            ]
        else:
            outputs = [
                self._store_output(
                    unit_of_work,
                    export,
                    build_csv_analysis(inputs.records),
                    logical_type=_EXPORT_OUTPUT_CSV_LOGICAL_TYPE,
                    logical_name=_CSV_ANALYSIS_LOGICAL_NAME,
                    media_type=CSV_ANALYSIS_MEDIA_TYPE,
                )
            ]

        manifest = build_export_manifest(
            export_execution_id=export.id,
            dataset_snapshot_id=inputs.dataset_snapshot_id,
            source_snapshot_sha256=inputs.source_snapshot_sha256,
            run_id=export.run_id,
            aggregation_execution_id=export.aggregation_execution_id,
            export_format=export.format,
            label_source_policy=export.label_source_policy,
            tei_profile=export.tei_profile,
            outputs=[
                ExportManifestOutput(
                    logical_name=logical_name,
                    sha256=artifact.sha256,
                    byte_size=artifact.byte_size,
                    media_type=artifact.media_type,
                )
                for artifact, logical_name in outputs
            ],
            generated_at=self._clock(),
        )
        return self._store_output(
            unit_of_work,
            export,
            manifest.model_dump_json().encode("utf-8"),
            logical_type=_EXPORT_MANIFEST_LOGICAL_TYPE,
            logical_name="manifest.json",
            media_type=_EXPORT_MANIFEST_MEDIA_TYPE,
        )[0]

    def _build_tei_outputs(
        self,
        unit_of_work: UnitOfWork,
        export: ExportExecution,
        inputs: ExportInputs,
    ) -> list[tuple[Artifact, str]]:
        records_by_member: dict[str, dict[str, ExportPersonRecord]] = defaultdict(dict)
        for record in inputs.records:
            if record.source_member_name is None:
                msg = f"person {record.tei_id!r} has no source-member locator"
                raise InvalidResourceStateError(msg)
            records_by_member[record.source_member_name][record.tei_id] = record

        outputs: list[tuple[Artifact, str]] = []
        for member in inputs.source_members:
            source_artifact = unit_of_work.artifacts.get_artifact(member.artifact_id)
            if source_artifact is None:
                msg = f"artifact {member.artifact_id} for source member {member.logical_name!r} does not exist"
                raise InvalidResourceStateError(msg)
            with self._artifact_storage.open(source_artifact.storage_uri) as source:
                source_bytes = source.read()
            output_bytes = inject_gender_annotations(
                source_bytes,
                records_by_member.get(member.logical_name, {}),
            )
            outputs.append(
                self._store_output(
                    unit_of_work,
                    export,
                    output_bytes,
                    logical_type=_EXPORT_OUTPUT_TEI_LOGICAL_TYPE,
                    logical_name=member.logical_name,
                    media_type=_EXPORT_OUTPUT_TEI_MEDIA_TYPE,
                )
            )
        return outputs

    def _store_output(
        self,
        unit_of_work: UnitOfWork,
        export: ExportExecution,
        content: bytes,
        *,
        logical_type: str,
        logical_name: str,
        media_type: str,
    ) -> tuple[Artifact, str]:
        stored = self._artifact_storage.store(
            BytesIO(content),
            max_byte_size=self._max_output_bytes,
        )
        artifact = unit_of_work.artifacts.add_artifact(
            ArtifactCreate(
                logical_type=logical_type,
                storage_uri=stored.storage_uri,
                sha256=stored.sha256,
                byte_size=stored.byte_size,
                media_type=media_type,
                run_id=export.run_id,
                export_execution_id=export.id,
            )
        )
        return artifact, logical_name

    def _mark_failed(
        self,
        unit_of_work: UnitOfWork,
        export_execution_id: UUID,
        error: BaseException,
    ) -> ExportExecution:
        return unit_of_work.exports.mark_export_finished(
            export_execution_id,
            status=ExportExecutionStatus.failed,
            finished_at=self._clock(),
            failure_class=type(error).__name__,
            failure_diagnostic=sanitized_diagnostic(error),
        )

    @staticmethod
    def _existing_export(
        unit_of_work: UnitOfWork,
        message: ExportTaskMessage,
    ) -> ExportExecution:
        export = unit_of_work.exports.get_export(message.export_execution_id)
        if export is None:
            msg = f"export execution {message.export_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        return export
