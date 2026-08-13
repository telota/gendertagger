"""Application repository contract for projects, snapshots, and people."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.person import PersonInput, PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
)


class ProjectRepository(Protocol):
    """Persist canonical project resources without owning the transaction."""

    def add_project(self, command: ProjectCreate) -> Project:
        """Persist and return a new project in the current transaction."""
        ...

    def get_project(self, project_id: UUID) -> Project | None:
        """Return a project by ID, or ``None`` when absent."""
        ...

    def add_snapshot(self, command: DatasetSnapshotCreate) -> DatasetSnapshot:
        """Persist and return a new pending dataset snapshot."""
        ...

    def get_snapshot(self, snapshot_id: UUID) -> DatasetSnapshot | None:
        """Return a snapshot by ID, or ``None`` when absent."""
        ...

    def begin_snapshot_import(self, snapshot_id: UUID) -> DatasetSnapshot:
        """Move a pending snapshot into its importing state."""
        ...

    def add_person_records(
        self,
        snapshot_id: UUID,
        people: Sequence[PersonInput],
    ) -> int:
        """Persist one bounded person batch and return its record count."""
        ...

    def get_person_record(self, person_record_id: UUID) -> PersonRecord | None:
        """Return one person occurrence by persistence ID."""
        ...

    def get_person_record_by_tei_id(
        self,
        snapshot_id: UUID,
        tei_id: str,
    ) -> PersonRecord | None:
        """Return one person occurrence by snapshot-scoped TEI identity."""
        ...

    def complete_snapshot_import(
        self,
        snapshot_id: UUID,
        *,
        ready_at: datetime,
    ) -> DatasetSnapshot:
        """Atomically mark an importing snapshot ready with its persisted count."""
        ...

    def fail_snapshot_import(
        self,
        snapshot_id: UUID,
        *,
        failure_diagnostic: str,
    ) -> DatasetSnapshot:
        """Mark a pending or importing snapshot failed with a sanitized diagnostic."""
        ...
