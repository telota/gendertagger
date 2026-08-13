"""SQLAlchemy repository for projects, snapshots, and person records."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gendertagger.db.projects import (
    DatasetSnapshotRow,
    PersonExternalIdRow,
    PersonRecordRow,
    ProjectRow,
)
from gendertagger.models.common import normalize_utc_datetime
from gendertagger.models.lifecycle import DatasetSnapshotStatus
from gendertagger.models.person import PersonInput, PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
)
from gendertagger.services.persistence_errors import (
    ImmutableResourceError,
    InvalidResourceStateError,
    ResourceNotFoundError,
)


class SqlAlchemyProjectRepository:
    """Map project contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_project(self, command: ProjectCreate) -> Project:
        """Persist and flush a new project without committing."""
        row = ProjectRow(
            slug=command.slug,
            display_name=command.display_name,
            description=command.description,
        )
        self._session.add(row)
        self._session.flush()
        return self._project_from_row(row)

    def get_project(self, project_id: UUID) -> Project | None:
        """Return a project contract by ID without exposing its row."""
        row = self._session.get(ProjectRow, project_id)
        return None if row is None else self._project_from_row(row)

    def add_snapshot(self, command: DatasetSnapshotCreate) -> DatasetSnapshot:
        """Persist and flush a new pending snapshot without committing."""
        row = DatasetSnapshotRow(
            project_id=command.project_id,
            source_artifact_id=command.source_artifact_id,
            status=DatasetSnapshotStatus.pending,
            source_sha256=command.source_sha256,
            parser_version=command.parser_version,
            import_config=command.import_config,
            record_count=None,
            ready_at=None,
            failure_diagnostic=None,
        )
        self._session.add(row)
        self._session.flush()
        return self._snapshot_from_row(row)

    def get_snapshot(self, snapshot_id: UUID) -> DatasetSnapshot | None:
        """Return a snapshot contract by ID without exposing its row."""
        row = self._session.get(DatasetSnapshotRow, snapshot_id)
        return None if row is None else self._snapshot_from_row(row)

    def begin_snapshot_import(self, snapshot_id: UUID) -> DatasetSnapshot:
        """Lock and move a pending snapshot to importing."""
        row = self._locked_snapshot(snapshot_id)
        self._require_snapshot_status(row, DatasetSnapshotStatus.pending)
        row.status = DatasetSnapshotStatus.importing
        self._session.flush()
        return self._snapshot_from_row(row)

    def add_person_records(
        self,
        snapshot_id: UUID,
        people: Sequence[PersonInput],
    ) -> int:
        """Persist one bounded person batch while the snapshot is importing."""
        snapshot = self._locked_snapshot(snapshot_id)
        self._require_snapshot_status(snapshot, DatasetSnapshotStatus.importing)

        person_rows = [
            PersonRecordRow(
                dataset_snapshot_id=snapshot_id,
                tei_id=person.tei_id,
                surname=person.surname,
                forenames=person.forenames,
                birth=person.birth,
                death=person.death,
                note=person.note,
                alt_names=person.alt_names,
            )
            for person in people
        ]
        self._session.add_all(person_rows)
        self._session.flush()

        external_rows: list[PersonExternalIdRow] = []
        for person, person_row in zip(people, person_rows, strict=True):
            for scheme, value in self._external_ids(person).items():
                external_rows.append(
                    PersonExternalIdRow(
                        person_record_id=person_row.id,
                        scheme=scheme,
                        value=value,
                    )
                )
        self._session.add_all(external_rows)
        self._session.flush()
        return len(person_rows)

    def get_person_record(self, person_record_id: UUID) -> PersonRecord | None:
        """Return one person contract by persistence ID."""
        row = self._session.get(PersonRecordRow, person_record_id)
        if row is None:
            return None
        return self._person_from_row(row, self._external_ids_for([row.id]).get(row.id, ()))

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

    def complete_snapshot_import(
        self,
        snapshot_id: UUID,
        *,
        ready_at: datetime,
    ) -> DatasetSnapshot:
        """Lock and make an importing snapshot immutable and ready."""
        row = self._locked_snapshot(snapshot_id)
        self._require_snapshot_status(row, DatasetSnapshotStatus.importing)
        row.record_count = self._session.scalar(
            select(func.count(PersonRecordRow.id)).where(
                PersonRecordRow.dataset_snapshot_id == snapshot_id
            )
        )
        row.ready_at = normalize_utc_datetime(ready_at)
        row.status = DatasetSnapshotStatus.ready
        self._session.flush()
        return self._snapshot_from_row(row)

    def fail_snapshot_import(
        self,
        snapshot_id: UUID,
        *,
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

    @staticmethod
    def _project_from_row(row: ProjectRow) -> Project:
        return Project(
            id=row.id,
            slug=row.slug,
            display_name=row.display_name,
            description=row.description,
            created_at=row.created_at,
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
            failure_diagnostic=row.failure_diagnostic,
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
            alt_names=row.alt_names,
            gnd_id=identifier_map.pop("gnd", None),
            external_ids=identifier_map,
            created_at=row.created_at,
        )
