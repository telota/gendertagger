"""Pure export-manifest construction."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from gendertagger.models.export import (
    ExportFormat,
    ExportManifest,
    ExportManifestOutput,
    LabelSourcePolicy,
    TeiExportProfile,
)


def build_export_manifest(
    *,
    export_id: UUID,
    dataset_snapshot_id: UUID,
    source_snapshot_sha256: str,
    run_id: UUID,
    aggregation_execution_id: UUID,
    export_format: ExportFormat,
    label_source_policy: LabelSourcePolicy,
    tei_profile: TeiExportProfile | None,
    outputs: Sequence[ExportManifestOutput],
    generated_at: datetime,
) -> ExportManifest:
    """Assemble the immutable provenance record for one completed export."""
    return ExportManifest(
        export_id=export_id,
        dataset_snapshot_id=dataset_snapshot_id,
        source_snapshot_sha256=source_snapshot_sha256,
        run_id=run_id,
        aggregation_execution_id=aggregation_execution_id,
        format=export_format,
        label_source_policy=label_source_policy,
        tei_profile=tei_profile,
        outputs=tuple(outputs),
        generated_at=generated_at,
    )
