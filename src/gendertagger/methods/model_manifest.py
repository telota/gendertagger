"""Shared contract for content-addressed multi-file model artifacts.

Mirrors the role :mod:`~gendertagger.methods.sqlite_lookup` plays for compiled
SQLite lookups: the resolver protocol and its safe unconfigured default live
with the adapters that consume them, while the real implementation lives in
:mod:`~gendertagger.services.model_assets` and is wired in only by the
composition root. See ADR-0023 and ADR-0024.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from gendertagger.methods.base import MethodDependencyError


class ModelDirectoryResolver(Protocol):
    """Materialize one registered model manifest to a verified local directory."""

    def materialize_directory(
        self,
        *,
        manifest_logical_type: str,
        member_logical_type: str,
        manifest_sha256: str,
        expected_method_name: str,
    ) -> Path:
        """Return a stable local directory containing the manifest's exact members."""
        ...


class UnavailableModelDirectoryResolver:
    """Fail prediction when runtime composition omitted model-asset storage."""

    def materialize_directory(
        self,
        *,
        manifest_logical_type: str,
        member_logical_type: str,
        manifest_sha256: str,
        expected_method_name: str,
    ) -> Path:
        """Raise a permanent dependency error for an uncomposed resolver."""
        del manifest_logical_type, member_logical_type, manifest_sha256, expected_method_name
        msg = "model directory resolver is not configured"
        raise MethodDependencyError(msg)
