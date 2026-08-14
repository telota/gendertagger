import hashlib
import os
from io import BytesIO
from pathlib import Path

import pytest

from gendertagger.storage.local import (
    ArtifactIntegrityError,
    ArtifactStorageError,
    ArtifactTooLargeError,
    LocalArtifactStorage,
)

SOURCE_BYTES = b"exact source bytes\n\x00"


def test_storage_streams_exact_content_to_internal_digest_locator(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)

    stored = storage.store(BytesIO(SOURCE_BYTES), max_byte_size=len(SOURCE_BYTES))
    duplicate = storage.store(BytesIO(SOURCE_BYTES), max_byte_size=len(SOURCE_BYTES))

    assert stored.sha256 == hashlib.sha256(SOURCE_BYTES).hexdigest()
    assert stored.byte_size == len(SOURCE_BYTES)
    assert stored.storage_uri == f"local-sha256:{stored.sha256}"
    assert duplicate == stored
    with storage.open(stored.storage_uri) as reopened:
        assert reopened.read() == SOURCE_BYTES


def test_storage_removes_partial_file_after_size_limit_failure(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)

    with pytest.raises(ArtifactTooLargeError, match="4-byte upload limit"):
        storage.store(BytesIO(b"12345"), max_byte_size=4)

    assert list((tmp_path / ".tmp").iterdir()) == []


def test_storage_rejects_invalid_locator_and_corrupted_existing_content(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)
    stored = storage.store(BytesIO(SOURCE_BYTES), max_byte_size=len(SOURCE_BYTES))
    digest_path = tmp_path / stored.sha256[:2] / stored.sha256
    digest_path.write_bytes(b"corrupted")

    with pytest.raises(ArtifactStorageError, match="unsupported"):
        storage.open("file:///untrusted/path")
    with pytest.raises(ArtifactIntegrityError, match="integrity"):
        storage.store(BytesIO(SOURCE_BYTES), max_byte_size=len(SOURCE_BYTES))


def test_storage_fsyncs_new_directory_entries_and_published_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "new-artifact-root"
    storage = LocalArtifactStorage(root)
    events: list[tuple[str, Path]] = []
    real_link = os.link

    def record_directory_sync(path: Path) -> None:
        events.append(("fsync", path))

    def record_link(source: Path, destination: Path) -> None:
        events.append(("link", destination.parent))
        real_link(source, destination)

    monkeypatch.setattr(
        LocalArtifactStorage,
        "_fsync_directory",
        staticmethod(record_directory_sync),
    )
    monkeypatch.setattr(os, "link", record_link)

    stored = storage.store(BytesIO(SOURCE_BYTES), max_byte_size=len(SOURCE_BYTES))

    destination_parent = root / stored.sha256[:2]
    link_index = events.index(("link", destination_parent))
    assert ("fsync", root.parent) in events
    assert ("fsync", root) in events
    assert ("fsync", destination_parent) in events[link_index + 1 :]


def test_duplicate_store_still_fsyncs_the_existing_digest_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = LocalArtifactStorage(tmp_path)
    stored = storage.store(BytesIO(SOURCE_BYTES), max_byte_size=len(SOURCE_BYTES))
    synced_directories: list[Path] = []
    monkeypatch.setattr(
        LocalArtifactStorage,
        "_fsync_directory",
        staticmethod(synced_directories.append),
    )

    duplicate = storage.store(BytesIO(SOURCE_BYTES), max_byte_size=len(SOURCE_BYTES))

    assert duplicate == stored
    assert synced_directories == [tmp_path / stored.sha256[:2]]
