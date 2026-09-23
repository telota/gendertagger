"""Application boundary for immutable binary artifact storage."""

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """Content-addressed metadata returned after durable storage."""

    storage_uri: str
    sha256: str
    byte_size: int


class ArtifactStorage(Protocol):
    """Store and reopen immutable bytes without exposing filesystem paths."""

    def store(self, source: BinaryIO, *, max_byte_size: int) -> StoredArtifact:
        """Persist bytes atomically while hashing and enforcing a size limit."""
        ...

    def open(self, storage_uri: str) -> BinaryIO:
        """Open a validated internal locator for binary reading."""
        ...

    def materialize(self, storage_uri: str) -> Path:
        """Return a verified stable local path for file-oriented consumers."""
        ...
