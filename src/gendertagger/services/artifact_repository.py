"""Application repository contract for immutable artifact records."""

from typing import Protocol
from uuid import UUID

from gendertagger.models.artifact import Artifact, ArtifactCreate


class ArtifactRepository(Protocol):
    """Persist checksummed artifact metadata without owning the transaction."""

    def add_artifact(self, command: ArtifactCreate) -> Artifact:
        """Persist an immutable reference to externally stored bytes."""
        ...

    def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        """Return an artifact by ID, or ``None`` when absent."""
        ...
