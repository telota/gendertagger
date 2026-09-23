"""Runtime materialization of multi-file content-addressed model artifacts.

A model manifest artifact records the ordered, checksummed member files that
compose one locally loadable model directory (Hugging Face weights, tokenizer,
and config). Workers resolve the manifest and its members through the same
:class:`~gendertagger.methods.sqlite_lookup.LookupAssetResolver` used for
SQLite lookups, then materialize them once per manifest digest into a stable
local directory using their exact relative filenames. Structurally implements
:class:`~gendertagger.methods.model_manifest.ModelDirectoryResolver`. See
ADR-0023 and ADR-0024.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from threading import Lock

from pydantic import ValidationError

from gendertagger.methods.base import MethodDependencyError
from gendertagger.methods.sqlite_lookup import LookupAssetResolver
from gendertagger.models.artifact import ModelManifestMetadata


class RegisteredModelDirectoryResolver:
    """Materialize a registered manifest and its members into a stable directory."""

    def __init__(
        self,
        *,
        lookup_asset_resolver: LookupAssetResolver,
        cache_root: Path,
    ) -> None:
        self._lookup_asset_resolver = lookup_asset_resolver
        self._cache_root = cache_root
        self._directories: dict[tuple[str, str], Path] = {}
        self._lock = Lock()

    def materialize_directory(
        self,
        *,
        manifest_logical_type: str,
        member_logical_type: str,
        manifest_sha256: str,
        expected_method_name: str,
    ) -> Path:
        """Resolve, verify, and materialize a model directory once per process.

        Raises:
            MethodDependencyError: If the manifest cannot be read or does not
                match the expected method, or a member cannot be materialized.
        """
        cache_key = (manifest_logical_type, manifest_sha256)
        cached = self._directories.get(cache_key)
        if cached is not None:
            return cached

        with self._lock:
            cached = self._directories.get(cache_key)
            if cached is not None:
                return cached
            manifest_path = self._lookup_asset_resolver.materialize(
                manifest_logical_type,
                manifest_sha256,
            )
            manifest = self._load_manifest(manifest_path, expected_method_name)
            directory = self._cache_root / manifest_logical_type / manifest_sha256
            self._materialize_members(directory, manifest, member_logical_type)
            self._directories[cache_key] = directory
            return directory

    @staticmethod
    def _load_manifest(path: Path, expected_method_name: str) -> ModelManifestMetadata:
        try:
            manifest = ModelManifestMetadata.model_validate_json(path.read_bytes())
        except (OSError, ValidationError) as error:
            msg = "model manifest cannot be read or validated"
            raise MethodDependencyError(msg) from error
        if manifest.method_name != expected_method_name:
            msg = "model manifest method metadata does not match the adapter"
            raise MethodDependencyError(msg)
        return manifest

    def _materialize_members(
        self,
        directory: Path,
        manifest: ModelManifestMetadata,
        member_logical_type: str,
    ) -> None:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        for member in manifest.members:
            source_path = self._lookup_asset_resolver.materialize(
                member_logical_type,
                member.sha256,
            )
            destination = directory / member.relative_path
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                os.link(source_path, destination)
            except FileExistsError:
                continue
            except OSError:
                shutil.copyfile(source_path, destination)
