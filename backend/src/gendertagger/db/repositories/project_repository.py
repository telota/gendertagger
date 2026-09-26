"""SQLAlchemy repository for projects, snapshots, and person records."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from gendertagger.config.run import AggregationStrategy, RunConfig
from gendertagger.db.keyset import newest_first_slice
from gendertagger.db.rows.aggregations import (
    AggregationExecutionRow,
    AggregationMethodExecutionRow,
)
from gendertagger.db.rows.artifacts import ArtifactRow
from gendertagger.db.rows.executions import MethodExecutionRow, RunRow
from gendertagger.db.rows.projects import (
    DatasetSnapshotRow,
    PersonExternalIdRow,
    PersonRecordRow,
    ProjectRow,
    SnapshotSourceMemberRow,
)
from gendertagger.db.rows.teams import TeamRow
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.models.aggregation import AggregationExecution
from gendertagger.models.common import normalize_utc_datetime
from gendertagger.models.lifecycle import AggregationExecutionStatus, DatasetSnapshotStatus
from gendertagger.models.person import (
    ImportedPerson,
    PersonEvent,
    PersonInput,
    PersonNameForm,
    PersonRecord,
)
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    DatasetSnapshotListFilter,
    DatasetSnapshotStatistics,
    Project,
    ProjectCreate,
    ProjectDataAvailability,
    SnapshotGndStatistics,
    SnapshotImportConfig,
    SnapshotSourceMember,
    SnapshotSourceMemberCreate,
    SourcePackaging,
    TabularImportProfile,
    TeiImportProfile,
)
from gendertagger.models.run import Progress, Run
from gendertagger.models.task import ProjectReviewResult
from gendertagger.models.team import TeamSummary
from gendertagger.services.pagination import CreationPosition
from gendertagger.services.ports.persistence_errors import (
    ImmutableResourceError,
    InvalidResourceStateError,
    ResourceNotFoundError,
)


class SqlAlchemyProjectRepository:
    """Map project contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_project(
        self,
        command: ProjectCreate,
        *,
        manager_user_id: UUID,
        created_by_user_id: UUID,
    ) -> Project:
        """Persist and flush a new team-owned project without committing."""
        row = ProjectRow(
            slug=command.slug,
            display_name=command.display_name,
            description=command.description,
            team_id=command.team_id,
            manager_user_id=manager_user_id,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(row)
        self._session.flush()
        team = self._require_team(row.team_id)
        return self._project_from_row(row, team)

    def get_project(self, project_id: UUID) -> Project | None:
        """Return a project contract by ID without exposing its row."""
        row = self._session.get(ProjectRow, project_id)
        return None if row is None else self._project_from_row(row, self._require_team(row.team_id))

    def get_data_availability(self, project_id: UUID) -> ProjectDataAvailability | None:
        """Read project-wide existence without loading collections or using a working pointer."""
        ready_snapshots = (
            select(DatasetSnapshotRow.id)
            .where(
                DatasetSnapshotRow.project_id == ProjectRow.id,
                DatasetSnapshotRow.status == DatasetSnapshotStatus.ready,
            )
            .exists()
        )
        completed_aggregations = (
            select(AggregationExecutionRow.id)
            .join(RunRow, RunRow.id == AggregationExecutionRow.run_id)
            .join(DatasetSnapshotRow, DatasetSnapshotRow.id == RunRow.dataset_snapshot_id)
            .where(
                DatasetSnapshotRow.project_id == ProjectRow.id,
                AggregationExecutionRow.status == AggregationExecutionStatus.completed,
            )
            .exists()
        )
        row = self._session.execute(
            select(ProjectRow.id, ready_snapshots, completed_aggregations).where(
                ProjectRow.id == project_id
            )
        ).one_or_none()
        if row is None:
            return None
        return ProjectDataAvailability(
            project_id=row[0],
            has_ready_snapshots=row[1],
            has_completed_aggregations=row[2],
        )

    def get_project_for_update(self, project_id: UUID) -> Project | None:
        """Return a project contract under a write lock without exposing its row."""
        row = self._session.get(ProjectRow, project_id, with_for_update=True)
        return None if row is None else self._project_from_row(row, self._require_team(row.team_id))

    def get_project_by_slug(self, slug: str) -> Project | None:
        """Return a project contract by its unique slug without exposing its row."""
        row = self._session.scalar(select(ProjectRow).where(ProjectRow.slug == slug))
        return None if row is None else self._project_from_row(row, self._require_team(row.team_id))

    def list_projects(
        self,
        *,
        limit: int,
        after_slug: str | None = None,
    ) -> Sequence[Project]:
        """Return every project in unique-slug order using keyset continuation."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        statement = select(ProjectRow, TeamRow).join(TeamRow, TeamRow.id == ProjectRow.team_id)
        if after_slug is not None:
            statement = statement.where(ProjectRow.slug > after_slug)
        rows = self._session.execute(statement.order_by(ProjectRow.slug).limit(limit))
        return tuple(self._project_from_row(project, team) for project, team in rows)

    def set_working_aggregation(
        self,
        project_id: UUID,
        *,
        aggregation_execution_id: UUID | None,
    ) -> Project:
        """Point a project at one of its own completed aggregations, or clear the pointer."""
        row = self._session.get(ProjectRow, project_id)
        if row is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        if aggregation_execution_id is not None:
            owning_project_id, status = self._session.execute(
                select(DatasetSnapshotRow.project_id, AggregationExecutionRow.status)
                .select_from(AggregationExecutionRow)
                .join(RunRow, RunRow.id == AggregationExecutionRow.run_id)
                .join(DatasetSnapshotRow, DatasetSnapshotRow.id == RunRow.dataset_snapshot_id)
                .where(AggregationExecutionRow.id == aggregation_execution_id)
            ).first() or (None, None)
            if owning_project_id is None:
                msg = f"aggregation execution {aggregation_execution_id} does not exist"
                raise ResourceNotFoundError(msg)
            if owning_project_id != project_id:
                msg = (
                    f"aggregation execution {aggregation_execution_id} "
                    f"does not exist under project {project_id}"
                )
                raise ResourceNotFoundError(msg)
            if status is not AggregationExecutionStatus.completed:
                msg = f"aggregation execution {aggregation_execution_id} is not completed"
                raise InvalidResourceStateError(msg)
        row.working_aggregation_execution_id = aggregation_execution_id
        self._session.flush()
        return self._project_from_row(row, self._require_team(row.team_id))

    def set_game_mode_enabled(self, project_id: UUID, *, enabled: bool) -> Project:
        """Enable or disable the optional game interface for one project."""
        row = self._session.get(ProjectRow, project_id)
        if row is None:
            msg = f"project {project_id} does not exist"
            raise ResourceNotFoundError(msg)
        row.game_mode_enabled = enabled
        self._session.flush()
        return self._project_from_row(row, self._require_team(row.team_id))

    def add_snapshot(self, command: DatasetSnapshotCreate) -> DatasetSnapshot:
        """Persist and flush a new pending snapshot without committing."""
        import_config = self._validated_import_config(command.import_config)
        self._require_parser_version_provenance(
            parser_version=command.parser_version,
            import_config=import_config,
        )
        self._require_primary_artifact_provenance(
            project_id=command.project_id,
            source_artifact_id=command.source_artifact_id,
            source_sha256=command.source_sha256,
            import_config=import_config,
        )
        row = DatasetSnapshotRow(
            project_id=command.project_id,
            source_artifact_id=command.source_artifact_id,
            status=DatasetSnapshotStatus.pending,
            source_sha256=command.source_sha256,
            parser_version=command.parser_version,
            import_config=command.import_config,
            record_count=None,
            statistics=None,
            ready_at=None,
            failure_class=None,
            failure_diagnostic=None,
        )
        self._session.add(row)
        self._session.flush()
        return self._snapshot_from_row(row)

    def get_snapshot(self, snapshot_id: UUID) -> DatasetSnapshot | None:
        """Return a snapshot contract by ID without exposing its row."""
        row = self._session.get(DatasetSnapshotRow, snapshot_id)
        return None if row is None else self._snapshot_from_row(row)

    def get_snapshot_statistics(
        self,
        snapshot_id: UUID,
    ) -> DatasetSnapshotStatistics | None:
        """Return materialized statistics, deriving GND coverage for legacy snapshots."""
        row = self._session.get(DatasetSnapshotRow, snapshot_id)
        if row is None:
            return None
        if row.status is not DatasetSnapshotStatus.ready:
            msg = f"dataset snapshot {snapshot_id} is not ready"
            raise InvalidResourceStateError(msg)
        if row.statistics is not None:
            statistics = DatasetSnapshotStatistics.model_validate(row.statistics)
            if (
                statistics.dataset_snapshot_id != row.id
                or statistics.total_person_count != row.record_count
            ):
                msg = f"dataset snapshot {snapshot_id} statistics do not match the snapshot"
                raise InvalidResourceStateError(msg)
            return statistics

        with_gnd_count = (
            self._session.scalar(
                select(func.count(PersonExternalIdRow.id))
                .join(
                    PersonRecordRow,
                    PersonRecordRow.id == PersonExternalIdRow.person_record_id,
                )
                .where(
                    PersonRecordRow.dataset_snapshot_id == snapshot_id,
                    PersonExternalIdRow.scheme == "gnd",
                )
            )
            or 0
        )
        total_person_count = row.record_count
        if total_person_count is None:
            msg = f"ready dataset snapshot {snapshot_id} has no record count"
            raise InvalidResourceStateError(msg)
        return DatasetSnapshotStatistics(
            dataset_snapshot_id=snapshot_id,
            total_person_count=total_person_count,
            source_gender=None,
            gnd=SnapshotGndStatistics(
                with_reference_count=with_gnd_count,
                without_reference_count=total_person_count - with_gnd_count,
                with_reference_and_source_gender_count=None,
            ),
        )

    def list_snapshots(
        self,
        project_id: UUID,
        *,
        limit: int,
        after: CreationPosition | None = None,
        filters: DatasetSnapshotListFilter | None = None,
    ) -> Sequence[DatasetSnapshot]:
        """Return matching snapshots newest first, filtering before the keyset slice."""
        filters = filters or DatasetSnapshotListFilter()
        statement = select(DatasetSnapshotRow).where(DatasetSnapshotRow.project_id == project_id)
        if filters.status is not None:
            statement = statement.where(DatasetSnapshotRow.status == filters.status)
        if filters.has_completed_aggregations is not None:
            completed = (
                select(AggregationExecutionRow.id)
                .join(RunRow, RunRow.id == AggregationExecutionRow.run_id)
                .where(
                    RunRow.dataset_snapshot_id == DatasetSnapshotRow.id,
                    AggregationExecutionRow.status == AggregationExecutionStatus.completed,
                )
                .exists()
            )
            statement = statement.where(
                completed if filters.has_completed_aggregations else ~completed
            )
        rows = self._session.scalars(
            newest_first_slice(
                statement,
                created_at=DatasetSnapshotRow.created_at,
                row_id=DatasetSnapshotRow.id,
                limit=limit,
                after=after,
            )
        )
        return tuple(self._snapshot_from_row(row) for row in rows)

    def list_review_results(
        self,
        project_id: UUID,
        *,
        limit: int,
        after: CreationPosition | None = None,
    ) -> Sequence[ProjectReviewResult]:
        """Return completed aggregation executions with their run and snapshot context."""
        statement = (
            select(AggregationExecutionRow, RunRow, DatasetSnapshotRow)
            .join(RunRow, RunRow.id == AggregationExecutionRow.run_id)
            .join(DatasetSnapshotRow, DatasetSnapshotRow.id == RunRow.dataset_snapshot_id)
            .where(
                DatasetSnapshotRow.project_id == project_id,
                DatasetSnapshotRow.status == DatasetSnapshotStatus.ready,
                AggregationExecutionRow.status == AggregationExecutionStatus.completed,
            )
        )
        if after is not None:
            statement = statement.where(
                or_(
                    AggregationExecutionRow.created_at < after.created_at,
                    and_(
                        AggregationExecutionRow.created_at == after.created_at,
                        AggregationExecutionRow.id < after.id,
                    ),
                )
            )
        rows = self._session.execute(
            statement.order_by(
                AggregationExecutionRow.created_at.desc(),
                AggregationExecutionRow.id.desc(),
            ).limit(limit)
        ).all()
        aggregation_ids = [aggregation.id for aggregation, _, _ in rows]
        run_ids = [run.id for _, run, _ in rows]
        method_ids = self._method_execution_ids_by_aggregation(aggregation_ids)
        progress = self._run_progress_by_id(run_ids)
        return tuple(
            ProjectReviewResult(
                id=aggregation.id,
                created_at=aggregation.created_at,
                aggregation=self._aggregation_from_row(
                    aggregation,
                    method_ids.get(aggregation.id, ()),
                ),
                run=self._run_from_row(run, progress=progress.get(run.id)),
                snapshot=self._snapshot_from_row(snapshot),
            )
            for aggregation, run, snapshot in rows
        )

    def add_snapshot_source_members(
        self,
        snapshot_id: UUID,
        members: Sequence[SnapshotSourceMemberCreate],
    ) -> Sequence[SnapshotSourceMember]:
        """Persist and flush one complete ordered source-member set."""
        if not members:
            msg = "a snapshot source requires at least one member"
            raise ValueError(msg)
        snapshot = self._locked_snapshot(snapshot_id)
        self._require_snapshot_status(snapshot, DatasetSnapshotStatus.pending)
        import_config = self._validated_import_config(
            snapshot.import_config,
            snapshot_id=snapshot.id,
        )
        self._require_parser_version_provenance(
            parser_version=snapshot.parser_version,
            import_config=import_config,
        )
        self._require_primary_artifact_provenance(
            project_id=snapshot.project_id,
            source_artifact_id=snapshot.source_artifact_id,
            source_sha256=snapshot.source_sha256,
            import_config=import_config,
        )
        if len(members) > import_config.limits.max_member_count:
            msg = "snapshot source exceeds its persisted member-count limit"
            raise InvalidResourceStateError(msg)
        packaging = import_config.packaging
        if packaging is not SourcePackaging.loose and len(members) != 1:
            msg = "single-file and archive snapshots require exactly one source container"
            raise ValueError(msg)
        if (
            packaging is not SourcePackaging.loose
            and members[0].artifact_id != snapshot.source_artifact_id
        ):
            msg = "single-file and archive source member must be the primary source artifact"
            raise InvalidResourceStateError(msg)
        expected_ordinals = set(range(len(members)))
        actual_ordinals = {member.ordinal for member in members}
        if actual_ordinals != expected_ordinals or len(actual_ordinals) != len(members):
            msg = "snapshot source-member ordinals must be unique and contiguous from zero"
            raise ValueError(msg)
        logical_names = [member.logical_name.casefold() for member in members]
        if len(logical_names) != len(set(logical_names)):
            msg = "snapshot source-member logical names must be unique"
            raise ValueError(msg)
        basenames = [PurePosixPath(member.logical_name).name.casefold() for member in members]
        if len(basenames) != len(set(basenames)):
            msg = "snapshot source-member basenames must be unique"
            raise ValueError(msg)

        artifact_ids = {member.artifact_id for member in members}
        artifacts = {
            artifact.id: artifact
            for artifact in self._session.scalars(
                select(ArtifactRow).where(ArtifactRow.id.in_(artifact_ids))
            )
        }
        if artifacts.keys() != artifact_ids:
            msg = "one or more snapshot source-member artifacts do not exist"
            raise ResourceNotFoundError(msg)

        rows: list[SnapshotSourceMemberRow] = []
        expected_logical_type = self._expected_member_logical_type(import_config)
        for member in sorted(members, key=lambda value: value.ordinal):
            artifact = artifacts[member.artifact_id]
            self._validate_source_member_artifact(
                snapshot,
                member,
                artifact,
                expected_logical_type=expected_logical_type,
            )
            rows.append(
                SnapshotSourceMemberRow(
                    dataset_snapshot_id=snapshot_id,
                    artifact_id=member.artifact_id,
                    ordinal=member.ordinal,
                    logical_name=member.logical_name,
                    sha256=member.sha256,
                    byte_size=member.byte_size,
                    media_type=member.media_type,
                )
            )
        self._session.add_all(rows)
        self._session.flush()
        return tuple(self._source_member_from_row(row) for row in rows)

    def list_snapshot_source_members(
        self,
        snapshot_id: UUID,
    ) -> Sequence[SnapshotSourceMember]:
        """Return one snapshot's source members ordered by ordinal."""
        rows = self._session.scalars(
            select(SnapshotSourceMemberRow)
            .where(SnapshotSourceMemberRow.dataset_snapshot_id == snapshot_id)
            .order_by(SnapshotSourceMemberRow.ordinal)
        )
        return tuple(self._source_member_from_row(row) for row in rows)

    def claim_snapshot_import(self, snapshot_id: UUID) -> DatasetSnapshot | None:
        """Atomically claim a pending snapshot for one import attempt.

        The caller keeps this transition in the same transaction as all person
        writes and terminal completion. A rollback therefore makes the snapshot
        pending and claimable again, while duplicate deliveries become no-ops.
        """
        statement = (
            update(DatasetSnapshotRow)
            .where(
                DatasetSnapshotRow.id == snapshot_id,
                DatasetSnapshotRow.status == DatasetSnapshotStatus.pending,
            )
            .values(status=DatasetSnapshotStatus.importing)
            .returning(DatasetSnapshotRow)
            .execution_options(populate_existing=True)
        )
        row = self._session.scalar(statement)
        if row is not None:
            self._session.flush()
            return self._snapshot_from_row(row)

        existing = self._session.scalar(
            select(DatasetSnapshotRow)
            .where(DatasetSnapshotRow.id == snapshot_id)
            .execution_options(populate_existing=True)
        )
        if existing is None:
            msg = f"dataset snapshot {snapshot_id} does not exist"
            raise ResourceNotFoundError(msg)
        self._session.flush()
        return None

    def add_imported_person_records(
        self,
        snapshot_id: UUID,
        people: Sequence[ImportedPerson],
    ) -> int:
        """Persist one bounded person batch with exact source provenance."""
        snapshot = self._locked_snapshot(snapshot_id)
        self._require_snapshot_status(snapshot, DatasetSnapshotStatus.importing)
        canonical_people = [imported.person for imported in people]
        self._require_profile_provenance(snapshot, canonical_people)
        self._require_source_member_provenance(snapshot, people)

        person_rows = [
            PersonRecordRow(
                dataset_snapshot_id=snapshot_id,
                tei_id=imported.person.tei_id,
                surname=imported.person.surname,
                forenames=imported.person.forenames,
                birth=imported.person.birth,
                death=imported.person.death,
                note=imported.person.note,
                events=[event.model_dump(mode="json") for event in imported.person.events],
                alt_names=imported.person.alt_names,
                name_forms=(
                    [name_form.model_dump(mode="json") for name_form in imported.person.name_forms]
                    if imported.person.name_forms is not None
                    else None
                ),
                source_member_name=imported.source_member_name,
                source_record_locator=imported.source_record_locator,
            )
            for imported in people
        ]
        self._session.add_all(person_rows)
        self._session.flush()

        external_rows: list[PersonExternalIdRow] = []
        for imported, person_row in zip(people, person_rows, strict=True):
            for scheme, value in self._external_ids(imported.person).items():
                external_rows.append(
                    PersonExternalIdRow(
                        person_record_id=person_row.id,
                        scheme=scheme,
                        value=value,
                    )
                )
        if external_rows:
            self._session.add_all(external_rows)
            self._session.flush()
        return len(person_rows)

    @staticmethod
    def _require_profile_provenance(
        snapshot: DatasetSnapshotRow,
        people: Sequence[PersonInput],
    ) -> None:
        profile = snapshot.import_config.get("profile")
        structured_profiles = {
            TeiImportProfile.tei_p5_person_register.value,
            TabularImportProfile.tei_equivalent_person_register_v1.value,
        }
        if profile not in structured_profiles:
            msg = f"snapshot {snapshot.id} has unsupported import profile provenance"
            raise InvalidResourceStateError(msg)
        if any(person.name_forms is None for person in people):
            msg = (
                f"snapshot {snapshot.id} uses profile {profile!r} and requires captured name_forms"
            )
            raise InvalidResourceStateError(msg)

    @staticmethod
    def _validate_source_member_artifact(
        snapshot: DatasetSnapshotRow,
        member: SnapshotSourceMemberCreate,
        artifact: ArtifactRow,
        *,
        expected_logical_type: str,
    ) -> None:
        if artifact.project_id != snapshot.project_id:
            msg = "snapshot source-member artifact belongs to a different project"
            raise InvalidResourceStateError(msg)
        if artifact.sha256 != member.sha256:
            msg = "snapshot source-member checksum disagrees with its artifact"
            raise InvalidResourceStateError(msg)
        if artifact.byte_size != member.byte_size:
            msg = "snapshot source-member byte size disagrees with its artifact"
            raise InvalidResourceStateError(msg)
        if artifact.media_type != member.media_type:
            msg = "snapshot source-member media type disagrees with its artifact"
            raise InvalidResourceStateError(msg)
        if artifact.logical_type != expected_logical_type:
            msg = "snapshot source-member artifact has an unsupported logical type"
            raise InvalidResourceStateError(msg)

    def _require_primary_artifact_provenance(
        self,
        *,
        project_id: UUID,
        source_artifact_id: UUID,
        source_sha256: str,
        import_config: SnapshotImportConfig,
    ) -> ArtifactRow:
        artifact = self._session.get(ArtifactRow, source_artifact_id)
        if artifact is None:
            msg = f"source artifact {source_artifact_id} does not exist"
            raise ResourceNotFoundError(msg)
        if artifact.project_id != project_id:
            msg = "snapshot source artifact belongs to a different project"
            raise InvalidResourceStateError(msg)
        if artifact.sha256 != source_sha256:
            msg = "snapshot source artifact checksum disagrees with import provenance"
            raise InvalidResourceStateError(msg)
        if artifact.logical_type != self._expected_primary_logical_type(import_config):
            msg = "snapshot source artifact has an unsupported logical type"
            raise InvalidResourceStateError(msg)
        return artifact

    @staticmethod
    def _expected_primary_logical_type(import_config: SnapshotImportConfig) -> str:
        if import_config.packaging is SourcePackaging.loose:
            return "source_manifest"
        if import_config.packaging is SourcePackaging.zip:
            return "source_zip"
        if import_config.packaging is SourcePackaging.tar_gz:
            return "source_tar_gz"
        return f"source_{import_config.source_format.value}"

    @classmethod
    def _expected_member_logical_type(cls, import_config: SnapshotImportConfig) -> str:
        if import_config.packaging is SourcePackaging.loose:
            return f"source_{import_config.source_format.value}"
        return cls._expected_primary_logical_type(import_config)

    @staticmethod
    def _require_parser_version_provenance(
        *,
        parser_version: str,
        import_config: SnapshotImportConfig,
    ) -> None:
        expected_version = version_for_snapshot_import(import_config)
        if parser_version != expected_version:
            msg = (
                f"snapshot parser version {parser_version!r} does not match "
                f"persisted import provenance; expected {expected_version!r}"
            )
            raise InvalidResourceStateError(msg)

    def _require_source_member_provenance(
        self,
        snapshot: DatasetSnapshotRow,
        people: Sequence[ImportedPerson],
    ) -> None:
        for imported in people:
            if not imported.source_member_name or not imported.source_member_name.strip():
                msg = "person record requires non-blank source_member_name"
                raise InvalidResourceStateError(msg)
            if not imported.source_record_locator or not imported.source_record_locator.strip():
                msg = "person record requires non-blank source_record_locator"
                raise InvalidResourceStateError(msg)

        referenced_names = {imported.source_member_name for imported in people}
        packaging = self._source_packaging(snapshot)
        if packaging in {SourcePackaging.zip, SourcePackaging.tar_gz}:
            source_member_count = self._session.scalar(
                select(func.count(SnapshotSourceMemberRow.id)).where(
                    SnapshotSourceMemberRow.dataset_snapshot_id == snapshot.id
                )
            )
            if source_member_count != 1:
                msg = "an archive snapshot requires exactly one source container"
                raise InvalidResourceStateError(msg)
            return
        persisted_names = set(
            self._session.scalars(
                select(SnapshotSourceMemberRow.logical_name).where(
                    SnapshotSourceMemberRow.dataset_snapshot_id == snapshot.id,
                    SnapshotSourceMemberRow.logical_name.in_(referenced_names),
                )
            )
        )
        if persisted_names != referenced_names:
            msg = "person source_member_name is not attached to the snapshot"
            raise InvalidResourceStateError(msg)

    @classmethod
    def _validated_import_config(
        cls,
        import_config: Mapping[str, object],
        *,
        snapshot_id: UUID | None = None,
    ) -> SnapshotImportConfig:
        try:
            return SnapshotImportConfig.model_validate(import_config)
        except ValidationError as error:
            subject = (
                "snapshot import provenance"
                if snapshot_id is None
                else f"snapshot {snapshot_id} import provenance"
            )
            msg = f"{subject} is not a complete supported import configuration"
            raise InvalidResourceStateError(msg) from error

    def _require_complete_source_provenance(self, snapshot: DatasetSnapshotRow) -> None:
        import_config = self._validated_import_config(
            snapshot.import_config,
            snapshot_id=snapshot.id,
        )
        self._require_parser_version_provenance(
            parser_version=snapshot.parser_version,
            import_config=import_config,
        )
        rows = tuple(
            self._session.scalars(
                select(SnapshotSourceMemberRow)
                .where(SnapshotSourceMemberRow.dataset_snapshot_id == snapshot.id)
                .order_by(SnapshotSourceMemberRow.ordinal)
            )
        )
        self._require_primary_artifact_provenance(
            project_id=snapshot.project_id,
            source_artifact_id=snapshot.source_artifact_id,
            source_sha256=snapshot.source_sha256,
            import_config=import_config,
        )
        if not rows:
            msg = "manifest-aware snapshots require a complete source-member set"
            raise InvalidResourceStateError(msg)
        if len(rows) > import_config.limits.max_member_count:
            msg = "snapshot source exceeds its persisted member-count limit"
            raise InvalidResourceStateError(msg)
        if [row.ordinal for row in rows] != list(range(len(rows))):
            msg = "snapshot source-member ordinals must be unique and contiguous from zero"
            raise InvalidResourceStateError(msg)
        if import_config.packaging is not SourcePackaging.loose and len(rows) != 1:
            msg = "single-file and archive snapshots require exactly one source container"
            raise InvalidResourceStateError(msg)
        if (
            import_config.packaging is not SourcePackaging.loose
            and rows[0].artifact_id != snapshot.source_artifact_id
        ):
            msg = "single-file and archive source member must be the primary source artifact"
            raise InvalidResourceStateError(msg)

        try:
            members = tuple(
                SnapshotSourceMemberCreate(
                    artifact_id=row.artifact_id,
                    ordinal=row.ordinal,
                    logical_name=row.logical_name,
                    sha256=row.sha256,
                    byte_size=row.byte_size,
                    media_type=row.media_type,
                )
                for row in rows
            )
        except ValidationError as error:
            msg = "snapshot source-member provenance is invalid"
            raise InvalidResourceStateError(msg) from error
        if any(
            member.logical_name != row.logical_name
            for member, row in zip(members, rows, strict=True)
        ):
            msg = "snapshot source-member logical names are not canonical"
            raise InvalidResourceStateError(msg)
        logical_names = [member.logical_name.casefold() for member in members]
        if len(logical_names) != len(set(logical_names)):
            msg = "snapshot source-member logical names must be unique"
            raise InvalidResourceStateError(msg)
        basenames = [PurePosixPath(member.logical_name).name.casefold() for member in members]
        if len(basenames) != len(set(basenames)):
            msg = "snapshot source-member basenames must be unique"
            raise InvalidResourceStateError(msg)

        artifact_ids = {member.artifact_id for member in members}
        artifacts = {
            artifact.id: artifact
            for artifact in self._session.scalars(
                select(ArtifactRow).where(ArtifactRow.id.in_(artifact_ids))
            )
        }
        if artifacts.keys() != artifact_ids:
            msg = "one or more snapshot source-member artifacts do not exist"
            raise ResourceNotFoundError(msg)
        expected_logical_type = self._expected_member_logical_type(import_config)
        for member in members:
            self._validate_source_member_artifact(
                snapshot,
                member,
                artifacts[member.artifact_id],
                expected_logical_type=expected_logical_type,
            )

    @staticmethod
    def _source_packaging(snapshot: DatasetSnapshotRow) -> SourcePackaging:
        raw_packaging = snapshot.import_config.get("packaging", SourcePackaging.single.value)
        try:
            return SourcePackaging(raw_packaging)
        except (TypeError, ValueError) as error:
            msg = f"snapshot {snapshot.id} has unsupported source packaging"
            raise InvalidResourceStateError(msg) from error

    def get_person_record_by_tei_id(
        self,
        snapshot_id: UUID,
        tei_id: str,
    ) -> PersonRecord | None:
        """Return one person contract by its snapshot-scoped canonical identity."""
        row = self._session.scalar(
            select(PersonRecordRow).where(
                PersonRecordRow.dataset_snapshot_id == snapshot_id,
                PersonRecordRow.tei_id == tei_id,
            )
        )
        if row is None:
            return None
        return self._person_from_row(row, self._external_ids_for([row.id]).get(row.id, ()))

    def list_person_records(
        self,
        snapshot_id: UUID,
        *,
        limit: int,
        after_tei_id: str | None = None,
        after_person_record_id: UUID | None = None,
    ) -> Sequence[PersonRecord]:
        """Return people in stable TEI-ID order using keyset continuation."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        if (after_tei_id is None) != (after_person_record_id is None):
            msg = "person cursor fields must be supplied together"
            raise ValueError(msg)
        statement = select(PersonRecordRow).where(
            PersonRecordRow.dataset_snapshot_id == snapshot_id
        )
        if after_tei_id is not None and after_person_record_id is not None:
            statement = statement.where(
                or_(
                    PersonRecordRow.tei_id > after_tei_id,
                    and_(
                        PersonRecordRow.tei_id == after_tei_id,
                        PersonRecordRow.id > after_person_record_id,
                    ),
                )
            )
        rows = tuple(
            self._session.scalars(
                statement.order_by(PersonRecordRow.tei_id, PersonRecordRow.id).limit(limit)
            )
        )
        identifiers = self._external_ids_for([row.id for row in rows])
        return tuple(self._person_from_row(row, identifiers.get(row.id, ())) for row in rows)

    def list_person_records_slice(
        self,
        snapshot_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[PersonRecord]:
        """Return one contiguous ``(tei_id, id)``-ordered person slice by offset."""
        if offset < 0:
            msg = "offset must not be negative"
            raise ValueError(msg)
        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        rows = tuple(
            self._session.scalars(
                select(PersonRecordRow)
                .where(PersonRecordRow.dataset_snapshot_id == snapshot_id)
                .order_by(PersonRecordRow.tei_id, PersonRecordRow.id)
                .offset(offset)
                .limit(limit)
            )
        )
        identifiers = self._external_ids_for([row.id for row in rows])
        return tuple(self._person_from_row(row, identifiers.get(row.id, ())) for row in rows)

    def complete_snapshot_import(
        self,
        snapshot_id: UUID,
        *,
        statistics: DatasetSnapshotStatistics,
        ready_at: datetime,
    ) -> DatasetSnapshot:
        """Lock and make an importing snapshot immutable and ready."""
        row = self._locked_snapshot(snapshot_id)
        self._require_snapshot_status(row, DatasetSnapshotStatus.importing)
        self._require_complete_source_provenance(row)
        record_count = self._session.scalar(
            select(func.count(PersonRecordRow.id)).where(
                PersonRecordRow.dataset_snapshot_id == snapshot_id
            )
        )
        if (
            statistics.dataset_snapshot_id != snapshot_id
            or statistics.total_person_count != record_count
        ):
            msg = f"dataset snapshot {snapshot_id} statistics do not match persisted people"
            raise InvalidResourceStateError(msg)
        row.record_count = record_count
        row.statistics = statistics.model_dump(mode="json")
        row.ready_at = normalize_utc_datetime(ready_at)
        row.status = DatasetSnapshotStatus.ready
        self._session.flush()
        return self._snapshot_from_row(row)

    def fail_snapshot_import(
        self,
        snapshot_id: UUID,
        *,
        failure_class: str | None = None,
        failure_diagnostic: str,
    ) -> DatasetSnapshot:
        """Lock and mark a pending or importing snapshot failed."""
        if not failure_diagnostic.strip():
            msg = "failure_diagnostic must not be blank"
            raise ValueError(msg)
        row = self._locked_snapshot(snapshot_id)
        if row.status is DatasetSnapshotStatus.ready:
            msg = f"dataset snapshot {snapshot_id} is ready and immutable"
            raise ImmutableResourceError(msg)
        if row.status is DatasetSnapshotStatus.failed:
            msg = f"dataset snapshot {snapshot_id} is already failed"
            raise InvalidResourceStateError(msg)
        row.status = DatasetSnapshotStatus.failed
        row.failure_class = failure_class
        row.failure_diagnostic = failure_diagnostic
        self._session.flush()
        return self._snapshot_from_row(row)

    def _locked_snapshot(self, snapshot_id: UUID) -> DatasetSnapshotRow:
        row = self._session.scalar(
            select(DatasetSnapshotRow).where(DatasetSnapshotRow.id == snapshot_id).with_for_update()
        )
        if row is None:
            msg = f"dataset snapshot {snapshot_id} does not exist"
            raise ResourceNotFoundError(msg)
        return row

    @staticmethod
    def _require_snapshot_status(
        row: DatasetSnapshotRow,
        expected_status: DatasetSnapshotStatus,
    ) -> None:
        if row.status is DatasetSnapshotStatus.ready:
            msg = f"dataset snapshot {row.id} is ready and immutable"
            raise ImmutableResourceError(msg)
        if row.status is not expected_status:
            msg = (
                f"dataset snapshot {row.id} has status {row.status.value}; "
                f"expected {expected_status.value}"
            )
            raise InvalidResourceStateError(msg)

    def _external_ids_for(
        self,
        person_record_ids: Sequence[UUID],
    ) -> dict[UUID, tuple[PersonExternalIdRow, ...]]:
        if not person_record_ids:
            return {}
        rows = self._session.scalars(
            select(PersonExternalIdRow)
            .where(PersonExternalIdRow.person_record_id.in_(person_record_ids))
            .order_by(PersonExternalIdRow.scheme)
        )
        grouped: defaultdict[UUID, list[PersonExternalIdRow]] = defaultdict(list)
        for row in rows:
            grouped[row.person_record_id].append(row)
        return {person_id: tuple(identifiers) for person_id, identifiers in grouped.items()}

    @staticmethod
    def _external_ids(person: PersonInput) -> dict[str, str]:
        external_ids = dict(person.external_ids)
        if person.gnd_id is not None:
            existing_gnd_id = external_ids.get("gnd")
            if existing_gnd_id is not None and existing_gnd_id != person.gnd_id:
                msg = "gnd_id conflicts with external_ids['gnd']"
                raise ValueError(msg)
            external_ids["gnd"] = person.gnd_id
        return dict(sorted(external_ids.items()))

    def _require_team(self, team_id: UUID) -> TeamRow:
        """Return a project's referentially required team row."""
        team = self._session.get(TeamRow, team_id)
        if team is None:
            msg = f"team {team_id} does not exist"
            raise RuntimeError(msg)
        return team

    @staticmethod
    def _project_from_row(row: ProjectRow, team: TeamRow) -> Project:
        return Project(
            id=row.id,
            slug=row.slug,
            display_name=row.display_name,
            description=row.description,
            team=TeamSummary(
                id=team.id,
                slug=team.slug,
                display_name=team.display_name,
                created_at=team.created_at,
                updated_at=team.updated_at,
            ),
            manager_user_id=row.manager_user_id,
            created_by_user_id=row.created_by_user_id,
            created_at=row.created_at,
            working_aggregation_execution_id=row.working_aggregation_execution_id,
            game_mode_enabled=row.game_mode_enabled,
        )

    @staticmethod
    def _snapshot_from_row(row: DatasetSnapshotRow) -> DatasetSnapshot:
        return DatasetSnapshot(
            id=row.id,
            project_id=row.project_id,
            source_artifact_id=row.source_artifact_id,
            source_sha256=row.source_sha256,
            parser_version=row.parser_version,
            import_config=row.import_config,
            status=row.status,
            record_count=row.record_count,
            ready_at=row.ready_at,
            failure_class=row.failure_class,
            failure_diagnostic=row.failure_diagnostic,
            created_at=row.created_at,
        )

    @staticmethod
    def _aggregation_from_row(
        row: AggregationExecutionRow,
        method_execution_ids: tuple[UUID, ...],
    ) -> AggregationExecution:
        return AggregationExecution(
            id=row.id,
            run_id=row.run_id,
            strategy=AggregationStrategy(row.strategy),
            resolved_config=row.resolved_config,
            method_execution_ids=method_execution_ids,
            config_sha256=row.config_sha256,
            status=row.status,
            started_at=row.started_at,
            finished_at=row.finished_at,
            failure_class=row.failure_class,
            failure_diagnostic=row.failure_diagnostic,
            created_at=row.created_at,
        )

    @staticmethod
    def _run_from_row(row: RunRow, *, progress: Progress | None = None) -> Run:
        return Run(
            id=row.id,
            dataset_snapshot_id=row.dataset_snapshot_id,
            resolved_config=RunConfig.model_validate(row.resolved_config),
            config_sha256=row.config_sha256,
            status=row.status,
            code_git_commit=row.code_git_commit,
            application_version=row.application_version,
            container_image_digest=row.container_image_digest,
            python_version=row.python_version,
            dependency_lock_sha256=row.dependency_lock_sha256,
            dependency_lock_artifact_id=row.dependency_lock_artifact_id,
            started_at=row.started_at,
            finished_at=row.finished_at,
            failure_class=row.failure_class,
            failure_diagnostic=row.failure_diagnostic,
            created_at=row.created_at,
            progress=Progress(total=None, completed=0, failed=0, percentage=None)
            if progress is None
            else progress,
        )

    def _method_execution_ids_by_aggregation(
        self,
        aggregation_execution_ids: Sequence[UUID],
    ) -> dict[UUID, tuple[UUID, ...]]:
        selections: defaultdict[UUID, list[UUID]] = defaultdict(list)
        if aggregation_execution_ids:
            for aggregation_execution_id, method_execution_id in self._session.execute(
                select(
                    AggregationMethodExecutionRow.aggregation_execution_id,
                    AggregationMethodExecutionRow.method_execution_id,
                )
                .where(
                    AggregationMethodExecutionRow.aggregation_execution_id.in_(
                        aggregation_execution_ids
                    )
                )
                .order_by(
                    AggregationMethodExecutionRow.aggregation_execution_id,
                    AggregationMethodExecutionRow.position,
                )
            ):
                selections[aggregation_execution_id].append(method_execution_id)
        return {
            aggregation_execution_id: tuple(selections[aggregation_execution_id])
            for aggregation_execution_id in aggregation_execution_ids
        }

    def _run_progress_by_id(self, run_ids: Sequence[UUID]) -> dict[UUID, Progress]:
        executions: defaultdict[UUID, list[MethodExecutionRow]] = defaultdict(list)
        if run_ids:
            for row in self._session.scalars(
                select(MethodExecutionRow)
                .where(MethodExecutionRow.run_id.in_(run_ids))
                .order_by(MethodExecutionRow.run_id, MethodExecutionRow.method_name)
            ):
                executions[row.run_id].append(row)
        return {run_id: _progress_of(executions[run_id]) for run_id in run_ids}

    @staticmethod
    def _source_member_from_row(row: SnapshotSourceMemberRow) -> SnapshotSourceMember:
        return SnapshotSourceMember(
            id=row.id,
            dataset_snapshot_id=row.dataset_snapshot_id,
            artifact_id=row.artifact_id,
            ordinal=row.ordinal,
            logical_name=row.logical_name,
            sha256=row.sha256,
            byte_size=row.byte_size,
            media_type=row.media_type,
            created_at=row.created_at,
        )

    @staticmethod
    def _person_from_row(
        row: PersonRecordRow,
        identifiers: Sequence[PersonExternalIdRow],
    ) -> PersonRecord:
        identifier_map = {identifier.scheme: identifier.value for identifier in identifiers}
        return PersonRecord(
            id=row.id,
            dataset_snapshot_id=row.dataset_snapshot_id,
            tei_id=row.tei_id,
            surname=row.surname,
            forenames=row.forenames,
            birth=row.birth,
            death=row.death,
            note=row.note,
            events=[PersonEvent.model_validate(event) for event in row.events],
            alt_names=row.alt_names,
            name_forms=(
                [PersonNameForm.model_validate(name_form) for name_form in row.name_forms]
                if row.name_forms is not None
                else None
            ),
            gnd_id=identifier_map.pop("gnd", None),
            external_ids=identifier_map,
            source_member_name=row.source_member_name,
            source_record_locator=row.source_record_locator,
            created_at=row.created_at,
        )


def _progress_of(executions: Sequence[MethodExecutionRow]) -> Progress:
    """Sum one run's execution counters; total is known only when every execution has one."""
    if not executions:
        return Progress(total=None, completed=0, failed=0, percentage=None)
    totals = [execution.total_count for execution in executions]
    present = [value for value in totals if value is not None]
    total = sum(present) if len(present) == len(totals) else None
    completed = sum(execution.completed_count for execution in executions)
    failed = sum(execution.failed_count for execution in executions)
    return Progress.of(total=total, completed=completed, failed=failed)
