"""Validated environment settings for the command-line interface."""

from __future__ import annotations

from gendertagger.config.settings import ArtifactStorageSettings


class AssetCliSettings(ArtifactStorageSettings):
    """Validated settings for explicit method-asset provisioning."""

    max_method_asset_bytes: int = 20 * 1024 * 1024 * 1024
