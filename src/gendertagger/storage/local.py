"""Content-addressed local filesystem artifact storage."""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import BinaryIO, Protocol, cast

from gendertagger.models.project import SHA256_PATTERN
from gendertagger.services.artifact_storage import ArtifactStorage, StoredArtifact

_STORAGE_URI_PREFIX = "local-sha256:"
_COPY_BUFFER_BYTE_SIZE = 1024 * 1024


class _ReadIntoSource(Protocol):
    def readinto(self, buffer: bytearray) -> int | None:
        """Read bytes into a reusable buffer."""
        ...


class ArtifactStorageError(RuntimeError):
    """Base failure for local artifact persistence or retrieval."""


class ArtifactTooLargeError(ArtifactStorageError):
    """Raised after an upload exceeds its configured byte limit."""


class ArtifactIntegrityError(ArtifactStorageError):
    """Raised when content-addressed bytes do not match their locator."""


class LocalArtifactStorage(ArtifactStorage):
    """Store immutable artifacts under SHA-256-derived private paths."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def store(self, source: BinaryIO, *, max_byte_size: int) -> StoredArtifact:
        """Stream to a private temporary file and publish by atomic hard link."""
        if max_byte_size <= 0:
            msg = "max_byte_size must be positive"
            raise ValueError(msg)
        temporary_directory = self._root / ".tmp"
        self._ensure_directory(temporary_directory)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                dir=temporary_directory,
                prefix="upload-",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                digest, byte_size = self._copy_and_hash(
                    source,
                    cast(BinaryIO, temporary_file),
                    max_byte_size=max_byte_size,
                )
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            destination = self._path_for_digest(digest)
            self._ensure_directory(destination.parent)
            try:
                os.link(temporary_path, destination)
            except FileExistsError:
                self._verify_path(destination, expected_digest=digest)
            self._fsync_directory(destination.parent)
            return StoredArtifact(
                storage_uri=f"{_STORAGE_URI_PREFIX}{digest}",
                sha256=digest,
                byte_size=byte_size,
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def open(self, storage_uri: str) -> BinaryIO:
        """Open a digest locator without following a substituted symlink."""
        digest = self._digest_from_uri(storage_uri)
        path = self._path_for_digest(digest)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as error:
            msg = "stored artifact is unavailable"
            raise ArtifactStorageError(msg) from error
        return os.fdopen(descriptor, "rb")

    @staticmethod
    def _copy_and_hash(
        source: BinaryIO,
        destination: BinaryIO,
        *,
        max_byte_size: int,
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        byte_size = 0
        buffer = bytearray(_COPY_BUFFER_BYTE_SIZE)
        buffer_view = memoryview(buffer)
        reader = cast(_ReadIntoSource, source)
        while True:
            bytes_read = reader.readinto(buffer)
            if bytes_read is None:
                msg = "artifact source did not return a byte count"
                raise ArtifactStorageError(msg)
            if bytes_read == 0:
                break
            byte_size += bytes_read
            if byte_size > max_byte_size:
                msg = f"artifact exceeds the {max_byte_size}-byte upload limit"
                raise ArtifactTooLargeError(msg)
            chunk = buffer_view[:bytes_read]
            digest.update(chunk)
            destination.write(chunk)
        return digest.hexdigest(), byte_size

    def _path_for_digest(self, digest: str) -> Path:
        return self._root / digest[:2] / digest

    @classmethod
    def _ensure_directory(cls, path: Path) -> None:
        """Create a private directory tree and durably record new entries."""
        missing: list[Path] = []
        candidate = path
        while not candidate.exists():
            missing.append(candidate)
            parent = candidate.parent
            if parent == candidate:  # pragma: no cover - filesystem root always exists.
                break
            candidate = parent

        for directory in reversed(missing):
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError:
                if not directory.is_dir():
                    raise
            # Another process may have won the mkdir race after our existence
            # check. Fsync in either case because we observed the entry missing.
            cls._fsync_directory(directory)
            cls._fsync_directory(directory.parent)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        """Persist directory metadata where the platform exposes that operation."""
        if os.name == "nt":  # Windows does not expose directory fsync through os.open.
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _digest_from_uri(storage_uri: str) -> str:
        if not storage_uri.startswith(_STORAGE_URI_PREFIX):
            msg = "unsupported artifact storage URI"
            raise ArtifactStorageError(msg)
        digest = storage_uri.removeprefix(_STORAGE_URI_PREFIX)

        if re.fullmatch(SHA256_PATTERN, digest) is None:
            msg = "invalid content-addressed artifact URI"
            raise ArtifactStorageError(msg)
        return digest

    @staticmethod
    def _verify_path(path: Path, *, expected_digest: str) -> None:
        digest = hashlib.sha256()
        buffer = bytearray(_COPY_BUFFER_BYTE_SIZE)
        buffer_view = memoryview(buffer)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as existing_file:
                reader = cast(_ReadIntoSource, existing_file)
                while bytes_read := reader.readinto(buffer):
                    digest.update(buffer_view[:bytes_read])
        except OSError as error:
            msg = "existing content-addressed artifact is unavailable"
            raise ArtifactIntegrityError(msg) from error
        if digest.hexdigest() != expected_digest:
            msg = "existing content-addressed artifact failed integrity validation"
            raise ArtifactIntegrityError(msg)
