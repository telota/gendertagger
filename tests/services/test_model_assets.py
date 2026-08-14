from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from gendertagger.methods.base import MethodDependencyError
from gendertagger.methods.model_manifest import UnavailableModelDirectoryResolver
from gendertagger.models.artifact import ModelManifestMember, ModelManifestMetadata
from gendertagger.services.model_assets import RegisteredModelDirectoryResolver

pytestmark = pytest.mark.unit

_MANIFEST_LOGICAL_TYPE = "hf_distilbert_model_manifest"
_MEMBER_LOGICAL_TYPE = "hf_distilbert_model_file"
_MANIFEST_SHA256 = "c" * 64
_CONFIG_SHA256 = "a" * 64
_WEIGHTS_SHA256 = "b" * 64


class _FakeLookupAssetResolver:
    def __init__(self, files: dict[tuple[str, str], Path]) -> None:
        self._files = files
        self.calls: list[tuple[str, str]] = []

    def materialize(self, logical_type: str, sha256: str) -> Path:
        self.calls.append((logical_type, sha256))
        return self._files[(logical_type, sha256)]


def _build_resolver(tmp_path: Path) -> _FakeLookupAssetResolver:
    sources = tmp_path / "sources"
    sources.mkdir()
    config_source = sources / "config-source"
    config_source.write_bytes(b'{"hidden_size": 768}')
    weights_source = sources / "weights-source"
    weights_source.write_bytes(b"weights-bytes")

    manifest = ModelManifestMetadata(
        method_name="hf_distilbert",
        model_schema_version="hf_distilbert_model_v1",
        compiler_version="hf_model_manifest_compiler_v1",
        source_identifier="padmajabfrl/Gender-Classification",
        source_revision="a" * 40,
        members=(
            ModelManifestMember(
                relative_path="config.json",
                artifact_id=uuid4(),
                sha256=_CONFIG_SHA256,
                byte_size=config_source.stat().st_size,
            ),
            ModelManifestMember(
                relative_path="model.safetensors",
                artifact_id=uuid4(),
                sha256=_WEIGHTS_SHA256,
                byte_size=weights_source.stat().st_size,
            ),
        ),
    )
    manifest_path = tmp_path / "manifest-store" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")

    return _FakeLookupAssetResolver(
        {
            (_MANIFEST_LOGICAL_TYPE, _MANIFEST_SHA256): manifest_path,
            (_MEMBER_LOGICAL_TYPE, _CONFIG_SHA256): config_source,
            (_MEMBER_LOGICAL_TYPE, _WEIGHTS_SHA256): weights_source,
        }
    )


def _materialize(
    resolver: _FakeLookupAssetResolver,
    tmp_path: Path,
    *,
    manifest_sha256: str = _MANIFEST_SHA256,
    expected_method_name: str = "hf_distilbert",
) -> Path:
    directory_resolver = RegisteredModelDirectoryResolver(
        lookup_asset_resolver=resolver,
        cache_root=tmp_path / "cache",
    )
    return directory_resolver.materialize_directory(
        manifest_logical_type=_MANIFEST_LOGICAL_TYPE,
        member_logical_type=_MEMBER_LOGICAL_TYPE,
        manifest_sha256=manifest_sha256,
        expected_method_name=expected_method_name,
    )


def test_materialize_directory_places_members_at_their_relative_paths(tmp_path: Path) -> None:
    resolver = _build_resolver(tmp_path)

    directory = _materialize(resolver, tmp_path)

    assert (directory / "config.json").read_bytes() == b'{"hidden_size": 768}'
    assert (directory / "model.safetensors").read_bytes() == b"weights-bytes"


def test_materialize_directory_resolves_the_manifest_and_members_once(tmp_path: Path) -> None:
    resolver = _build_resolver(tmp_path)
    directory_resolver = RegisteredModelDirectoryResolver(
        lookup_asset_resolver=resolver,
        cache_root=tmp_path / "cache",
    )
    kwargs = {
        "manifest_logical_type": _MANIFEST_LOGICAL_TYPE,
        "member_logical_type": _MEMBER_LOGICAL_TYPE,
        "manifest_sha256": _MANIFEST_SHA256,
        "expected_method_name": "hf_distilbert",
    }

    first = directory_resolver.materialize_directory(**kwargs)
    second = directory_resolver.materialize_directory(**kwargs)

    assert first == second
    assert resolver.calls == [
        (_MANIFEST_LOGICAL_TYPE, _MANIFEST_SHA256),
        (_MEMBER_LOGICAL_TYPE, _CONFIG_SHA256),
        (_MEMBER_LOGICAL_TYPE, _WEIGHTS_SHA256),
    ]


def test_materialize_directory_rejects_a_mismatched_method_name(tmp_path: Path) -> None:
    resolver = _build_resolver(tmp_path)

    with pytest.raises(MethodDependencyError, match="does not match"):
        _materialize(resolver, tmp_path, expected_method_name="hf_genderize")


def test_materialize_directory_rejects_malformed_manifest_bytes(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("not json", encoding="utf-8")
    resolver = _FakeLookupAssetResolver({(_MANIFEST_LOGICAL_TYPE, "f" * 64): manifest_path})

    with pytest.raises(MethodDependencyError, match="cannot be read or validated"):
        _materialize(resolver, tmp_path, manifest_sha256="f" * 64)


def test_unavailable_resolver_raises_dependency_error() -> None:
    with pytest.raises(MethodDependencyError, match="not configured"):
        UnavailableModelDirectoryResolver().materialize_directory(
            manifest_logical_type=_MANIFEST_LOGICAL_TYPE,
            member_logical_type=_MEMBER_LOGICAL_TYPE,
            manifest_sha256="f" * 64,
            expected_method_name="hf_distilbert",
        )
