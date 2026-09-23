from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from gendertagger.models.artifact import (
    LookupArtifactMetadata,
    LookupSourceArtifactReference,
    ModelManifestMember,
    ModelManifestMetadata,
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


def _member(relative_path: str = "config.json") -> ModelManifestMember:
    return ModelManifestMember(
        relative_path=relative_path,
        artifact_id=uuid4(),
        sha256="a" * 64,
        byte_size=10,
    )


def test_model_manifest_preserves_ordered_member_content_identities() -> None:
    first = _member("config.json")
    second = _member("model.safetensors")
    manifest = ModelManifestMetadata(
        method_name="hf_distilbert",
        model_schema_version="hf_distilbert_model_v1",
        compiler_version="hf_model_manifest_compiler_v1",
        source_identifier="padmajabfrl/Gender-Classification",
        source_revision="a" * 40,
        members=(first, second),
    )

    assert [member.relative_path for member in manifest.members] == [
        "config.json",
        "model.safetensors",
    ]
    assert manifest.model_dump(mode="json")["members"][0]["artifact_id"] == str(first.artifact_id)


def test_model_manifest_requires_at_least_one_member() -> None:
    with pytest.raises(ValidationError, match="members"):
        ModelManifestMetadata(
            method_name="hf_distilbert",
            model_schema_version="hf_distilbert_model_v1",
            compiler_version="hf_model_manifest_compiler_v1",
            source_identifier="padmajabfrl/Gender-Classification",
            source_revision="a" * 40,
            members=(),
        )


def test_model_manifest_rejects_duplicate_relative_paths() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ModelManifestMetadata(
            method_name="hf_distilbert",
            model_schema_version="hf_distilbert_model_v1",
            compiler_version="hf_model_manifest_compiler_v1",
            source_identifier="padmajabfrl/Gender-Classification",
            source_revision="a" * 40,
            members=(_member("config.json"), _member("CONFIG.JSON")),
        )


@pytest.mark.parametrize(
    "relative_path",
    ["/etc/passwd", "../escape", "a/../../b", "a\\b", ""],
)
def test_model_manifest_member_rejects_unsafe_relative_paths(relative_path: str) -> None:
    with pytest.raises(ValidationError):
        _member(relative_path)
