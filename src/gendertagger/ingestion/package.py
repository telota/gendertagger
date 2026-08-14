"""Secure logical-member readers for loose, ZIP, and TAR.GZ TEI collections."""

from __future__ import annotations

import gzip
import math
import re
import stat
import tarfile
import tempfile
import unicodedata
import zipfile
import zlib
from collections.abc import Callable, Generator, Iterable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO, cast
from urllib.parse import quote

from gendertagger.ingestion.tei import TeiImportError
from gendertagger.ingestion.zip_safety import (
    ZipPreflightError,
    ZipPreflightErrorCode,
    preflight_zip_directory,
)
from gendertagger.models.project import normalize_source_member_logical_name

_READ_BUFFER_BYTES = 64 * 1024
_SPOOL_MEMORY_BYTES = 8 * 1024 * 1024
_ARCHIVE_FIXED_OVERHEAD_BYTES = 1024 * 1024
_ARCHIVE_MEMBER_OVERHEAD_BYTES = 256 * 1024
_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_NESTED_ARCHIVE_SUFFIXES = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
)
_SUPPORTED_ZIP_COMPRESSION = {
    zipfile.ZIP_STORED,
    zipfile.ZIP_DEFLATED,
    zipfile.ZIP_BZIP2,
    zipfile.ZIP_LZMA,
}


class TeiPackageError(TeiImportError):
    """Raised with a sanitized diagnostic for an unsafe or invalid package."""


@dataclass(frozen=True, slots=True)
class PackageLimits:
    """Independent resource ceilings applied to one logical source package."""

    max_member_count: int = 1_000
    max_member_expanded_bytes: int = 25 * 1024 * 1024
    max_total_expanded_bytes: int = 100 * 1024 * 1024
    max_compression_ratio: float = 100.0

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_member_count,
            self.max_member_expanded_bytes,
            self.max_total_expanded_bytes,
        )
        if any(limit <= 0 for limit in integer_limits):
            msg = "package member and expanded-byte limits must be positive"
            raise ValueError(msg)
        if not math.isfinite(self.max_compression_ratio) or self.max_compression_ratio <= 1:
            msg = "max_compression_ratio must be finite and greater than one"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class LooseDocument:
    """One loose XML source and its untrusted logical name.

    Callers may supply an already-open, caller-owned stream or an opener. An
    opener lets the collection reader keep at most one loose artifact open at
    a time while it still validates and sorts all logical names up front.
    """

    logical_name: str
    source: BinaryIO | None = None
    source_locator: str | None = None
    source_opener: Callable[[], BinaryIO] | None = None

    def __post_init__(self) -> None:
        if (self.source is None) == (self.source_opener is None):
            msg = "a loose document requires exactly one source or source opener"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SourceMember:
    """One validated XML member whose stream is valid until iteration advances."""

    logical_name: str
    source: BinaryIO
    source_locator: str


@dataclass(frozen=True, slots=True)
class _MemberDescription:
    logical_name: str
    source_locator: str
    expanded_bytes: int | None
    compressed_bytes: int | None
    payload: object


@dataclass(slots=True)
class _ExpansionBudget:
    limits: PackageLimits
    compressed_package_bytes: int | None = None
    expanded_bytes: int = 0

    def account(self, byte_count: int) -> None:
        self.expanded_bytes += byte_count
        if self.expanded_bytes > self.limits.max_total_expanded_bytes:
            msg = "package exceeds the total expanded-byte limit"
            raise TeiPackageError(msg)
        if (
            self.compressed_package_bytes is not None
            and _compression_ratio(
                self.expanded_bytes,
                self.compressed_package_bytes,
            )
            > self.limits.max_compression_ratio
        ):
            msg = "package exceeds the compression-ratio limit"
            raise TeiPackageError(msg)


class _BoundedMemberReader:
    """Count expanded bytes while exposing one non-seekable member stream."""

    def __init__(
        self,
        source: BinaryIO,
        *,
        budget: _ExpansionBudget,
        expected_expanded_bytes: int | None,
        compressed_bytes: int | None,
    ) -> None:
        self._source = source
        self._budget = budget
        self._expected_expanded_bytes = expected_expanded_bytes
        self._compressed_bytes = compressed_bytes
        self._expanded_bytes = 0
        self._reached_end = False
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            msg = "I/O operation on closed package member"
            raise ValueError(msg)
        if size == 0:
            return b""
        if size < 0:
            chunks: list[bytes] = []
            while chunk := self._read_chunk(_READ_BUFFER_BYTES):
                chunks.append(chunk)
            return b"".join(chunks)
        return self._read_chunk(size)

    def readinto(self, buffer: bytearray) -> int:
        chunk = self.read(len(buffer))
        buffer[: len(chunk)] = chunk
        return len(chunk)

    def ensure_complete(self) -> None:
        """Consume one final probe so declared sizes cannot hide trailing data."""
        if not self._reached_end:
            while self._read_chunk(_READ_BUFFER_BYTES):
                pass

    def _read_chunk(self, requested_bytes: int) -> bytes:
        if self._reached_end:
            return b""
        remaining_member = self._budget.limits.max_member_expanded_bytes - self._expanded_bytes
        remaining_total = self._budget.limits.max_total_expanded_bytes - self._budget.expanded_bytes
        safe_remaining = min(remaining_member, remaining_total)
        read_size = min(requested_bytes, max(safe_remaining + 1, 1))
        try:
            chunk = self._source.read(read_size)
        except (
            EOFError,
            RuntimeError,
            gzip.BadGzipFile,
            tarfile.ReadError,
            zipfile.BadZipFile,
            zlib.error,
        ) as error:
            msg = "package member could not be decoded"
            raise TeiPackageError(msg) from error
        if not chunk:
            self._reached_end = True
            if (
                self._expected_expanded_bytes is not None
                and self._expanded_bytes != self._expected_expanded_bytes
            ):
                msg = "package member size disagrees with its header"
                raise TeiPackageError(msg)
            return b""

        self._expanded_bytes += len(chunk)
        self._budget.account(len(chunk))
        if self._expanded_bytes > self._budget.limits.max_member_expanded_bytes:
            msg = "package member exceeds the expanded-byte limit"
            raise TeiPackageError(msg)
        if (
            self._expected_expanded_bytes is not None
            and self._expanded_bytes > self._expected_expanded_bytes
        ):
            msg = "package member expands beyond its declared size"
            raise TeiPackageError(msg)
        if (
            self._compressed_bytes is not None
            and _compression_ratio(self._expanded_bytes, self._compressed_bytes)
            > self._budget.limits.max_compression_ratio
        ):
            msg = "package member exceeds the compression-ratio limit"
            raise TeiPackageError(msg)
        return chunk


def iter_loose_xml_members(
    documents: Iterable[LooseDocument],
    *,
    limits: PackageLimits,
    require_xml_suffix: bool = True,
) -> Iterator[SourceMember]:
    """Yield validated loose streams in deterministic logical-name order."""
    descriptions: list[_MemberDescription] = []
    full_names: set[str] = set()
    basenames: set[str] = set()
    for member_count, document in enumerate(documents, start=1):
        _check_member_count(member_count, limits)
        logical_name = normalize_logical_name(document.logical_name)
        _register_logical_name(logical_name, full_names=full_names, basenames=basenames)
        if require_xml_suffix:
            _require_xml_member(logical_name)
        descriptions.append(
            _MemberDescription(
                logical_name=logical_name,
                source_locator=document.source_locator or f"loose:{_quote_name(logical_name)}",
                expanded_bytes=None,
                compressed_bytes=None,
                payload=document,
            )
        )
    _require_nonempty_collection(descriptions)

    budget = _ExpansionBudget(limits)
    for description in _sort_descriptions(descriptions):
        document = cast(LooseDocument, description.payload)
        with _open_loose_document(document) as source:
            reader = _BoundedMemberReader(
                source,
                budget=budget,
                expected_expanded_bytes=None,
                compressed_bytes=None,
            )
            try:
                yield SourceMember(
                    logical_name=description.logical_name,
                    source=cast(BinaryIO, reader),
                    source_locator=description.source_locator,
                )
                reader.ensure_complete()
            finally:
                reader.close()


@contextmanager
def _open_loose_document(document: LooseDocument) -> Generator[BinaryIO, None, None]:
    if document.source is not None:
        yield document.source
        return

    opener = document.source_opener
    if opener is None:  # Defensive guard for instances bypassing dataclass construction.
        msg = "loose document source provenance is invalid"
        raise TeiPackageError(msg)
    source = opener()
    with source:
        yield source


@contextmanager
def _spooled_package_source(
    package_source: BinaryIO,
    *,
    limits: PackageLimits,
) -> Generator[tuple[BinaryIO, int], None, None]:
    """Copy one possibly non-seekable container into a bounded seekable spool."""
    max_source_bytes = (
        limits.max_total_expanded_bytes
        + _ARCHIVE_FIXED_OVERHEAD_BYTES
        + limits.max_member_count * _ARCHIVE_MEMBER_OVERHEAD_BYTES
    )
    memory_bytes = min(_SPOOL_MEMORY_BYTES, max_source_bytes)
    with tempfile.SpooledTemporaryFile(max_size=memory_bytes, mode="w+b") as spool:
        byte_count = 0
        while True:
            remaining = max_source_bytes - byte_count
            raw_chunk = cast(
                object,
                package_source.read(min(_READ_BUFFER_BYTES, remaining + 1)),
            )
            if raw_chunk is None or not isinstance(raw_chunk, bytes):
                msg = "package source did not return binary data"
                raise OSError(msg)
            if not raw_chunk:
                break
            byte_count += len(raw_chunk)
            if byte_count > max_source_bytes:
                msg = "package source exceeds the byte-size limit"
                raise TeiPackageError(msg)
            spool.write(raw_chunk)
        spool.seek(0)
        yield cast(BinaryIO, spool), byte_count


@contextmanager
def _spooled_tar_stream(
    compressed_source: BinaryIO,
    *,
    compressed_bytes: int,
    limits: PackageLimits,
) -> Generator[BinaryIO, None, None]:
    """Bound every gzip-expanded TAR byte, including headers and metadata."""
    memory_bytes = min(_SPOOL_MEMORY_BYTES, limits.max_total_expanded_bytes)
    with tempfile.SpooledTemporaryFile(max_size=memory_bytes, mode="w+b") as spool:
        expanded_bytes = 0
        try:
            with gzip.GzipFile(fileobj=compressed_source, mode="rb") as decompressor:
                while True:
                    remaining = limits.max_total_expanded_bytes - expanded_bytes
                    chunk = decompressor.read(min(_READ_BUFFER_BYTES, remaining + 1))
                    if not chunk:
                        break
                    expanded_bytes += len(chunk)
                    if expanded_bytes > limits.max_total_expanded_bytes:
                        msg = "TAR.GZ package exceeds the total expanded-byte limit"
                        raise TeiPackageError(msg)
                    if (
                        _compression_ratio(expanded_bytes, compressed_bytes)
                        > limits.max_compression_ratio
                    ):
                        msg = "TAR.GZ package exceeds the compression-ratio limit"
                        raise TeiPackageError(msg)
                    spool.write(chunk)
        except (EOFError, gzip.BadGzipFile, zlib.error) as error:
            msg = "invalid TAR.GZ compressed stream"
            raise TeiPackageError(msg) from error
        spool.seek(0)
        yield cast(BinaryIO, spool)


def iter_zip_xml_members(
    package_source: BinaryIO,
    *,
    limits: PackageLimits,
    package_locator: str = "package:zip",
) -> Iterator[SourceMember]:
    """Yield safe regular XML members from one ZIP without filesystem extraction."""
    with _spooled_package_source(package_source, limits=limits) as (seekable_source, _):
        try:
            preflight_zip_directory(
                seekable_source,
                max_entry_count=limits.max_member_count,
            )
        except ZipPreflightError as error:
            if error.code is ZipPreflightErrorCode.entry_count:
                msg = "source package exceeds the member-count limit"
            elif error.code is ZipPreflightErrorCode.metadata_size:
                msg = "ZIP package exceeds the metadata-size limit"
            else:
                msg = "invalid ZIP package"
            raise TeiPackageError(msg) from error
        try:
            archive = zipfile.ZipFile(seekable_source, mode="r")
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as error:
            msg = "invalid ZIP package"
            raise TeiPackageError(msg) from error

        with archive:
            descriptions = _zip_descriptions(
                archive,
                limits=limits,
                package_locator=package_locator,
            )
            budget = _ExpansionBudget(limits)
            for description in _sort_descriptions(descriptions):
                info = cast(zipfile.ZipInfo, description.payload)
                try:
                    source = archive.open(info, mode="r")
                except (NotImplementedError, RuntimeError, zipfile.BadZipFile) as error:
                    msg = "ZIP member could not be opened"
                    raise TeiPackageError(msg) from error
                with source:
                    reader = _BoundedMemberReader(
                        cast(BinaryIO, source),
                        budget=budget,
                        expected_expanded_bytes=description.expanded_bytes,
                        compressed_bytes=description.compressed_bytes,
                    )
                    try:
                        yield SourceMember(
                            logical_name=description.logical_name,
                            source=cast(BinaryIO, reader),
                            source_locator=description.source_locator,
                        )
                        reader.ensure_complete()
                    finally:
                        reader.close()


def iter_tar_gz_xml_members(
    package_source: BinaryIO,
    *,
    limits: PackageLimits,
    package_locator: str = "package:tar.gz",
) -> Iterator[SourceMember]:
    """Yield safe regular XML members from one TAR.GZ without extraction."""
    with _spooled_package_source(package_source, limits=limits) as (
        seekable_source,
        compressed_bytes,
    ):
        if compressed_bytes == 0:
            msg = "TAR.GZ package must not be empty"
            raise TeiPackageError(msg)
        with (
            _spooled_tar_stream(
                seekable_source,
                compressed_bytes=compressed_bytes,
                limits=limits,
            ) as tar_source,
            ExitStack() as stack,
        ):
            try:
                archive = stack.enter_context(tarfile.open(fileobj=tar_source, mode="r:"))
            except (tarfile.CompressionError, tarfile.ReadError) as error:
                msg = "invalid TAR.GZ package"
                raise TeiPackageError(msg) from error
            descriptions = _tar_descriptions(
                archive,
                limits=limits,
                package_locator=package_locator,
                compressed_package_bytes=compressed_bytes,
            )
            budget = _ExpansionBudget(limits, compressed_package_bytes=compressed_bytes)
            for description in _sort_descriptions(descriptions):
                info = cast(tarfile.TarInfo, description.payload)
                try:
                    source = archive.extractfile(info)
                except (KeyError, tarfile.ExtractError, tarfile.ReadError) as error:
                    msg = "TAR.GZ member could not be opened"
                    raise TeiPackageError(msg) from error
                if source is None:
                    msg = "TAR.GZ regular member has no readable payload"
                    raise TeiPackageError(msg)
                with source:
                    reader = _BoundedMemberReader(
                        cast(BinaryIO, source),
                        budget=budget,
                        expected_expanded_bytes=description.expanded_bytes,
                        compressed_bytes=None,
                    )
                    try:
                        yield SourceMember(
                            logical_name=description.logical_name,
                            source=cast(BinaryIO, reader),
                            source_locator=description.source_locator,
                        )
                        reader.ensure_complete()
                    finally:
                        reader.close()


def normalize_logical_name(raw_name: str) -> str:
    """Return one NFC POSIX logical name or reject ambiguous path syntax."""
    try:
        normalized = normalize_source_member_logical_name(raw_name)
    except ValueError as error:
        msg = "source member name is unsafe or invalid"
        raise TeiPackageError(msg) from error
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        msg = "source member name contains a control character"
        raise TeiPackageError(msg)
    if PurePosixPath(normalized).is_absolute() or _WINDOWS_DRIVE_PREFIX.match(normalized):
        msg = "source member name must be relative"
        raise TeiPackageError(msg)
    return normalized


def _zip_descriptions(
    archive: zipfile.ZipFile,
    *,
    limits: PackageLimits,
    package_locator: str,
) -> list[_MemberDescription]:
    infos = archive.infolist()
    _check_member_count(len(infos), limits)
    descriptions: list[_MemberDescription] = []
    full_names: set[str] = set()
    basenames: set[str] = set()
    total_expanded = 0
    for info in infos:
        mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if file_type == stat.S_IFLNK:
            msg = "ZIP package contains a symbolic link"
            raise TeiPackageError(msg)
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            msg = "ZIP package contains a non-regular member"
            raise TeiPackageError(msg)
        directory = info.is_dir() or file_type == stat.S_IFDIR
        if directory and not info.is_dir() and file_type == stat.S_IFDIR:
            msg = "ZIP directory member has an ambiguous name"
            raise TeiPackageError(msg)
        raw_name = (
            info.orig_filename[:-1]
            if directory and info.orig_filename.endswith("/")
            else info.orig_filename
        )
        logical_name = normalize_logical_name(raw_name)
        _register_full_name(logical_name, full_names)
        if info.flag_bits & 0x1:
            msg = "encrypted ZIP members are not supported"
            raise TeiPackageError(msg)
        if directory:
            if info.file_size != 0:
                msg = "ZIP directory member contains payload bytes"
                raise TeiPackageError(msg)
            continue
        if info.compress_type not in _SUPPORTED_ZIP_COMPRESSION:
            msg = "ZIP member uses an unsupported compression method"
            raise TeiPackageError(msg)
        _register_basename(logical_name, basenames)
        _require_xml_member(logical_name)
        _check_declared_member_size(info.file_size, limits)
        _check_compression_ratio(info.file_size, info.compress_size, limits)
        total_expanded = _account_declared_total(total_expanded, info.file_size, limits)
        descriptions.append(
            _MemberDescription(
                logical_name=logical_name,
                source_locator=f"{package_locator}!/{_quote_name(logical_name)}",
                expanded_bytes=info.file_size,
                compressed_bytes=info.compress_size,
                payload=info,
            )
        )
    _require_nonempty_collection(descriptions)
    return descriptions


def _tar_descriptions(
    archive: tarfile.TarFile,
    *,
    limits: PackageLimits,
    package_locator: str,
    compressed_package_bytes: int,
) -> list[_MemberDescription]:
    descriptions: list[_MemberDescription] = []
    full_names: set[str] = set()
    basenames: set[str] = set()
    total_expanded = 0
    member_count = 0
    try:
        while info := archive.next():
            member_count += 1
            _check_member_count(member_count, limits)
            logical_name = normalize_logical_name(
                info.name.rstrip("/") if info.isdir() else info.name
            )
            _register_full_name(logical_name, full_names)
            if info.isdir():
                if info.size != 0:
                    msg = "TAR.GZ directory member contains payload bytes"
                    raise TeiPackageError(msg)
                continue
            if not info.isfile() or _tar_member_is_sparse(info):
                msg = "TAR.GZ package contains a link, sparse file, or non-regular member"
                raise TeiPackageError(msg)
            _register_basename(logical_name, basenames)
            _require_xml_member(logical_name)
            _check_declared_member_size(info.size, limits)
            total_expanded = _account_declared_total(total_expanded, info.size, limits)
            _check_compression_ratio(total_expanded, compressed_package_bytes, limits)
            descriptions.append(
                _MemberDescription(
                    logical_name=logical_name,
                    source_locator=f"{package_locator}!/{_quote_name(logical_name)}",
                    expanded_bytes=info.size,
                    compressed_bytes=None,
                    payload=info,
                )
            )
    except (gzip.BadGzipFile, tarfile.HeaderError, tarfile.ReadError, zlib.error) as error:
        msg = "invalid TAR.GZ member table"
        raise TeiPackageError(msg) from error
    _require_nonempty_collection(descriptions)
    return descriptions


def _tar_member_is_sparse(info: tarfile.TarInfo) -> bool:
    return info.issparse() or any(
        key.startswith("GNU.sparse") or key == "SCHILY.realsize" for key in info.pax_headers
    )


def _register_logical_name(
    logical_name: str,
    *,
    full_names: set[str],
    basenames: set[str],
) -> None:
    _register_full_name(logical_name, full_names)
    _register_basename(logical_name, basenames)


def _register_full_name(logical_name: str, seen: set[str]) -> None:
    key = logical_name.casefold()
    if key in seen:
        msg = "source package contains duplicate normalized member names"
        raise TeiPackageError(msg)
    seen.add(key)


def _register_basename(logical_name: str, seen: set[str]) -> None:
    key = PurePosixPath(logical_name).name.casefold()
    if not key or key in seen:
        msg = "source package contains empty or colliding normalized basenames"
        raise TeiPackageError(msg)
    seen.add(key)


def _require_xml_member(logical_name: str) -> None:
    folded_name = logical_name.casefold()
    if folded_name.endswith(_NESTED_ARCHIVE_SUFFIXES):
        msg = "nested archives are not supported"
        raise TeiPackageError(msg)
    if not folded_name.endswith(".xml"):
        msg = "source package contains an unsupported non-XML member"
        raise TeiPackageError(msg)


def _check_member_count(member_count: int, limits: PackageLimits) -> None:
    if member_count > limits.max_member_count:
        msg = "source package exceeds the member-count limit"
        raise TeiPackageError(msg)


def _check_declared_member_size(expanded_bytes: int, limits: PackageLimits) -> None:
    if expanded_bytes < 0:
        msg = "package member declares a negative size"
        raise TeiPackageError(msg)
    if expanded_bytes > limits.max_member_expanded_bytes:
        msg = "package member exceeds the expanded-byte limit"
        raise TeiPackageError(msg)


def _account_declared_total(
    current_total: int,
    expanded_bytes: int,
    limits: PackageLimits,
) -> int:
    total = current_total + expanded_bytes
    if total > limits.max_total_expanded_bytes:
        msg = "package exceeds the total expanded-byte limit"
        raise TeiPackageError(msg)
    return total


def _check_compression_ratio(
    expanded_bytes: int,
    compressed_bytes: int,
    limits: PackageLimits,
) -> None:
    if compressed_bytes < 0:
        msg = "package member declares a negative compressed size"
        raise TeiPackageError(msg)
    if _compression_ratio(expanded_bytes, compressed_bytes) > limits.max_compression_ratio:
        msg = "package exceeds the compression-ratio limit"
        raise TeiPackageError(msg)


def _compression_ratio(expanded_bytes: int, compressed_bytes: int) -> float:
    if expanded_bytes == 0:
        return 0.0
    return expanded_bytes / max(compressed_bytes, 1)


def _require_nonempty_collection(descriptions: list[_MemberDescription]) -> None:
    if not descriptions:
        msg = "source collection contains no XML documents"
        raise TeiPackageError(msg)


def _sort_descriptions(
    descriptions: list[_MemberDescription],
) -> list[_MemberDescription]:
    return sorted(
        descriptions,
        key=lambda description: (
            description.logical_name.casefold(),
            description.logical_name,
        ),
    )


def _quote_name(logical_name: str) -> str:
    return quote(logical_name, safe="/-._~")
