"""Version registry for reproducible snapshot-import implementations."""

from gendertagger.ingestion.tabular import version_for_profile as tabular_version_for_profile
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.project import (
    SnapshotImportRequest,
    SourcePackaging,
    TeiImportProfile,
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
    profile = command.profile
    if isinstance(profile, TeiImportProfile):
        parser_version = TeiPersonParser.version_for_profile(profile)
        packaging_version = _TEI_PACKAGING_VERSIONS[command.packaging]
        return f"{parser_version}+{TEI_COLLECTION_IMPORTER_VERSION}+{packaging_version}"
    return tabular_version_for_profile(profile)
