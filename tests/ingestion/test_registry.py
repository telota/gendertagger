from __future__ import annotations

import pytest

from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.ingestion.tabular import TABULAR_PERSON_PARSER_VERSION
from gendertagger.models.project import (
    SnapshotImportRequest,
    SourceFormat,
    SourcePackaging,
    TabularImportProfile,
    TeiImportProfile,
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
        profile=TeiImportProfile.tei_p5_person_register_v3,
    )

    assert version_for_snapshot_import(command) == (
        f"tei_parser_v3+tei_collection_v1+{source_version}"
    )


def test_tabular_import_version_comes_from_the_format_profile() -> None:
    command = SnapshotImportRequest(
        source_format=SourceFormat.json,
        profile=TabularImportProfile.tei_equivalent_person_register_v1,
    )

    assert version_for_snapshot_import(command) == TABULAR_PERSON_PARSER_VERSION


def test_committed_v2_import_version_remains_resolvable() -> None:
    command = SnapshotImportRequest(profile=TeiImportProfile.tei_p5_person_register_v2)

    assert version_for_snapshot_import(command) == (
        "tei_parser_v2+tei_collection_v1+tei_single_source_v1"
    )
