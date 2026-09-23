"""Application repository contract for immutable artifact records."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from gendertagger.models.artifact import Artifact, ArtifactCreate


class AmbiguousArtifactError(RuntimeError):
    """Raised when a content identity resolves to multiple artifact records."""


class ArtifactRepository(Protocol):
    """Persist checksummed artifact metadata without owning the transaction."""

    def add_artifact(self, command: ArtifactCreate) -> Artifact:
        """Persist an immutable reference to externally stored bytes."""
        ...

    def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        """Return an artifact by ID, or ``None`` when absent."""
        ...

    def get_artifact_by_sha256(self, logical_type: str, sha256: str) -> Artifact | None:
        """Return one content match, ``None`` when absent, or raise on ambiguity."""
        ...

    def get_latest_artifact(self, logical_type: str) -> Artifact | None:
        """Return the most recently registered artifact for one logical type, or ``None``."""
        ...

    def list_artifacts_by_export(self, export_execution_id: UUID) -> Sequence[Artifact]:
        """Return every artifact produced by one export, in creation order."""
        ...
