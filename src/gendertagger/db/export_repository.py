"""SQLAlchemy repository for export executions."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gendertagger.db.aggregations import AggregatedResultRow, AggregationExecutionRow
from gendertagger.db.executions import RunRow
from gendertagger.db.exports import ExportExecutionRow
from gendertagger.db.keyset import newest_first_slice
from gendertagger.db.projects import DatasetSnapshotRow, PersonRecordRow, SnapshotSourceMemberRow
from gendertagger.db.reviews import AnnotationRow, ReviewStateRow
from gendertagger.export.final_decision import resolve_final_decision
from gendertagger.models.aggregation import AggregatedResult, VoteCounts
from gendertagger.models.classification import CanonicalLabel
from gendertagger.models.export import (
    ExportExecution,
    ExportExecutionCreate,
    ExportFormat,
    ExportInputs,
    ExportPersonRecord,
    ExportSourceMember,
    LabelSourcePolicy,
)
from gendertagger.models.lifecycle import AggregationExecutionStatus, ExportExecutionStatus
from gendertagger.models.project import SourceFormat, SourcePackaging
from gendertagger.models.review import Annotation
from gendertagger.services.pagination import CreationPosition
from gendertagger.services.ports.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)

_TERMINAL_EXPORT_STATUSES = {
    ExportExecutionStatus.completed,
    ExportExecutionStatus.failed,
}


class SqlAlchemyExportRepository:
    """Map export contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_export(self, command: ExportExecutionCreate) -> ExportExecution:
        """Persist an export over a locked run and its completed aggregation."""
        run = self._session.scalar(
            select(RunRow)
            .where(RunRow.id == command.run_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if run is None:
            msg = f"run {command.run_id} does not exist"
            raise ResourceNotFoundError(msg)

        aggregation = self._session.get(
            AggregationExecutionRow,
            command.aggregation_execution_id,
        )
        if aggregation is None:
            msg = f"aggregation execution {command.aggregation_execution_id} does not exist"
            raise ResourceNotFoundError(msg)
        if aggregation.run_id != command.run_id:
            msg = "the selected aggregation execution must belong to the export run"
            raise InvalidResourceStateError(msg)
        if aggregation.status is not AggregationExecutionStatus.completed:
            msg = f"aggregation execution {aggregation.id} is not completed"
            raise InvalidResourceStateError(msg)

        row = ExportExecutionRow(
            run_id=command.run_id,
            aggregation_execution_id=command.aggregation_execution_id,
            format=command.format,
            label_source_policy=command.label_source_policy,
            tei_profile=command.tei_profile,
            human_resp_id=command.human_resp_id,
            status=ExportExecutionStatus.pending,
            manifest_artifact_id=None,
            started_at=None,
            finished_at=None,
            failure_class=None,
            failure_diagnostic=None,
        )
        self._session.add(row)
        self._session.flush()
        return self._export_from_row(row)

    def get_export(self, export_id: UUID) -> ExportExecution | None:
        """Return an export contract by ID without exposing its row."""
        row = self._session.get(ExportExecutionRow, export_id)
        return None if row is None else self._export_from_row(row)

    def list_exports(
        self,
        run_id: UUID,
        *,
        limit: int,
        after: CreationPosition | None = None,
    ) -> Sequence[ExportExecution]:
        """Return a run's exports newest first, in every lifecycle state."""
        rows = self._session.scalars(
            newest_first_slice(
                select(ExportExecutionRow).where(ExportExecutionRow.run_id == run_id),
                created_at=ExportExecutionRow.created_at,
                row_id=ExportExecutionRow.id,
                limit=limit,
                after=after,
            )
        )
        return tuple(self._export_from_row(row) for row in rows)

    def mark_export_queued(self, export_id: UUID) -> ExportExecution:
        """Atomically transition a pending export to queued."""
        statement = (
            select(ExportExecutionRow)
            .where(
                ExportExecutionRow.id == export_id,
                ExportExecutionRow.status == ExportExecutionStatus.pending,
            )
            .with_for_update()
        )
        row = self._session.scalar(statement)
        if row is not None:
            row.status = ExportExecutionStatus.queued
            self._session.flush()
            return self._export_from_row(row)

        existing = self._require_export(export_id)
        self._require_source(
            export_id,
            existing.status,
            {ExportExecutionStatus.pending},
            ExportExecutionStatus.queued.value,
        )
        raise AssertionError("unreachable export queuing transition")  # pragma: no cover

    def claim_export(
        self,
        export_id: UUID,
        *,
        started_at: datetime,
    ) -> ExportExecution | None:
        """Atomically claim a pending or queued export for one worker."""
        statement = (
            select(ExportExecutionRow)
            .where(
                ExportExecutionRow.id == export_id,
                ExportExecutionRow.status.in_(
                    (ExportExecutionStatus.pending, ExportExecutionStatus.queued)
                ),
            )
            .with_for_update()
        )
        row = self._session.scalar(statement)
        if row is not None:
            row.status = ExportExecutionStatus.running
            row.started_at = started_at
            self._session.flush()
            return self._export_from_row(row)

        existing = self._session.scalar(
            select(ExportExecutionRow).where(ExportExecutionRow.id == export_id)
        )
        if existing is None:
            msg = f"export execution {export_id} does not exist"
            raise ResourceNotFoundError(msg)
        return None

    def load_export_inputs(self, export_id: UUID) -> ExportInputs:
        """Load every snapshot person's FinalDecision projection and source members."""
        export = self._require_export(export_id)
        self._require_source(
            export_id,
            export.status,
            {ExportExecutionStatus.running},
            "load export inputs",
        )
        snapshot_id = self._snapshot_id_for_run(export.run_id)
        snapshot = self._session.get(DatasetSnapshotRow, snapshot_id)
        if snapshot is None or snapshot.record_count is None:
            msg = f"dataset snapshot {snapshot_id} has no complete record count"
            raise InvalidResourceStateError(msg)

        raw_source_format = snapshot.import_config.get("source_format", SourceFormat.tei.value)
        source_format = SourceFormat(raw_source_format)
        raw_packaging = snapshot.import_config.get("packaging", SourcePackaging.single.value)
        packaging = SourcePackaging(raw_packaging)
        if export.format is ExportFormat.tei:
            if source_format is not SourceFormat.tei:
                msg = f"snapshot {snapshot_id} is not a TEI source and cannot use format='tei'"
                raise InvalidResourceStateError(msg)
            if packaging not in {SourcePackaging.single, SourcePackaging.loose}:
                msg = (
                    f"snapshot {snapshot_id} uses packaging {packaging.value!r}, which "
                    "format='tei' export does not yet support"
                )
                raise InvalidResourceStateError(msg)

        aggregation = self._session.get(
            AggregationExecutionRow,
            export.aggregation_execution_id,
        )
        if aggregation is None or aggregation.status is not AggregationExecutionStatus.completed:
            msg = f"aggregation execution {export.aggregation_execution_id} is no longer completed"
            raise InvalidResourceStateError(msg)
        result_rows = tuple(
            self._session.scalars(
                select(AggregatedResultRow).where(
                    AggregatedResultRow.aggregation_execution_id == export.aggregation_execution_id
                )
            )
        )

        person_rows = tuple(
            self._session.scalars(
                select(PersonRecordRow).where(PersonRecordRow.dataset_snapshot_id == snapshot_id)
            )
        )
        person_locators = {row.id: (row.tei_id, row.source_member_name) for row in person_rows}

        annotations_by_person: dict[UUID, Annotation] = {}
        if export.label_source_policy is LabelSourcePolicy.human_overrides:
            rows = self._session.execute(
                select(ReviewStateRow, AnnotationRow, PersonRecordRow.tei_id)
                .join(AnnotationRow, AnnotationRow.id == ReviewStateRow.current_annotation_id)
                .join(
                    PersonRecordRow,
                    PersonRecordRow.id == ReviewStateRow.person_record_id,
                )
                .where(ReviewStateRow.dataset_snapshot_id == snapshot_id)
            )
            for review_state, annotation_row, tei_id in rows:
                annotations_by_person[review_state.person_record_id] = self._annotation_from_row(
                    annotation_row,
                    tei_id,
                )

        records: list[ExportPersonRecord] = [
            resolve_final_decision(
                tei_id=person_locators[result_row.person_record_id][0],
                source_member_name=person_locators[result_row.person_record_id][1],
                aggregated_result=self._aggregated_result_from_row(result_row),
                annotation=annotations_by_person.get(result_row.person_record_id),
                label_source_policy=export.label_source_policy,
                human_resp_id=export.human_resp_id,
            )
            for result_row in result_rows
        ]

        member_rows = self._session.scalars(
            select(SnapshotSourceMemberRow)
            .where(SnapshotSourceMemberRow.dataset_snapshot_id == snapshot_id)
            .order_by(SnapshotSourceMemberRow.ordinal)
        )
        source_members = tuple(
            ExportSourceMember(
                logical_name=member.logical_name,
                artifact_id=member.artifact_id,
                media_type=member.media_type,
            )
            for member in member_rows
        )

        return ExportInputs(
            dataset_snapshot_id=snapshot_id,
            source_snapshot_sha256=snapshot.source_sha256,
            source_format=source_format,
            packaging=packaging,
            records=tuple(records),
            source_members=source_members,
        )

    def mark_export_finished(
        self,
        export_id: UUID,
        *,
        status: ExportExecutionStatus,
        finished_at: datetime,
        manifest_artifact_id: UUID | None = None,
        failure_class: str | None = None,
        failure_diagnostic: str | None = None,
    ) -> ExportExecution:
        """Transition a running export to a complete or failed outcome."""
        if status not in _TERMINAL_EXPORT_STATUSES:
            msg = f"{status} is not a supported terminal export status"
            raise ValueError(msg)
        row = self._require_export(export_id)
        self._require_source(
            export_id,
            row.status,
            {ExportExecutionStatus.running},
            status.value,
        )
        failed = status is ExportExecutionStatus.failed
        if failed:
            if not (failure_diagnostic and failure_diagnostic.strip()):
                msg = "a failed export requires a failure diagnostic"
                raise ValueError(msg)
            if manifest_artifact_id is not None:
                msg = "a failed export must not retain a manifest artifact"
                raise InvalidResourceStateError(msg)
        elif manifest_artifact_id is None:
            msg = "a completed export requires a manifest artifact"
            raise ValueError(msg)

        row.status = status
        row.finished_at = finished_at
        row.manifest_artifact_id = None if failed else manifest_artifact_id
        row.failure_class = failure_class if failed else None
        row.failure_diagnostic = failure_diagnostic if failed else None
        self._session.flush()
        return self._export_from_row(row)

    @staticmethod
    def _export_from_row(row: ExportExecutionRow) -> ExportExecution:
        return ExportExecution(
            id=row.id,
            run_id=row.run_id,
            aggregation_execution_id=row.aggregation_execution_id,
            format=row.format,
            label_source_policy=row.label_source_policy,
            tei_profile=row.tei_profile,
            human_resp_id=row.human_resp_id,
            status=row.status,
            manifest_artifact_id=row.manifest_artifact_id,
            started_at=row.started_at,
            finished_at=row.finished_at,
            failure_class=row.failure_class,
            failure_diagnostic=row.failure_diagnostic,
            created_at=row.created_at,
        )

    def _require_export(self, export_id: UUID) -> ExportExecutionRow:
        row = self._session.get(ExportExecutionRow, export_id)
        if row is None:
            msg = f"export execution {export_id} does not exist"
            raise ResourceNotFoundError(msg)
        return row

    def _snapshot_id_for_run(self, run_id: UUID) -> UUID:
        snapshot_id = self._session.scalar(
            select(RunRow.dataset_snapshot_id).where(RunRow.id == run_id)
        )
        if snapshot_id is None:
            msg = f"run {run_id} does not exist"
            raise ResourceNotFoundError(msg)
        return snapshot_id

    @staticmethod
    def _require_source(
        export_id: UUID,
        current_status: ExportExecutionStatus,
        allowed_statuses: set[ExportExecutionStatus],
        action: str,
    ) -> None:
        if current_status not in allowed_statuses:
            msg = f"export execution {export_id} cannot {action} from status {current_status.value}"
            raise InvalidResourceStateError(msg)

    @staticmethod
    def _annotation_from_row(row: AnnotationRow, tei_id: str) -> Annotation:
        return Annotation(
            id=row.id,
            snapshot_id=row.dataset_snapshot_id,
            person_record_id=row.person_record_id,
            tei_id=tei_id,
            action=row.action,
            label=row.label,
            reviewer_user_id=row.reviewer_user_id,
            comment=row.comment,
            aggregated_result_id=row.aggregated_result_id,
            supersedes_annotation_id=row.supersedes_annotation_id,
            resulting_revision=row.resulting_revision,
            created_at=row.created_at,
        )

    @staticmethod
    def _aggregated_result_from_row(row: AggregatedResultRow) -> AggregatedResult:
        return AggregatedResult(
            id=row.id,
            aggregation_execution_id=row.aggregation_execution_id,
            person_record_id=row.person_record_id,
            outcome=row.outcome,
            label=row.label,
            pooled_vote_counts=VoteCounts(
                male=row.male_vote_count,
                female=row.female_vote_count,
                unknown=row.unknown_vote_count,
                institution=row.institution_vote_count,
            ),
            tied_labels=tuple(CanonicalLabel(label) for label in row.tied_labels),
            override_source=row.override_source,
            override_agreeing_count=row.override_agreeing_count,
            override_comparison_count=row.override_comparison_count,
            agreement_score=row.agreement_score,
            agreement_tier=row.agreement_tier,
            certainty_tier=row.certainty_tier,
            has_prediction_error=row.has_prediction_error,
            metadata=row.result_metadata,
            created_at=row.created_at,
        )
