"""SQLAlchemy repository for immutable checksummed artifact records."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gendertagger.db.rows.artifacts import ArtifactRow
from gendertagger.models.artifact import Artifact, ArtifactCreate
from gendertagger.services.ports.artifact_repository import AmbiguousArtifactError


class SqlAlchemyArtifactRepository:
    """Map artifact contracts to rows within a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_artifact(self, command: ArtifactCreate) -> Artifact:
        """Persist and flush immutable artifact metadata without committing."""
        row = ArtifactRow(
            logical_type=command.logical_type,
            storage_uri=command.storage_uri,
            sha256=command.sha256,
            byte_size=command.byte_size,
            media_type=command.media_type,
            project_id=command.project_id,
            dataset_snapshot_id=command.dataset_snapshot_id,
            run_id=command.run_id,
            method_execution_id=command.method_execution_id,
            aggregation_execution_id=command.aggregation_execution_id,
            evaluation_execution_id=command.evaluation_execution_id,
            export_execution_id=command.export_execution_id,
            artifact_metadata=command.metadata,
        )
        self._session.add(row)
        self._session.flush()
        return self._artifact_from_row(row)

    def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        """Return an artifact contract by ID without exposing its row."""
        row = self._session.get(ArtifactRow, artifact_id)
        return None if row is None else self._artifact_from_row(row)

    def get_artifact_by_sha256(self, logical_type: str, sha256: str) -> Artifact | None:
        """Return one matching artifact without exposing its row."""
        statement = (
            select(ArtifactRow)
            .where(
                ArtifactRow.logical_type == logical_type,
                ArtifactRow.sha256 == sha256,
            )
            .order_by(ArtifactRow.created_at, ArtifactRow.id)
            .limit(2)
        )
        rows = tuple(self._session.scalars(statement))
        if len(rows) > 1:
            msg = f"artifact identity {logical_type}:{sha256} is ambiguous"
            raise AmbiguousArtifactError(msg)
        return None if not rows else self._artifact_from_row(rows[0])

    def get_latest_artifact(self, logical_type: str) -> Artifact | None:
        """Return the most recently registered artifact for one logical type, or ``None``."""
        statement = (
            select(ArtifactRow)
            .where(ArtifactRow.logical_type == logical_type)
            .order_by(ArtifactRow.created_at.desc(), ArtifactRow.id.desc())
            .limit(1)
        )
        row = self._session.scalars(statement).first()
        return None if row is None else self._artifact_from_row(row)

    def list_artifacts_by_export(self, export_execution_id: UUID) -> Sequence[Artifact]:
        """Return every artifact produced by one export, in creation order."""
        rows = self._session.scalars(
            select(ArtifactRow)
            .where(ArtifactRow.export_execution_id == export_execution_id)
            .order_by(ArtifactRow.created_at, ArtifactRow.id)
        )
        return tuple(self._artifact_from_row(row) for row in rows)

    @staticmethod
    def _artifact_from_row(row: ArtifactRow) -> Artifact:
        return Artifact(
            id=row.id,
            logical_type=row.logical_type,
            storage_uri=row.storage_uri,
            sha256=row.sha256,
            byte_size=row.byte_size,
            media_type=row.media_type,
            project_id=row.project_id,
            dataset_snapshot_id=row.dataset_snapshot_id,
            run_id=row.run_id,
            method_execution_id=row.method_execution_id,
            aggregation_execution_id=row.aggregation_execution_id,
            evaluation_execution_id=row.evaluation_execution_id,
            export_execution_id=row.export_execution_id,
            metadata=row.artifact_metadata,
            created_at=row.created_at,
        )
