"""Application repository contract for projects, snapshots, and people."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.person import ImportedPerson, PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    Project,
    ProjectCreate,
    SnapshotSourceMember,
    SnapshotSourceMemberCreate,
)


class ProjectRepository(Protocol):
    """Persist canonical project resources without owning the transaction."""

    def add_project(self, command: ProjectCreate) -> Project:
        """Persist and return a new project in the current transaction."""
        ...

    def get_project(self, project_id: UUID) -> Project | None:
        """Return a project by ID, or ``None`` when absent."""
        ...

    def get_project_by_slug(self, slug: str) -> Project | None:
        """Return a project by its unique slug, or ``None`` when absent."""
        ...

    def list_projects(
        self,
        *,
        limit: int,
        after_slug: str | None = None,
    ) -> Sequence[Project]:
        """Return one keyset slice of every project in unique-slug order."""
        ...

    def add_snapshot(self, command: DatasetSnapshotCreate) -> DatasetSnapshot:
        """Persist and return a new pending dataset snapshot."""
        ...

    def get_snapshot(self, snapshot_id: UUID) -> DatasetSnapshot | None:
        """Return a snapshot by ID, or ``None`` when absent."""
        ...

    def add_snapshot_source_members(
        self,
        snapshot_id: UUID,
        members: Sequence[SnapshotSourceMemberCreate],
    ) -> Sequence[SnapshotSourceMember]:
        """Persist an ordered source manifest for one pending snapshot."""
        ...

    def list_snapshot_source_members(
        self,
        snapshot_id: UUID,
    ) -> Sequence[SnapshotSourceMember]:
        """Return source members in canonical ordinal order."""
        ...

    def begin_snapshot_import(self, snapshot_id: UUID) -> DatasetSnapshot:
        """Move a pending snapshot into its importing state."""
        ...

    def claim_snapshot_import(self, snapshot_id: UUID) -> DatasetSnapshot | None:
        """Atomically claim a pending snapshot, or return ``None`` if already claimed."""
        ...

    def add_imported_person_records(
        self,
        snapshot_id: UUID,
        people: Sequence[ImportedPerson],
    ) -> int:
        """Persist people with non-null source-member record provenance."""
        ...

    def get_person_record_by_tei_id(
        self,
        snapshot_id: UUID,
        tei_id: str,
    ) -> PersonRecord | None:
        """Return one person occurrence by snapshot-scoped TEI identity."""
        ...

    def list_person_records(
        self,
        snapshot_id: UUID,
        *,
        limit: int,
        after_tei_id: str | None = None,
        after_person_record_id: UUID | None = None,
    ) -> Sequence[PersonRecord]:
        """Return one stable ``(tei_id, id)`` keyset slice."""
        ...

    def list_person_records_slice(
        self,
        snapshot_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[PersonRecord]:
        """Return one contiguous ``(tei_id, id)``-ordered person slice by offset."""
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
