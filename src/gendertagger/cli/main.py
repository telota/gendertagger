"""Command-line provisioning for immutable method lookup assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Final, Protocol
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pydantic import JsonValue, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from gendertagger.db.session import create_database_engine, create_session_factory
from gendertagger.db.unit_of_work import SqlAlchemyUnitOfWork
from gendertagger.methods.gnd_snapshot import (
    GND_LOOKUP_COMPILER_VERSION,
    GND_LOOKUP_LOGICAL_TYPE,
    GND_LOOKUP_SCHEMA_VERSION,
    compile_gnd_marcxml_lookup,
)
from gendertagger.methods.hf_distilbert import (
    HF_DISTILBERT_MODEL_COMPILER_VERSION,
    HF_DISTILBERT_MODEL_FILE_LOGICAL_TYPE,
    HF_DISTILBERT_MODEL_MANIFEST_LOGICAL_TYPE,
    HF_DISTILBERT_MODEL_SCHEMA_VERSION,
)
from gendertagger.methods.hf_genderize import (
    HF_GENDERIZE_MODEL_COMPILER_VERSION,
    HF_GENDERIZE_MODEL_FILE_LOGICAL_TYPE,
    HF_GENDERIZE_MODEL_MANIFEST_LOGICAL_TYPE,
    HF_GENDERIZE_MODEL_SCHEMA_VERSION,
)
from gendertagger.methods.hivoto import (
    HIVOTO_LOOKUP_COMPILER_VERSION,
    HIVOTO_LOOKUP_LOGICAL_TYPE,
    HIVOTO_LOOKUP_SCHEMA_VERSION,
    compile_hivoto_lookup,
)
from gendertagger.methods.hivoto_xgboost import (
    HIVOTO_XGBOOST_MODEL_COMPILER_VERSION,
    HIVOTO_XGBOOST_MODEL_FILE_LOGICAL_TYPE,
    HIVOTO_XGBOOST_MODEL_MANIFEST_LOGICAL_TYPE,
    HIVOTO_XGBOOST_MODEL_SCHEMA_VERSION,
    IDF_MEMBER_RELATIVE_PATH,
    LOOKUP_MEMBER_RELATIVE_PATH,
    MODEL_MEMBER_RELATIVE_PATH,
    VECTORIZER_CONFIG_MEMBER_RELATIVE_PATH,
    VOCABULARY_MEMBER_RELATIVE_PATH,
)
from gendertagger.methods.wiki_gendersort import (
    WIKI_GENDERSORT_LOOKUP_COMPILER_VERSION,
    WIKI_GENDERSORT_LOOKUP_LOGICAL_TYPE,
    WIKI_GENDERSORT_LOOKUP_SCHEMA_VERSION,
    compile_wiki_gendersort_lookup,
)
from gendertagger.models.artifact import (
    MODEL_MANIFEST_MEDIA_TYPE,
    SQLITE_MEDIA_TYPE,
    Artifact,
    LookupArtifactMetadata,
    LookupSourceArtifactReference,
    ModelManifestMember,
    ModelManifestMetadata,
)
from gendertagger.services.lookup_assets import (
    LookupAssetRegistrationService,
    RegisteredLookupAssetResolver,
)
from gendertagger.services.unit_of_work import UnitOfWorkFactory
from gendertagger.storage.local import LocalArtifactStorage

_HIVOTO_SOURCE_TYPE: Final = "hivoto_source"
_WIKI_SOURCE_TYPE: Final = "wiki_gendersort_source"
_GND_SOURCE_TYPE: Final = "gnd_source_dump"
_HIVOTO_SOURCE_URL: Final = (
    "https://radar4memory.radar-service.eu/radar/en/dataset/pwbupf0jc2zj4k7x"
)
_DOWNLOAD_BUFFER_BYTES: Final = 1024 * 1024


class LookupCompiler(Protocol):
    """Compile one registered source to one SQLite lookup."""

    def __call__(
        self,
        source_path: Path,
        destination_path: Path,
        *,
        source_sha256: str,
        source_version: str | None = None,
    ) -> int:
        """Return the number of compiled lookup records."""
        raise NotImplementedError


class AssetCliSettings(BaseSettings):
    """Validated settings for explicit method-asset provisioning."""

    model_config = SettingsConfigDict(
        env_prefix="GENDERTAGGER_",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    artifact_root: Path = Path("data/artifacts")
    max_method_asset_bytes: int = 20 * 1024 * 1024 * 1024

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            database_url = make_url(value.get_secret_value())
        except ArgumentError as error:
            msg = "database_url must be a valid SQLAlchemy URL"
            raise ValueError(msg) from error
        if database_url.drivername != "postgresql+psycopg":
            msg = "database_url must use the postgresql+psycopg driver"
            raise ValueError(msg)
        return value


@dataclass(frozen=True, slots=True)
class _LookupPreparation:
    method_name: str
    source_logical_type: str
    source_media_type: str
    lookup_logical_type: str
    lookup_schema_version: str
    compiler_version: str
    compiler: LookupCompiler


_PREPARATIONS: Final = {
    "hivoto": _LookupPreparation(
        method_name="hivoto",
        source_logical_type=_HIVOTO_SOURCE_TYPE,
        source_media_type="text/csv",
        lookup_logical_type=HIVOTO_LOOKUP_LOGICAL_TYPE,
        lookup_schema_version=HIVOTO_LOOKUP_SCHEMA_VERSION,
        compiler_version=HIVOTO_LOOKUP_COMPILER_VERSION,
        compiler=compile_hivoto_lookup,
    ),
    "wiki_gendersort": _LookupPreparation(
        method_name="wiki_gendersort",
        source_logical_type=_WIKI_SOURCE_TYPE,
        source_media_type="text/tab-separated-values",
        lookup_logical_type=WIKI_GENDERSORT_LOOKUP_LOGICAL_TYPE,
        lookup_schema_version=WIKI_GENDERSORT_LOOKUP_SCHEMA_VERSION,
        compiler_version=WIKI_GENDERSORT_LOOKUP_COMPILER_VERSION,
        compiler=compile_wiki_gendersort_lookup,
    ),
    "gnd": _LookupPreparation(
        method_name="gnd",
        source_logical_type=_GND_SOURCE_TYPE,
        source_media_type="application/marcxml+xml",
        lookup_logical_type=GND_LOOKUP_LOGICAL_TYPE,
        lookup_schema_version=GND_LOOKUP_SCHEMA_VERSION,
        compiler_version=GND_LOOKUP_COMPILER_VERSION,
        compiler=compile_gnd_marcxml_lookup,
    ),
}


@dataclass(frozen=True, slots=True)
class _HfModelPreparation:
    method_name: str
    manifest_logical_type: str
    member_logical_type: str
    model_schema_version: str
    compiler_version: str


_HF_MODEL_PREPARATIONS: Final = {
    "hf_distilbert": _HfModelPreparation(
        method_name="hf_distilbert",
        manifest_logical_type=HF_DISTILBERT_MODEL_MANIFEST_LOGICAL_TYPE,
        member_logical_type=HF_DISTILBERT_MODEL_FILE_LOGICAL_TYPE,
        model_schema_version=HF_DISTILBERT_MODEL_SCHEMA_VERSION,
        compiler_version=HF_DISTILBERT_MODEL_COMPILER_VERSION,
    ),
    "hf_genderize": _HfModelPreparation(
        method_name="hf_genderize",
        manifest_logical_type=HF_GENDERIZE_MODEL_MANIFEST_LOGICAL_TYPE,
        member_logical_type=HF_GENDERIZE_MODEL_FILE_LOGICAL_TYPE,
        model_schema_version=HF_GENDERIZE_MODEL_SCHEMA_VERSION,
        compiler_version=HF_GENDERIZE_MODEL_COMPILER_VERSION,
    ),
}

_MODEL_FILE_MEDIA_TYPES_BY_SUFFIX: Final = {
    ".json": "application/json",
    ".txt": "text/plain",
}


def _model_file_media_type(path: Path) -> str:
    return _MODEL_FILE_MEDIA_TYPES_BY_SUFFIX.get(path.suffix.casefold(), "application/octet-stream")


def _prepare_hf_model(
    registration: LookupAssetRegistrationService,
    directory: Path,
    preparation: _HfModelPreparation,
    *,
    source_identifier: str,
    source_revision: str,
    license_identifier: str | None,
) -> Artifact:
    """Register every file in a local model directory plus its content manifest."""
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    if not files:
        msg = f"hf model source directory contains no files: {directory}"
        raise ValueError(msg)
    members: list[ModelManifestMember] = []
    for file_path in files:
        artifact = registration.register_file(
            file_path,
            logical_type=preparation.member_logical_type,
            media_type=_model_file_media_type(file_path),
        )
        members.append(
            ModelManifestMember(
                relative_path=file_path.relative_to(directory).as_posix(),
                artifact_id=artifact.id,
                sha256=artifact.sha256,
                byte_size=artifact.byte_size,
            )
        )
    manifest = ModelManifestMetadata(
        method_name=preparation.method_name,
        model_schema_version=preparation.model_schema_version,
        compiler_version=preparation.compiler_version,
        source_identifier=source_identifier,
        source_revision=source_revision,
        members=tuple(members),
        license_identifier=license_identifier,
    )
    with tempfile.TemporaryDirectory(prefix="gendertagger-model-manifest-") as temporary_directory:
        manifest_path = Path(temporary_directory) / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return registration.register_file(
            manifest_path,
            logical_type=preparation.manifest_logical_type,
            media_type=MODEL_MANIFEST_MEDIA_TYPE,
            metadata=manifest.model_dump(mode="json"),
        )


def _prepare_hivoto_xgboost(
    registration: LookupAssetRegistrationService,
    lookup_asset_resolver: RegisteredLookupAssetResolver,
    model_directory: Path,
    *,
    hivoto_lookup_sha256: str,
    source_identifier: str,
    source_revision: str,
    license_identifier: str | None,
) -> Artifact:
    """Register the HIVOTO-XGBoost model bundle, reusing an already-registered lookup.

    The lookup member is materialized from the digest of a ``hivoto_lookup``
    artifact already registered via ``prepare-hivoto``/``fetch-wiki``-style
    provisioning, never recompiled from the licensed HIVOTO source. See
    ADR-0025.
    """
    lookup_path = lookup_asset_resolver.materialize(HIVOTO_LOOKUP_LOGICAL_TYPE, hivoto_lookup_sha256)
    file_specs = (
        (lookup_path, LOOKUP_MEMBER_RELATIVE_PATH, SQLITE_MEDIA_TYPE),
        (model_directory / VOCABULARY_MEMBER_RELATIVE_PATH, VOCABULARY_MEMBER_RELATIVE_PATH, "application/json"),
        (model_directory / IDF_MEMBER_RELATIVE_PATH, IDF_MEMBER_RELATIVE_PATH, "application/json"),
        (
            model_directory / VECTORIZER_CONFIG_MEMBER_RELATIVE_PATH,
            VECTORIZER_CONFIG_MEMBER_RELATIVE_PATH,
            "application/json",
        ),
        (model_directory / MODEL_MEMBER_RELATIVE_PATH, MODEL_MEMBER_RELATIVE_PATH, "application/json"),
    )
    members: list[ModelManifestMember] = []
    for file_path, relative_path, media_type in file_specs:
        artifact = registration.register_file(
            file_path,
            logical_type=HIVOTO_XGBOOST_MODEL_FILE_LOGICAL_TYPE,
            media_type=media_type,
        )
        members.append(
            ModelManifestMember(
                relative_path=relative_path,
                artifact_id=artifact.id,
                sha256=artifact.sha256,
                byte_size=artifact.byte_size,
            )
        )
    manifest = ModelManifestMetadata(
        method_name="hivoto_xgboost",
        model_schema_version=HIVOTO_XGBOOST_MODEL_SCHEMA_VERSION,
        compiler_version=HIVOTO_XGBOOST_MODEL_COMPILER_VERSION,
        source_identifier=source_identifier,
        source_revision=source_revision,
        members=tuple(members),
        license_identifier=license_identifier,
    )
    with tempfile.TemporaryDirectory(prefix="gendertagger-model-manifest-") as temporary_directory:
        manifest_path = Path(temporary_directory) / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return registration.register_file(
            manifest_path,
            logical_type=HIVOTO_XGBOOST_MODEL_MANIFEST_LOGICAL_TYPE,
            media_type=MODEL_MANIFEST_MEDIA_TYPE,
            metadata=manifest.model_dump(mode="json"),
        )


def _metadata_values(args: argparse.Namespace) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {}
    for key in ("source_version", "source_url", "license_identifier"):
        value = getattr(args, key, None)
        if value is not None:
            metadata[key] = str(value)
    return metadata


def _sha256_argument(value: str) -> str:
    normalized = value.casefold()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        msg = "expected a 64-character hexadecimal SHA-256 digest"
        raise argparse.ArgumentTypeError(msg)
    return normalized


def _source_media_type(preparation: _LookupPreparation, source_path: Path) -> str:
    if preparation.method_name != "gnd":
        return preparation.source_media_type
    with source_path.open("rb") as source:
        return (
            "application/gzip" if source.read(2) == b"\x1f\x8b" else preparation.source_media_type
        )


def _source_metadata(
    *,
    source_version: str | None,
    source_url: str | None,
    license_identifier: str | None,
) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {}
    if source_version is not None:
        metadata["source_version"] = source_version
    if source_url is not None:
        metadata["source_url"] = source_url
    if license_identifier is not None:
        metadata["license_identifier"] = license_identifier
    return metadata


def _register_source(
    registration: LookupAssetRegistrationService,
    source_path: Path,
    preparation: _LookupPreparation,
    *,
    source_version: str | None,
    source_url: str | None,
    license_identifier: str | None,
) -> tuple[Artifact, Path]:
    source_artifact = registration.register_file(
        source_path,
        logical_type=preparation.source_logical_type,
        media_type=_source_media_type(preparation, source_path),
        metadata=_source_metadata(
            source_version=source_version,
            source_url=source_url,
            license_identifier=license_identifier,
        ),
    )
    return source_artifact, registration.materialize(source_artifact)


def _source_identity(sources: Sequence[Artifact]) -> str:
    digests = sorted(source.sha256 for source in sources)
    if len(digests) == 1:
        return digests[0]
    manifest = json.dumps(digests, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(manifest).hexdigest()


def _register_compiled_lookup(
    registration: LookupAssetRegistrationService,
    lookup_path: Path,
    preparation: _LookupPreparation,
    sources: Sequence[Artifact],
    *,
    record_count: int,
    source_version: str | None,
    source_url: str | None,
    license_identifier: str | None,
) -> Artifact:
    lookup_metadata = LookupArtifactMetadata(
        method_name=preparation.method_name,
        lookup_schema_version=preparation.lookup_schema_version,
        compiler_version=preparation.compiler_version,
        source_artifacts=tuple(
            LookupSourceArtifactReference(
                artifact_id=source.id,
                sha256=source.sha256,
            )
            for source in sources
        ),
        source_version=source_version,
        source_url=source_url,
        license_identifier=license_identifier,
        sqlite_version=sqlite3.sqlite_version,
        record_count=record_count,
    )
    return registration.register_file(
        lookup_path,
        logical_type=preparation.lookup_logical_type,
        media_type=SQLITE_MEDIA_TYPE,
        metadata=lookup_metadata.model_dump(mode="json"),
    )


def _prepare_lookup(
    registration: LookupAssetRegistrationService,
    source_path: Path,
    preparation: _LookupPreparation,
    *,
    source_version: str | None,
    source_url: str | None,
    license_identifier: str | None,
) -> tuple[tuple[Artifact, ...], Artifact]:
    source_artifact, immutable_source_path = _register_source(
        registration,
        source_path,
        preparation,
        source_version=source_version,
        source_url=source_url,
        license_identifier=license_identifier,
    )
    with tempfile.TemporaryDirectory(prefix="gendertagger-lookup-") as temporary_directory:
        lookup_path = Path(temporary_directory) / "lookup.sqlite3"
        record_count = preparation.compiler(
            immutable_source_path,
            lookup_path,
            source_sha256=source_artifact.sha256,
            source_version=source_version,
        )
        lookup_artifact = _register_compiled_lookup(
            registration,
            lookup_path,
            preparation,
            (source_artifact,),
            record_count=record_count,
            source_version=source_version,
            source_url=source_url,
            license_identifier=license_identifier,
        )
    return (source_artifact,), lookup_artifact


def _prepare_gnd_lookup(
    registration: LookupAssetRegistrationService,
    source_paths: Sequence[Path],
    preparation: _LookupPreparation,
    *,
    source_version: str | None,
    source_url: str | None,
    source_urls: Sequence[str | None] | None = None,
    license_identifier: str | None,
) -> tuple[tuple[Artifact, ...], Artifact]:
    if not source_paths:
        msg = "at least one GND source is required"
        raise ValueError(msg)
    resolved_source_urls = (
        tuple(source_url for _ in source_paths) if source_urls is None else tuple(source_urls)
    )
    if len(resolved_source_urls) != len(source_paths):
        msg = "every GND source requires a corresponding source URL entry"
        raise ValueError(msg)
    registered_by_digest: dict[str, tuple[Artifact, Path]] = {}
    for source_path, artifact_source_url in zip(
        source_paths,
        resolved_source_urls,
        strict=True,
    ):
        source_artifact, immutable_source_path = _register_source(
            registration,
            source_path,
            preparation,
            source_version=source_version,
            source_url=artifact_source_url,
            license_identifier=license_identifier,
        )
        registered_by_digest[source_artifact.sha256] = (
            source_artifact,
            immutable_source_path,
        )
    registered = tuple(registered_by_digest[digest] for digest in sorted(registered_by_digest))
    sources = tuple(source for source, _ in registered)
    immutable_source_paths = tuple(path for _, path in registered)
    with tempfile.TemporaryDirectory(prefix="gendertagger-lookup-") as temporary_directory:
        lookup_path = Path(temporary_directory) / "lookup.sqlite3"
        record_count = compile_gnd_marcxml_lookup(
            immutable_source_paths,
            lookup_path,
            source_sha256=_source_identity(sources),
            source_sha256s=tuple(source.sha256 for source in sources),
            source_version=source_version,
        )
        lookup_artifact = _register_compiled_lookup(
            registration,
            lookup_path,
            preparation,
            sources,
            record_count=record_count,
            source_version=source_version,
            source_url=source_url,
            license_identifier=license_identifier,
        )
    return sources, lookup_artifact


def _download_https(
    url: str,
    destination: Path,
    *,
    expected_sha256: str,
    max_byte_size: int,
) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        msg = "method asset downloads require an absolute HTTPS URL"
        raise ValueError(msg)
    request = Request(  # noqa: S310 - the URL was restricted to absolute HTTPS above.
        url,
        headers={"User-Agent": "gendertagger-asset-provisioner/1"},
    )
    digest = hashlib.sha256()
    byte_count = 0
    with urlopen(request, timeout=60) as response, destination.open("wb") as output:  # noqa: S310
        while chunk := response.read(_DOWNLOAD_BUFFER_BYTES):
            byte_count += len(chunk)
            if byte_count > max_byte_size:
                msg = f"download exceeds the {max_byte_size}-byte method-asset limit"
                raise ValueError(msg)
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != expected_sha256:
        destination.unlink(missing_ok=True)
        msg = "downloaded method asset does not match expected SHA-256"
        raise ValueError(msg)


def _artifact_payload(sources: Sequence[Artifact], lookup: Artifact) -> str:
    return json.dumps(
        {
            "source_artifacts": [
                {"artifact_id": str(source.id), "sha256": source.sha256} for source in sources
            ],
            "lookup_artifact_id": str(lookup.id),
            "lookup_sha256": lookup.sha256,
            "lookup_logical_type": lookup.logical_type,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _add_source_metadata_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-version")
    parser.add_argument("--source-url")
    parser.add_argument("--license-identifier")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gendertagger")
    commands = parser.add_subparsers(dest="command", required=True)
    assets = commands.add_parser("assets", help="Provision immutable method data")
    asset_commands = assets.add_subparsers(dest="asset_command", required=True)

    register = asset_commands.add_parser("register", help="Register exact source bytes")
    register.add_argument("source", type=Path)
    register.add_argument("--logical-type", required=True)
    register.add_argument("--media-type", required=True)
    _add_source_metadata_arguments(register)

    for command_name, method_name in (
        ("prepare-hivoto", "hivoto"),
        ("prepare-wiki", "wiki_gendersort"),
    ):
        command = asset_commands.add_parser(command_name)
        command.set_defaults(method_name=method_name)
        command.add_argument("source", type=Path)
        _add_source_metadata_arguments(command)
    build_gnd = asset_commands.add_parser("build-gnd")
    build_gnd.set_defaults(method_name="gnd")
    build_gnd.add_argument("sources", type=Path, nargs="+")
    _add_source_metadata_arguments(build_gnd)
    prepare_hf_model = asset_commands.add_parser(
        "prepare-hf-model",
        help="Register a locally materialized Hugging Face model directory",
    )
    prepare_hf_model.add_argument(
        "--method-name", required=True, choices=sorted(_HF_MODEL_PREPARATIONS)
    )
    prepare_hf_model.add_argument("directory", type=Path)
    prepare_hf_model.add_argument("--source-identifier", required=True)
    prepare_hf_model.add_argument(
        "--source-revision",
        required=True,
        help="Pinned model commit SHA; a mutable branch name such as 'main' is unsafe.",
    )
    prepare_hf_model.add_argument("--license-identifier")
    prepare_hivoto_xgboost = asset_commands.add_parser(
        "prepare-hivoto-xgboost",
        help="Register the HIVOTO-XGBoost model bundle, reusing a registered hivoto_lookup",
    )
    prepare_hivoto_xgboost.add_argument("model_directory", type=Path)
    prepare_hivoto_xgboost.add_argument(
        "--hivoto-lookup-sha256",
        required=True,
        type=_sha256_argument,
        help="Digest of an already-registered hivoto_lookup artifact.",
    )
    prepare_hivoto_xgboost.add_argument("--source-identifier", required=True)
    prepare_hivoto_xgboost.add_argument("--source-revision", required=True)
    prepare_hivoto_xgboost.add_argument("--license-identifier")
    fetch_wiki = asset_commands.add_parser("fetch-wiki")
    fetch_wiki.set_defaults(method_name="wiki_gendersort")
    fetch_wiki.add_argument("url")
    fetch_wiki.add_argument("--expected-sha256", required=True, type=_sha256_argument)
    fetch_wiki.add_argument("--source-version")
    fetch_wiki.add_argument("--license-identifier")
    fetch_gnd = asset_commands.add_parser("fetch-gnd")
    fetch_gnd.set_defaults(method_name="gnd")
    fetch_gnd.add_argument("urls", nargs="+")
    fetch_gnd.add_argument(
        "--expected-sha256",
        action="append",
        required=True,
        type=_sha256_argument,
    )
    fetch_gnd.add_argument("--source-version")
    fetch_gnd.add_argument("--license-identifier")
    return parser


def _registration_service(
    settings: AssetCliSettings,
) -> tuple[LookupAssetRegistrationService, RegisteredLookupAssetResolver, Callable[[], None]]:
    engine = create_database_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    unit_of_work_factory: UnitOfWorkFactory = partial(SqlAlchemyUnitOfWork, session_factory)
    artifact_storage = LocalArtifactStorage(settings.artifact_root)
    service = LookupAssetRegistrationService(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=artifact_storage,
        max_byte_size=settings.max_method_asset_bytes,
    )
    resolver = RegisteredLookupAssetResolver(
        unit_of_work_factory=unit_of_work_factory,
        artifact_storage=artifact_storage,
    )
    return service, resolver, engine.dispose


def _run_assets(args: argparse.Namespace, settings: AssetCliSettings) -> str:
    registration, lookup_asset_resolver, dispose = _registration_service(settings)
    try:
        if args.asset_command == "register":
            artifact = registration.register_file(
                args.source,
                logical_type=args.logical_type,
                media_type=args.media_type,
                metadata=_metadata_values(args),
            )
            return json.dumps(
                {"artifact_id": str(artifact.id), "sha256": artifact.sha256},
                sort_keys=True,
            )

        if args.asset_command == "prepare-hf-model":
            hf_preparation = _HF_MODEL_PREPARATIONS[str(args.method_name)]
            manifest_artifact = _prepare_hf_model(
                registration,
                args.directory,
                hf_preparation,
                source_identifier=str(args.source_identifier),
                source_revision=str(args.source_revision),
                license_identifier=args.license_identifier,
            )
            return json.dumps(
                {
                    "manifest_artifact_id": str(manifest_artifact.id),
                    "lookup_sha256": manifest_artifact.sha256,
                    "manifest_logical_type": manifest_artifact.logical_type,
                },
                sort_keys=True,
            )

        if args.asset_command == "prepare-hivoto-xgboost":
            manifest_artifact = _prepare_hivoto_xgboost(
                registration,
                lookup_asset_resolver,
                args.model_directory,
                hivoto_lookup_sha256=str(args.hivoto_lookup_sha256),
                source_identifier=str(args.source_identifier),
                source_revision=str(args.source_revision),
                license_identifier=args.license_identifier,
            )
            return json.dumps(
                {
                    "manifest_artifact_id": str(manifest_artifact.id),
                    "lookup_sha256": manifest_artifact.sha256,
                    "manifest_logical_type": manifest_artifact.logical_type,
                },
                sort_keys=True,
            )

        preparation = _PREPARATIONS[str(args.method_name)]
        sources: tuple[Artifact, ...]
        lookup: Artifact
        source_url: str | None
        if args.asset_command == "fetch-gnd":
            source_urls = tuple(str(url) for url in args.urls)
            expected_digests = tuple(str(digest) for digest in args.expected_sha256)
            if len(source_urls) != len(expected_digests):
                msg = "fetch-gnd requires one --expected-sha256 per source URL"
                raise ValueError(msg)
            with tempfile.TemporaryDirectory(prefix="gendertagger-download-") as directory:
                source_paths: list[Path] = []
                for index, (url, expected_digest) in enumerate(
                    zip(source_urls, expected_digests, strict=True)
                ):
                    source_path = Path(directory) / f"source-{index}"
                    _download_https(
                        url,
                        source_path,
                        expected_sha256=expected_digest,
                        max_byte_size=settings.max_method_asset_bytes,
                    )
                    source_paths.append(source_path)
                sources, lookup = _prepare_gnd_lookup(
                    registration,
                    source_paths,
                    preparation,
                    source_version=args.source_version,
                    source_url=None,
                    source_urls=source_urls,
                    license_identifier=args.license_identifier,
                )
        elif args.asset_command == "fetch-wiki":
            source_url = str(args.url)
            with tempfile.TemporaryDirectory(prefix="gendertagger-download-") as directory:
                source_path = Path(directory) / "source"
                _download_https(
                    source_url,
                    source_path,
                    expected_sha256=str(args.expected_sha256),
                    max_byte_size=settings.max_method_asset_bytes,
                )
                sources, lookup = _prepare_lookup(
                    registration,
                    source_path,
                    preparation,
                    source_version=args.source_version,
                    source_url=source_url,
                    license_identifier=args.license_identifier,
                )
        elif args.asset_command == "build-gnd":
            sources, lookup = _prepare_gnd_lookup(
                registration,
                args.sources,
                preparation,
                source_version=args.source_version,
                source_url=args.source_url,
                license_identifier=args.license_identifier,
            )
        else:
            source_url = args.source_url
            if preparation.method_name == "hivoto" and source_url is None:
                source_url = _HIVOTO_SOURCE_URL
            sources, lookup = _prepare_lookup(
                registration,
                args.source,
                preparation,
                source_version=args.source_version,
                source_url=source_url,
                license_identifier=args.license_identifier,
            )
        return _artifact_payload(sources, lookup)
    finally:
        dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """Provision assets and emit their identifiers as one JSON line."""
    args = _build_parser().parse_args(argv)
    settings = AssetCliSettings()  # type: ignore[call-arg]  # Loaded from environment.
    payload = _run_assets(args, settings)
    sys.stdout.write(f"{payload}\n")
    return 0
