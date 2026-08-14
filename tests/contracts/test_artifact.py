from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from gendertagger.models.artifact import (
    LookupArtifactMetadata,
    LookupSourceArtifactReference,
)

pytestmark = pytest.mark.contract


def test_lookup_metadata_preserves_ordered_source_content_identities() -> None:
    first_id = uuid4()
    second_id = uuid4()
    metadata = LookupArtifactMetadata(
        method_name="gnd",
        lookup_schema_version="gnd_lookup_v1",
        compiler_version="gnd_marcxml_compiler_v1",
        source_artifacts=(
            LookupSourceArtifactReference(artifact_id=first_id, sha256="a" * 64),
            LookupSourceArtifactReference(artifact_id=second_id, sha256="b" * 64),
        ),
        source_version="2026-06-24",
        sqlite_version="3.50.0",
        record_count=10,
    )

    assert metadata.model_dump(mode="json")["source_artifacts"] == [
        {"artifact_id": str(first_id), "sha256": "a" * 64},
        {"artifact_id": str(second_id), "sha256": "b" * 64},
    ]


def test_lookup_metadata_requires_at_least_one_valid_source_identity() -> None:
    with pytest.raises(ValidationError, match="source_artifacts"):
        LookupArtifactMetadata.model_validate(
            {
                "method_name": "gnd",
                "lookup_schema_version": "gnd_lookup_v1",
                "compiler_version": "gnd_marcxml_compiler_v1",
                "source_artifacts": [],
                "sqlite_version": "3.50.0",
                "record_count": 10,
            }
        )
    with pytest.raises(ValidationError, match="sha256"):
        LookupSourceArtifactReference(artifact_id=uuid4(), sha256="not-a-digest")
