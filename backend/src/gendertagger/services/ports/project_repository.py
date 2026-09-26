"""Application repository contract for projects, snapshots, and people."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.person import ImportedPerson, PersonRecord
from gendertagger.models.project import (
    DatasetSnapshot,
    DatasetSnapshotCreate,
    DatasetSnapshotListFilter,
    DatasetSnapshotStatistics,
    Project,
    ProjectCreate,
    ProjectDataAvailability,
    SnapshotSourceMember,
    SnapshotSourceMemberCreate,
)
from gendertagger.models.task import ProjectReviewResult
from gendertagger.services.pagination import CreationPosition


class ProjectRepository(Protocol):
    """Persist canonical project resources without owning the transaction."""

    def add_project(
        self,
        command: ProjectCreate,
        *,
        manager_user_id: UUID,
        created_by_user_id: UUID,
    ) -> Project:
        """Persist a validated team-owned project without committing."""
        ...

    def get_project(self, project_id: UUID) -> Project | None:
        """Return a project by ID, or ``None`` when absent."""
        ...

    def get_data_availability(self, project_id: UUID) -> ProjectDataAvailability | None:
        """Return project-wide data existence, or ``None`` if the project is absent."""
        ...

    def get_project_for_update(self, project_id: UUID) -> Project | None:
        """Return one project under a write lock, or ``None`` when absent."""
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

    def set_working_aggregation(
        self,
        project_id: UUID,
        *,
        aggregation_execution_id: UUID | None,
    ) -> Project:
        """Point a project at one of its own completed aggregations, or clear the pointer.

        Raises:
            ResourceNotFoundError: If the project does not exist, the aggregation does not
                exist, or the aggregation belongs to a different project.
            InvalidResourceStateError: If the aggregation is not ``completed``.
        """
        ...

    def add_snapshot(self, command: DatasetSnapshotCreate) -> DatasetSnapshot:
        """Persist and return a new pending dataset snapshot."""
        ...

    def get_snapshot(self, snapshot_id: UUID) -> DatasetSnapshot | None:
        """Return a snapshot by ID, or ``None`` when absent."""
        ...

    def get_snapshot_statistics(
        self,
        snapshot_id: UUID,
    ) -> DatasetSnapshotStatistics | None:
        """Return persisted or legacy-derived statistics for a ready snapshot."""
        ...

    def list_snapshots(
        self,
        project_id: UUID,
        *,
        limit: int,
        after: CreationPosition | None = None,
        filters: DatasetSnapshotListFilter | None = None,
    ) -> Sequence[DatasetSnapshot]:
        """Return one newest-first ``(created_at, id)`` keyset slice of a project's snapshots."""
        ...

    def list_review_results(
        self,
        project_id: UUID,
        *,
        limit: int,
        after: CreationPosition | None = None,
    ) -> Sequence[ProjectReviewResult]:
        """Return completed reviewable results newest first for one project."""
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
        statistics: DatasetSnapshotStatistics,
        ready_at: datetime,
    ) -> DatasetSnapshot:
        """Atomically mark an importing snapshot ready with its count and statistics."""
        ...

    def fail_snapshot_import(
        self,
        snapshot_id: UUID,
        *,
        failure_class: str | None = None,
        failure_diagnostic: str,
    ) -> DatasetSnapshot:
        """Mark a pending or importing snapshot failed with a sanitized diagnostic."""
        ...
