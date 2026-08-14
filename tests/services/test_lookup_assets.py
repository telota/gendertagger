from __future__ import annotations

from pathlib import Path

import pytest

from gendertagger.methods.base import MethodDependencyError
from gendertagger.services.lookup_assets import (
    LookupAssetRegistrationService,
    RegisteredLookupAssetResolver,
)
from gendertagger.services.unit_of_work import UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

pytestmark = pytest.mark.postgres


def test_registration_and_resolution_are_content_addressed_and_idempotent(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, object],
    tmp_path: Path,
) -> None:
    unit_of_work_factory, _ = postgres_unit_of_work
    storage = LocalArtifactStorage(tmp_path / "artifacts")
    registration = LookupAssetRegistrationService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
        max_byte_size=1024,
    )
    source = tmp_path / "lookup.sqlite3"
    source.write_bytes(b"immutable lookup bytes")

    first = registration.register_file(
        source,
        logical_type="test_lookup",
        media_type="application/vnd.sqlite3",
        metadata={"method_name": "test"},
    )
    second = registration.register_file(
        source,
        logical_type="test_lookup",
        media_type="application/vnd.sqlite3",
        metadata={"method_name": "test"},
    )
    source.write_bytes(b"mutated source path")

    resolver = RegisteredLookupAssetResolver(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=storage,
    )
    resolved = resolver.materialize("test_lookup", first.sha256)

    assert second.id == first.id
    assert resolved.read_bytes() == b"immutable lookup bytes"
    assert resolver.materialize("test_lookup", first.sha256) == resolved


def test_resolution_rejects_an_unregistered_digest(
    postgres_unit_of_work: tuple[UnitOfWorkFactory, object],
    tmp_path: Path,
) -> None:
    unit_of_work_factory, _ = postgres_unit_of_work
    resolver = RegisteredLookupAssetResolver(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=LocalArtifactStorage(tmp_path / "artifacts"),
    )

    with pytest.raises(MethodDependencyError, match="does not exist"):
        resolver.materialize("test_lookup", "f" * 64)
