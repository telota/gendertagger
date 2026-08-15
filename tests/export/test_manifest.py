from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gendertagger.export.manifest import build_export_manifest
from gendertagger.models.export import ExportFormat, ExportManifestOutput, LabelSourcePolicy

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def test_manifest_captures_every_required_provenance_field() -> None:
    export_id = uuid4()
    dataset_snapshot_id = uuid4()
    run_id = uuid4()
    aggregation_execution_id = uuid4()
    output = ExportManifestOutput(
        logical_name="A.xml",
        sha256="a" * 64,
        byte_size=123,
        media_type="application/xml",
    )

    manifest = build_export_manifest(
        export_id=export_id,
        dataset_snapshot_id=dataset_snapshot_id,
        source_snapshot_sha256="b" * 64,
        run_id=run_id,
        aggregation_execution_id=aggregation_execution_id,
        export_format=ExportFormat.tei,
        label_source_policy=LabelSourcePolicy.machine_aggregation,
        tei_profile=None,
        outputs=[output],
        generated_at=NOW,
    )

    assert manifest.export_id == export_id
    assert manifest.dataset_snapshot_id == dataset_snapshot_id
    assert manifest.source_snapshot_sha256 == "b" * 64
    assert manifest.run_id == run_id
    assert manifest.aggregation_execution_id == aggregation_execution_id
    assert manifest.format is ExportFormat.tei
    assert manifest.label_source_policy is LabelSourcePolicy.machine_aggregation
    assert manifest.outputs == (output,)
    assert manifest.generated_at == NOW
