from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from gendertagger.cli.main import _build_parser, _download_https, main
from gendertagger.db.artifact_repository import SqlAlchemyArtifactRepository
from gendertagger.models.artifact import LookupArtifactMetadata
from gendertagger.storage.local import LocalArtifactStorage


def test_asset_download_rejects_non_https_urls(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute HTTPS"):
        _download_https(
            "http://example.test/NamesOut.txt",
            tmp_path / "download",
            expected_sha256="a" * 64,
            max_byte_size=1024,
        )


def test_build_gnd_cli_accepts_multiple_dnb_entity_dumps() -> None:
    args = _build_parser().parse_args(
        ["assets", "build-gnd", "person.xml.gz", "corporate-body.xml.gz"]
    )

    assert args.sources == [Path("person.xml.gz"), Path("corporate-body.xml.gz")]


def test_fetch_gnd_cli_pairs_each_url_with_a_checksum() -> None:
    args = _build_parser().parse_args(
        [
            "assets",
            "fetch-gnd",
            "https://data.example/person.xml.gz",
            "https://data.example/corporate.xml.gz",
            "--expected-sha256",
            "a" * 64,
            "--expected-sha256",
            "b" * 64,
        ]
    )

    assert args.urls == [
        "https://data.example/person.xml.gz",
        "https://data.example/corporate.xml.gz",
    ]
    assert args.expected_sha256 == ["a" * 64, "b" * 64]


@pytest.mark.postgres
def test_prepare_wiki_cli_registers_source_and_compiled_lookup(
    repository_database_url: str,
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    database_url = make_url(repository_database_url).set(drivername="postgresql+psycopg")
    monkeypatch.setenv(
        "GENDERTAGGER_DATABASE_URL",
        database_url.render_as_string(hide_password=False),
    )
    monkeypatch.setenv("GENDERTAGGER_ARTIFACT_ROOT", str(artifact_root))
    source = tmp_path / "NamesOut.txt"
    source_bytes = b"Karl\tM\nMaria\tF\n"
    source.write_bytes(source_bytes)

    exit_code = main(
        [
            "assets",
            "prepare-wiki",
            str(source),
            "--source-version",
            "wiki-gendersort-test",
            "--source-url",
            "https://example.test/NamesOut.txt",
            "--license-identifier",
            "test-license",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    [source_payload] = payload["source_artifacts"]
    assert source_payload["sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert payload["lookup_logical_type"] == "wiki_gendersort_lookup"

    with Session(postgres_engine) as session:
        artifacts = SqlAlchemyArtifactRepository(session)
        source_artifact = artifacts.get_artifact(UUID(source_payload["artifact_id"]))
        lookup_artifact = artifacts.get_artifact(UUID(payload["lookup_artifact_id"]))

    assert source_artifact is not None
    assert source_artifact.metadata == {
        "license_identifier": "test-license",
        "source_url": "https://example.test/NamesOut.txt",
        "source_version": "wiki-gendersort-test",
    }
    assert lookup_artifact is not None
    metadata = LookupArtifactMetadata.model_validate(lookup_artifact.metadata)
    assert metadata.method_name == "wiki_gendersort"
    assert len(metadata.source_artifacts) == 1
    assert metadata.source_artifacts[0].artifact_id == source_artifact.id
    assert metadata.source_artifacts[0].sha256 == source_artifact.sha256
    assert metadata.source_version == "wiki-gendersort-test"
    assert metadata.record_count == 2

    lookup_path = LocalArtifactStorage(artifact_root).materialize(lookup_artifact.storage_uri)
    uri = f"{lookup_path.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        rows = connection.execute(
            "SELECT name, native_label FROM wiki_names ORDER BY name"
        ).fetchall()
    finally:
        connection.close()
    assert rows == [("Karl", "M"), ("Maria", "F")]
