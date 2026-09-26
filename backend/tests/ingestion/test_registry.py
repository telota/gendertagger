from __future__ import annotations

import pytest

from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.ingestion.tabular import TABULAR_PERSON_PARSER_VERSION
from gendertagger.models.project import (
    SnapshotImportRequest,
    SourceFormat,
    SourcePackaging,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("packaging", "source_version"),
    [
        (SourcePackaging.single, "tei_single_source_v1"),
        (SourcePackaging.loose, "tei_loose_source_v1"),
        (SourcePackaging.zip, "tei_zip_source_v1"),
        (SourcePackaging.tar_gz, "tei_tar_gz_source_v1"),
    ],
)
def test_tei_import_version_captures_profile_collection_and_packaging(
    packaging: SourcePackaging,
    source_version: str,
) -> None:
    command = SnapshotImportRequest(
        packaging=packaging,
    )

    assert version_for_snapshot_import(command) == (
        f"tei_parser_v4+tei_collection_v1+{source_version}"
    )


def test_tabular_import_version_comes_from_the_format_profile() -> None:
    command = SnapshotImportRequest(
        source_format=SourceFormat.json,
    )

    assert version_for_snapshot_import(command) == TABULAR_PERSON_PARSER_VERSION
