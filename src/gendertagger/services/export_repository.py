"""Application repository contract for export executions."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.export import ExportExecution, ExportExecutionCreate, ExportInputs
from gendertagger.models.lifecycle import ExportExecutionStatus


class ExportRepository(Protocol):
    """Persist canonical export resources without owning the transaction."""

    def add_export(self, command: ExportExecutionCreate) -> ExportExecution:
        """Persist an export over one locked run and its completed aggregation."""
        ...

    def get_export(self, export_id: UUID) -> ExportExecution | None:
        """Return an export execution by ID, or ``None`` when absent."""
        ...

    def mark_export_queued(self, export_id: UUID) -> ExportExecution:
        """Atomically transition a pending export with durable intent to queued."""
        ...

    def claim_export(
        self,
        export_id: UUID,
        *,
        started_at: datetime,
    ) -> ExportExecution | None:
        """Atomically claim a pending or queued export.

        Return ``None`` when another delivery has already claimed or terminally
        finished the export.
        """
        ...

    def load_export_inputs(self, export_id: UUID) -> ExportInputs:
        """Load every snapshot person's FinalDecision projection and source members."""
        ...

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
        """Finish a running export with a persisted manifest or a diagnostic."""
        ...
