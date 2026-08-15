"""Retry-safe execution of one persisted dataset-snapshot import."""

import hashlib
import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import cast
from uuid import UUID

from pydantic import ValidationError

from gendertagger.ingestion.collection import TeiCollectionImporter
from gendertagger.ingestion.package import (
    LooseDocument,
    PackageLimits,
    SourceMember,
    iter_loose_xml_members,
    iter_tar_gz_xml_members,
    iter_zip_xml_members,
)
from gendertagger.ingestion.registry import version_for_snapshot_import
from gendertagger.ingestion.tabular import (
    TabularImportError,
    TabularImportPolicy,
    TabularSourceReadError,
    TeiEquivalentPersonRegisterParser,
)
from gendertagger.ingestion.tei import TeiImportError, TeiPersonParser, TeiSourceReadError
from gendertagger.models.artifact import Artifact
from gendertagger.models.person import ImportedPerson
from gendertagger.models.project import (
    DatasetSnapshot,
    SnapshotImportConfig,
    SnapshotImportLimits,
    SnapshotImportTaskMessage,
    SnapshotSourceMember,
    SourceFormat,
    SourceManifestMember,
    SourceManifestV1,
    SourcePackaging,
    TabularImportProfile,
    TeiImportProfile,
)
from gendertagger.services.artifact_storage import ArtifactStorage
from gendertagger.services.persistence_errors import (
    InvalidResourceStateError,
    ResourceNotFoundError,
)
from gendertagger.services.unit_of_work import UnitOfWork, UnitOfWorkFactory

Clock = Callable[[], datetime]

DEFAULT_MAX_SNAPSHOT_IMPORT_ATTEMPTS = 3
_MAX_DIAGNOSTIC_LENGTH = 500
_INVALID_PROVENANCE_DIAGNOSTIC = "Snapshot import provenance is invalid."
_INVALID_STATE_DIAGNOSTIC = "Snapshot import state or provenance is invalid."
_INVALID_DATA_DIAGNOSTIC = "Snapshot import data or configuration is invalid."
_INTERNAL_FAILURE_DIAGNOSTIC = "Snapshot import failed due to an internal error."
_ARTIFACT_READ_BUFFER_BYTES = 64 * 1024

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ResolvedSource:
    """One persisted source member resolved to its immutable Artifact."""

    logical_name: str
    artifact: Artifact


class PermanentSnapshotImportError(RuntimeError):
    """Raised when persisted import provenance cannot produce a snapshot."""


class TransientSnapshotImportError(RuntimeError):
    """Raised when an import attempt should be retried after rollback."""


class _SnapshotSourceReadError(RuntimeError):
    """Raised when infrastructure prevents reading persisted source bytes."""


def _public_failure_diagnostic(error: BaseException) -> str:
    """Return a bounded diagnostic from a closed set of public-safe categories."""
    if isinstance(error, (TeiSourceReadError, TabularSourceReadError, _SnapshotSourceReadError)):
        return _INTERNAL_FAILURE_DIAGNOSTIC
    if isinstance(error, TeiImportError):
        # TeiImportError is the parser's sanitized public validation boundary.
        detail = " ".join(str(error).split()) or "TEI source is invalid"
        diagnostic = f"TEI import failed: {detail}"
        if len(diagnostic) > _MAX_DIAGNOSTIC_LENGTH:
            return diagnostic[: _MAX_DIAGNOSTIC_LENGTH - 1] + "…"
        return diagnostic
    if isinstance(error, TabularImportError):
        detail = " ".join(str(error).split()) or "tabular source is invalid"
        diagnostic = f"Tabular import failed: {detail}"
        if len(diagnostic) > _MAX_DIAGNOSTIC_LENGTH:
            return diagnostic[: _MAX_DIAGNOSTIC_LENGTH - 1] + "…"
        return diagnostic
    if isinstance(error, PermanentSnapshotImportError):
        return _INVALID_PROVENANCE_DIAGNOSTIC
    if isinstance(error, InvalidResourceStateError):
        return _INVALID_STATE_DIAGNOSTIC
    if isinstance(error, ValidationError):
        return _INVALID_DATA_DIAGNOSTIC
    return _INTERNAL_FAILURE_DIAGNOSTIC


class SnapshotImportExecutor:
    """Parse and atomically persist one immutable dataset snapshot.

    The pending claim, streamed person batches, and ready transition share one
    transaction. A worker crash or retryable failure rolls all of them back, so
    redelivery observes a pending snapshot and never committed partial people.
    """

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        artifact_storage: ArtifactStorage,
        parser: TeiPersonParser,
        clock: Clock,
        import_batch_record_count: int,
    ) -> None:
        if import_batch_record_count <= 0:
            msg = "import_batch_record_count must be positive"
            raise ValueError(msg)
        self._unit_of_work_factory = unit_of_work_factory
        self._artifact_storage = artifact_storage
        self._parser = parser
        self._clock = clock
        self._import_batch_record_count = import_batch_record_count

    def execute(
        self,
        message: SnapshotImportTaskMessage,
        *,
        attempt_count: int,
        max_attempts: int = DEFAULT_MAX_SNAPSHOT_IMPORT_ATTEMPTS,
    ) -> DatasetSnapshot:
        """Idempotently import a snapshot with bounded infrastructure retries."""
        if attempt_count <= 0:
            msg = "attempt_count must be positive"
            raise ValueError(msg)
        if max_attempts <= 0:
            msg = "max_attempts must be positive"
            raise ValueError(msg)

        try:
            return self._execute_once(message)
        except (TeiSourceReadError, TabularSourceReadError, _SnapshotSourceReadError) as error:
            if attempt_count < max_attempts:
                msg = (
                    f"dataset snapshot {message.dataset_snapshot_id} source read failed "
                    f"on attempt {attempt_count}"
                )
                raise TransientSnapshotImportError(msg) from error
            logger.exception(
                "dataset snapshot %s source read exhausted its retry budget",
                message.dataset_snapshot_id,
            )
            return self._persist_terminal_failure(
                message,
                error,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
            )
        except (
            PermanentSnapshotImportError,
            TeiImportError,
            TabularImportError,
            InvalidResourceStateError,
            ValidationError,
        ) as error:
            return self._persist_terminal_failure(
                message,
                error,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
            )
        except Exception as error:
            if attempt_count < max_attempts:
                msg = (
                    f"dataset snapshot {message.dataset_snapshot_id} import failed "
                    f"on attempt {attempt_count}"
                )
                raise TransientSnapshotImportError(msg) from error
            logger.exception(
                "dataset snapshot %s import exhausted its retry budget",
                message.dataset_snapshot_id,
            )
            return self._persist_terminal_failure(
                message,
                error,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
            )

    def _execute_once(self, message: SnapshotImportTaskMessage) -> DatasetSnapshot:
        with self._unit_of_work_factory() as unit_of_work:
            snapshot = unit_of_work.projects.claim_snapshot_import(message.dataset_snapshot_id)
            if snapshot is None:
                return self._existing_snapshot(unit_of_work, message.dataset_snapshot_id)

            import_config = self._import_config(snapshot)
            expected_parser_version = self._importer_version(import_config)
            if snapshot.parser_version != expected_parser_version:
                msg = (
                    f"snapshot parser version {snapshot.parser_version!r} does not match "
                    f"profile {import_config.profile.value!r}"
                )
                raise PermanentSnapshotImportError(msg)

            sources = self._resolved_sources(unit_of_work, snapshot, import_config)
            batch: list[ImportedPerson] = []
            for record_count, imported_person in enumerate(
                self._iter_people(import_config, sources),
                start=1,
            ):
                if record_count > import_config.limits.max_record_count:
                    msg = "snapshot source exceeds the configured record-count limit"
                    raise TeiImportError(msg)
                batch.append(imported_person)
                if len(batch) == self._import_batch_record_count:
                    self._persist_batch(unit_of_work, snapshot.id, batch)
                    batch.clear()
            if batch:
                self._persist_batch(unit_of_work, snapshot.id, batch)

            completed = unit_of_work.projects.complete_snapshot_import(
                snapshot.id,
                ready_at=self._clock(),
            )
            unit_of_work.commit()
            return completed

    @staticmethod
    def _persist_batch(
        unit_of_work: UnitOfWork,
        snapshot_id: UUID,
        batch: Sequence[ImportedPerson],
    ) -> None:
        unit_of_work.projects.add_imported_person_records(snapshot_id, batch)

    def _iter_people(
        self,
        config: SnapshotImportConfig,
        sources: tuple[_ResolvedSource, ...],
    ) -> Iterator[ImportedPerson]:
        """Return a lazy imported-person iterable for one resolved source contract."""
        if config.source_format is SourceFormat.tei:
            if not isinstance(config.profile, TeiImportProfile):
                msg = "TEI source has a non-TEI import profile"
                raise PermanentSnapshotImportError(msg)
            return self._iter_tei_people(config, sources)

        if not isinstance(config.profile, TabularImportProfile):
            msg = "tabular source has a non-tabular import profile"
            raise PermanentSnapshotImportError(msg)
        if config.packaging is not SourcePackaging.single or len(sources) != 1:
            msg = "tabular import provenance requires one single-file source"
            raise PermanentSnapshotImportError(msg)
        policy = self._tabular_policy(config.limits)
        parser = TeiEquivalentPersonRegisterParser(policy)
        resolved = sources[0]

        def iter_tabular() -> Iterator[ImportedPerson]:
            with self._artifact_storage.open(resolved.artifact.storage_uri) as source:
                if config.source_format is SourceFormat.csv:
                    yield from parser.iter_csv(
                        source,
                        source_member_name=resolved.logical_name,
                    )
                    return
                if config.source_format is SourceFormat.xlsx:
                    yield from parser.iter_xlsx(
                        source,
                        source_member_name=resolved.logical_name,
                    )
                    return
                if config.source_format is SourceFormat.json:
                    yield from parser.iter_json(
                        source,
                        source_member_name=resolved.logical_name,
                    )
                    return
                msg = f"unsupported tabular source format {config.source_format.value!r}"
                raise PermanentSnapshotImportError(msg)

        return iter_tabular()

    def _iter_tei_people(
        self,
        config: SnapshotImportConfig,
        sources: tuple[_ResolvedSource, ...],
    ) -> Iterator[ImportedPerson]:
        profile = config.profile
        if not isinstance(profile, TeiImportProfile):  # Narrow for static type checkers.
            msg = "TEI source has a non-TEI profile"
            raise PermanentSnapshotImportError(msg)
        limits = PackageLimits(
            max_member_count=config.limits.max_member_count,
            max_member_expanded_bytes=config.limits.max_member_expanded_bytes,
            max_total_expanded_bytes=config.limits.max_total_expanded_bytes,
            max_compression_ratio=config.limits.max_compression_ratio,
        )
        importer = TeiCollectionImporter(self._parser)

        def iter_tei() -> Iterator[ImportedPerson]:
            with ExitStack() as stack:
                members: Iterator[SourceMember] = iter(())
                if config.packaging in {SourcePackaging.single, SourcePackaging.loose}:
                    documents = [
                        LooseDocument(
                            logical_name=resolved.logical_name,
                            source_opener=partial(
                                self._artifact_storage.open,
                                resolved.artifact.storage_uri,
                            ),
                        )
                        for resolved in sources
                    ]
                    members = iter_loose_xml_members(
                        documents,
                        limits=limits,
                        require_xml_suffix=config.packaging is SourcePackaging.loose,
                    )
                elif config.packaging is SourcePackaging.zip:
                    self._require_one_container(sources, packaging=config.packaging)
                    package_source = stack.enter_context(
                        self._artifact_storage.open(sources[0].artifact.storage_uri)
                    )
                    members = iter_zip_xml_members(package_source, limits=limits)
                elif config.packaging is SourcePackaging.tar_gz:
                    self._require_one_container(sources, packaging=config.packaging)
                    package_source = stack.enter_context(
                        self._artifact_storage.open(sources[0].artifact.storage_uri)
                    )
                    members = iter_tar_gz_xml_members(package_source, limits=limits)
                yield from importer.iter_people(members, profile=profile)

        return iter_tei()

    @staticmethod
    def _import_config(snapshot: DatasetSnapshot) -> SnapshotImportConfig:
        try:
            return SnapshotImportConfig.model_validate(snapshot.import_config)
        except ValidationError as error:
            msg = "snapshot import configuration is invalid or missing persisted limits"
            raise PermanentSnapshotImportError(msg) from error

    @staticmethod
    def _importer_version(config: SnapshotImportConfig) -> str:
        return version_for_snapshot_import(config)

    def _resolved_sources(
        self,
        unit_of_work: UnitOfWork,
        snapshot: DatasetSnapshot,
        config: SnapshotImportConfig,
    ) -> tuple[_ResolvedSource, ...]:
        primary = self._primary_artifact(unit_of_work, snapshot, config)
        members = tuple(unit_of_work.projects.list_snapshot_source_members(snapshot.id))
        if not members:
            msg = "snapshot import provenance has no source members"
            raise PermanentSnapshotImportError(msg)

        if len(members) > config.limits.max_member_count:
            msg = "snapshot source-member count exceeds its persisted limit"
            raise PermanentSnapshotImportError(msg)
        self._require_member_shape(members, packaging=config.packaging)
        resolved = tuple(
            _ResolvedSource(
                logical_name=member.logical_name,
                artifact=self._member_artifact(unit_of_work, snapshot, member),
            )
            for member in members
        )
        if config.packaging is not SourcePackaging.loose:
            if resolved[0].artifact.id != primary.id:
                msg = "snapshot primary source disagrees with its source-member artifact"
                raise PermanentSnapshotImportError(msg)
            self._verify_artifact(primary)
        else:
            raw_manifest = self._read_verified_artifact(primary)
            self._validate_manifest(raw_manifest, config=config, members=members)
            for resolved_source in resolved:
                self._verify_artifact(resolved_source.artifact)
        return resolved

    @staticmethod
    def _member_artifact(
        unit_of_work: UnitOfWork,
        snapshot: DatasetSnapshot,
        member: SnapshotSourceMember,
    ) -> Artifact:
        artifact = unit_of_work.artifacts.get_artifact(member.artifact_id)
        if artifact is None:
            msg = f"source-member artifact {member.artifact_id} does not exist"
            raise PermanentSnapshotImportError(msg)
        if artifact.project_id != snapshot.project_id:
            msg = "snapshot source-member artifact belongs to a different project"
            raise PermanentSnapshotImportError(msg)
        if (
            artifact.sha256 != member.sha256
            or artifact.byte_size != member.byte_size
            or artifact.media_type != member.media_type
        ):
            msg = "snapshot source-member artifact disagrees with persisted provenance"
            raise PermanentSnapshotImportError(msg)
        return artifact

    @staticmethod
    def _require_member_shape(
        members: tuple[SnapshotSourceMember, ...],
        *,
        packaging: SourcePackaging,
    ) -> None:
        if not members:
            msg = "snapshot source-member set must not be empty"
            raise PermanentSnapshotImportError(msg)
        if [member.ordinal for member in members] != list(range(len(members))):
            msg = "snapshot source-member ordinals are not contiguous"
            raise PermanentSnapshotImportError(msg)
        collision_keys = [member.logical_name.casefold() for member in members]
        if len(collision_keys) != len(set(collision_keys)):
            msg = "snapshot source-member logical names collide"
            raise PermanentSnapshotImportError(msg)
        if packaging is not SourcePackaging.loose and len(members) != 1:
            msg = f"packaging={packaging.value!r} requires one persisted source member"
            raise PermanentSnapshotImportError(msg)

    def _primary_artifact(
        self,
        unit_of_work: UnitOfWork,
        snapshot: DatasetSnapshot,
        config: SnapshotImportConfig,
    ) -> Artifact:
        artifact = unit_of_work.artifacts.get_artifact(snapshot.source_artifact_id)
        if artifact is None:
            msg = f"source artifact {snapshot.source_artifact_id} does not exist"
            raise PermanentSnapshotImportError(msg)
        if artifact.project_id != snapshot.project_id:
            msg = "snapshot source artifact belongs to a different project"
            raise PermanentSnapshotImportError(msg)
        if artifact.sha256 != snapshot.source_sha256:
            msg = "snapshot source artifact checksum disagrees with import provenance"
            raise PermanentSnapshotImportError(msg)
        expected_type = self._expected_primary_logical_type(config)
        if artifact.logical_type != expected_type:
            msg = "snapshot source artifact has an unsupported logical type"
            raise PermanentSnapshotImportError(msg)
        return artifact

    @staticmethod
    def _expected_primary_logical_type(config: SnapshotImportConfig) -> str:
        if config.packaging is SourcePackaging.loose:
            return "source_manifest"
        if config.packaging is SourcePackaging.zip:
            return "source_zip"
        if config.packaging is SourcePackaging.tar_gz:
            return "source_tar_gz"
        return f"source_{config.source_format.value}"

    def _validate_manifest(
        self,
        raw_manifest: bytes,
        *,
        config: SnapshotImportConfig,
        members: tuple[SnapshotSourceMember, ...],
    ) -> None:
        manifest = SourceManifestV1.model_validate_json(raw_manifest)
        expected = SourceManifestV1(
            source_format=config.source_format,
            packaging=config.packaging,
            members=tuple(
                SourceManifestMember(
                    logical_name=member.logical_name,
                    sha256=member.sha256,
                    byte_size=member.byte_size,
                    media_type=member.media_type,
                )
                for member in members
            ),
        )
        if manifest != expected:
            msg = "snapshot source manifest disagrees with source-member provenance"
            raise PermanentSnapshotImportError(msg)

    def _verify_artifact(self, artifact: Artifact) -> None:
        self._read_verified_artifact(artifact, collect=False)

    def _read_verified_artifact(
        self,
        artifact: Artifact,
        *,
        collect: bool = True,
    ) -> bytes:
        """Read exact immutable bytes and verify persisted size and SHA-256."""
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        byte_count = 0
        try:
            with self._artifact_storage.open(artifact.storage_uri) as source:
                while True:
                    remaining = artifact.byte_size - byte_count
                    raw_chunk = cast(
                        object,
                        source.read(min(_ARTIFACT_READ_BUFFER_BYTES, max(remaining + 1, 1))),
                    )
                    if raw_chunk is None or not isinstance(raw_chunk, bytes):
                        msg = "persisted snapshot source did not return binary data"
                        raise _SnapshotSourceReadError(msg)
                    if not raw_chunk:
                        break
                    byte_count += len(raw_chunk)
                    if byte_count > artifact.byte_size:
                        msg = "snapshot source artifact byte size disagrees with provenance"
                        raise PermanentSnapshotImportError(msg)
                    digest.update(raw_chunk)
                    if collect:
                        chunks.append(raw_chunk)
        except OSError as error:
            msg = "persisted snapshot source could not be read"
            raise _SnapshotSourceReadError(msg) from error

        if byte_count != artifact.byte_size:
            msg = "snapshot source artifact byte size disagrees with provenance"
            raise PermanentSnapshotImportError(msg)
        if digest.hexdigest() != artifact.sha256:
            msg = "snapshot source artifact checksum disagrees with provenance"
            raise PermanentSnapshotImportError(msg)
        return b"".join(chunks)

    @staticmethod
    def _tabular_policy(limits: SnapshotImportLimits) -> TabularImportPolicy:
        return TabularImportPolicy(
            max_source_bytes=min(
                limits.max_member_expanded_bytes,
                limits.max_total_expanded_bytes,
            ),
            max_records=limits.max_record_count,
            max_cell_bytes=limits.max_cell_bytes,
            max_json_depth=20,
            max_json_nodes=max(limits.max_record_count * 100, 1_000),
            max_xlsx_archive_members=limits.max_member_count,
            max_xlsx_member_expanded_bytes=limits.max_member_expanded_bytes,
            max_xlsx_total_expanded_bytes=limits.max_total_expanded_bytes,
            max_xlsx_compression_ratio=limits.max_compression_ratio,
        )

    @staticmethod
    def _require_one_container(
        sources: tuple[_ResolvedSource, ...],
        *,
        packaging: SourcePackaging,
    ) -> None:
        if len(sources) != 1:
            msg = f"packaging={packaging.value!r} requires exactly one source container"
            raise PermanentSnapshotImportError(msg)

    def _persist_terminal_failure(
        self,
        message: SnapshotImportTaskMessage,
        error: BaseException,
        *,
        attempt_count: int,
        max_attempts: int,
    ) -> DatasetSnapshot:
        try:
            return self._fail_after_rollback(message, error)
        except Exception as persistence_error:
            if attempt_count < max_attempts:
                msg = (
                    f"dataset snapshot {message.dataset_snapshot_id} terminal state "
                    f"could not be persisted on attempt {attempt_count}"
                )
                raise TransientSnapshotImportError(msg) from persistence_error
            logger.exception(
                "dataset snapshot %s terminal failure state could not be persisted",
                message.dataset_snapshot_id,
            )
            raise

    def _fail_after_rollback(
        self,
        message: SnapshotImportTaskMessage,
        error: BaseException,
    ) -> DatasetSnapshot:
        with self._unit_of_work_factory() as unit_of_work:
            snapshot = unit_of_work.projects.claim_snapshot_import(message.dataset_snapshot_id)
            if snapshot is None:
                return self._existing_snapshot(unit_of_work, message.dataset_snapshot_id)
            failed = unit_of_work.projects.fail_snapshot_import(
                snapshot.id,
                failure_diagnostic=_public_failure_diagnostic(error),
            )
            unit_of_work.commit()
            return failed

    @staticmethod
    def _existing_snapshot(
        unit_of_work: UnitOfWork,
        snapshot_id: UUID,
    ) -> DatasetSnapshot:
        snapshot = unit_of_work.projects.get_snapshot(snapshot_id)
        if snapshot is None:
            msg = f"dataset snapshot {snapshot_id} does not exist"
            raise ResourceNotFoundError(msg)
        return snapshot
