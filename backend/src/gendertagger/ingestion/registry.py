"""Version registry for reproducible snapshot-import implementations."""

from gendertagger.ingestion.tabular import TABULAR_PERSON_PARSER_VERSION
from gendertagger.ingestion.tei import TEI_PARSER_VERSION
from gendertagger.models.project import (
    SnapshotImportRequest,
    SourceFormat,
    SourcePackaging,
)

TEI_COLLECTION_IMPORTER_VERSION = "tei_collection_v1"

_TEI_PACKAGING_VERSIONS = {
    SourcePackaging.single: "tei_single_source_v1",
    SourcePackaging.loose: "tei_loose_source_v1",
    SourcePackaging.zip: "tei_zip_source_v1",
    SourcePackaging.tar_gz: "tei_tar_gz_source_v1",
}


def version_for_snapshot_import(
    command: SnapshotImportRequest,
) -> str:
    """Return the exact semantic-parser and source-reader implementation version."""
    if command.source_format is SourceFormat.tei:
        packaging_version = _TEI_PACKAGING_VERSIONS[command.packaging]
        return f"{TEI_PARSER_VERSION}+{TEI_COLLECTION_IMPORTER_VERSION}+{packaging_version}"
    return TABULAR_PERSON_PARSER_VERSION
