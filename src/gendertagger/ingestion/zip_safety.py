"""Bound ZIP directory metadata before Python allocates ``ZipInfo`` objects."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO, cast

_EOCD_SIGNATURE = b"PK\x05\x06"
_ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_CENTRAL_DIRECTORY_SIGNATURE = b"PK\x01\x02"

_EOCD = struct.Struct("<4s4H2LH")
_ZIP64_EOCD = struct.Struct("<4sQ2H2L4Q")
_ZIP64_LOCATOR = struct.Struct("<4sLQL")
_CENTRAL_DIRECTORY_HEADER_BYTES = 46
_MAX_EOCD_COMMENT_BYTES = (1 << 16) - 1
_CLASSIC_COUNT_SENTINEL = (1 << 16) - 1
_CLASSIC_SIZE_SENTINEL = (1 << 32) - 1

# ZIP comments and extra fields are not scientific source payload. A fixed
# 64-KiB floor plus 16 KiB per persisted member permits long UTF-8 logical
# names and ordinary ZIP64 extras while bounding ``ZipFile``'s eager central-
# directory read. The cap is reproducible because it depends only on the
# persisted member-count limit, rather than mutable process configuration.
_MIN_CENTRAL_DIRECTORY_BYTES = 64 * 1024
_CENTRAL_DIRECTORY_BYTES_PER_ENTRY = 16 * 1024


class ZipPreflightErrorCode(StrEnum):
    """Stable failure categories that callers can map to format diagnostics."""

    invalid = "invalid"
    entry_count = "entry_count"
    metadata_size = "metadata_size"


class ZipPreflightError(ValueError):
    """Reject malformed or over-budget ZIP directory metadata."""

    def __init__(self, code: ZipPreflightErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ZipDirectorySummary:
    """Validated directory measurements obtained without constructing entries."""

    entry_count: int
    central_directory_bytes: int


@dataclass(frozen=True, slots=True)
class _DirectoryRecord:
    entry_count: int
    central_directory_bytes: int
    central_directory_offset: int
    directory_end_offset: int


def zip_central_directory_byte_limit(max_entry_count: int) -> int:
    """Derive the deterministic ZIP-metadata cap for one persisted count limit."""
    if max_entry_count <= 0:
        msg = "ZIP max_entry_count must be positive"
        raise ValueError(msg)
    return max(
        _MIN_CENTRAL_DIRECTORY_BYTES,
        max_entry_count * _CENTRAL_DIRECTORY_BYTES_PER_ENTRY,
    )


def preflight_zip_directory(
    source: BinaryIO,
    *,
    max_entry_count: int,
) -> ZipDirectorySummary:
    """Validate ZIP/ZIP64 directory bounds before constructing ``ZipFile``.

    The caller must provide a seekable binary stream. Its position is restored
    before return. Only the bounded EOCD tail and fixed-size directory headers
    are read; filenames, comments, and extra fields are skipped without being
    allocated.
    """
    metadata_limit = zip_central_directory_byte_limit(max_entry_count)
    original_offset = source.tell()
    try:
        source.seek(0, 2)
        file_size = source.tell()
        record = _directory_record(source, file_size=file_size)
        if record.entry_count > max_entry_count:
            _raise(
                ZipPreflightErrorCode.entry_count,
                "ZIP directory exceeds the entry-count limit",
            )
        if record.central_directory_bytes > metadata_limit:
            _raise(
                ZipPreflightErrorCode.metadata_size,
                "ZIP central directory exceeds the metadata-size limit",
            )

        actual_entry_count = _scan_central_directory(
            source,
            record=record,
            max_entry_count=max_entry_count,
        )
        if actual_entry_count != record.entry_count:
            _raise(
                ZipPreflightErrorCode.invalid,
                "ZIP directory entry count disagrees with its end record",
            )
        return ZipDirectorySummary(
            entry_count=actual_entry_count,
            central_directory_bytes=record.central_directory_bytes,
        )
    finally:
        source.seek(original_offset)


def _directory_record(source: BinaryIO, *, file_size: int) -> _DirectoryRecord:
    eocd_offset, eocd = _classic_eocd(source, file_size=file_size)
    (
        _,
        disk_number,
        directory_disk,
        entries_on_disk,
        total_entries,
        directory_bytes,
        directory_offset,
        _,
    ) = eocd
    zip64 = _zip64_directory_record(source, eocd_offset=eocd_offset)
    if zip64 is not None:
        return zip64

    if (
        disk_number == _CLASSIC_COUNT_SENTINEL
        or directory_disk == _CLASSIC_COUNT_SENTINEL
        or entries_on_disk == _CLASSIC_COUNT_SENTINEL
        or total_entries == _CLASSIC_COUNT_SENTINEL
        or directory_bytes == _CLASSIC_SIZE_SENTINEL
        or directory_offset == _CLASSIC_SIZE_SENTINEL
    ):
        _raise(ZipPreflightErrorCode.invalid, "ZIP64 end records are missing")
    _require_single_disk(
        disk_number=disk_number,
        directory_disk=directory_disk,
        entries_on_disk=entries_on_disk,
        total_entries=total_entries,
    )
    if directory_offset + directory_bytes > eocd_offset:
        _raise(ZipPreflightErrorCode.invalid, "ZIP central-directory offset is invalid")
    return _DirectoryRecord(
        entry_count=total_entries,
        central_directory_bytes=directory_bytes,
        central_directory_offset=directory_offset,
        directory_end_offset=eocd_offset,
    )


def _classic_eocd(
    source: BinaryIO,
    *,
    file_size: int,
) -> tuple[int, tuple[bytes, int, int, int, int, int, int, int]]:
    tail_bytes = min(file_size, _EOCD.size + _MAX_EOCD_COMMENT_BYTES)
    tail_offset = file_size - tail_bytes
    tail = _read_at(source, tail_offset, tail_bytes)
    search_end = len(tail)
    while True:
        relative_offset = tail.rfind(_EOCD_SIGNATURE, 0, search_end)
        if relative_offset < 0:
            _raise(ZipPreflightErrorCode.invalid, "ZIP end-of-directory record is missing")
        if relative_offset + _EOCD.size <= len(tail):
            eocd = _EOCD.unpack_from(tail, relative_offset)
            comment_bytes = eocd[-1]
            absolute_offset = tail_offset + relative_offset
            if absolute_offset + _EOCD.size + comment_bytes == file_size:
                return absolute_offset, eocd
        search_end = relative_offset


def _zip64_directory_record(
    source: BinaryIO,
    *,
    eocd_offset: int,
) -> _DirectoryRecord | None:
    locator_offset = eocd_offset - _ZIP64_LOCATOR.size
    if locator_offset < 0:
        return None
    locator = _ZIP64_LOCATOR.unpack(_read_at(source, locator_offset, _ZIP64_LOCATOR.size))
    signature, directory_disk, relative_eocd_offset, disk_count = locator
    if signature != _ZIP64_LOCATOR_SIGNATURE:
        return None
    if directory_disk != 0 or disk_count != 1:
        _raise(ZipPreflightErrorCode.invalid, "multi-disk ZIP archives are unsupported")

    expected_eocd_offset = locator_offset - _ZIP64_EOCD.size
    if relative_eocd_offset > expected_eocd_offset:
        _raise(ZipPreflightErrorCode.invalid, "ZIP64 end-record locator is invalid")

    zip64_offset = relative_eocd_offset
    record = _read_at(source, zip64_offset, _ZIP64_EOCD.size)
    extensible_bytes = expected_eocd_offset - relative_eocd_offset
    if not record.startswith(_ZIP64_EOCD_SIGNATURE) and zip64_offset != expected_eocd_offset:
        # The locator offset is relative to the archive rather than to a
        # prepended executable. Match ``zipfile``'s supported concatenation
        # behavior and assume no ZIP64 extensible-data sector in that case.
        zip64_offset = expected_eocd_offset
        extensible_bytes = 0
        record = _read_at(source, zip64_offset, _ZIP64_EOCD.size)
    if not record.startswith(_ZIP64_EOCD_SIGNATURE):
        _raise(ZipPreflightErrorCode.invalid, "ZIP64 end-of-directory record is missing")

    (
        _,
        record_payload_bytes,
        _,
        _,
        disk_number,
        directory_disk,
        entries_on_disk,
        total_entries,
        directory_bytes,
        directory_offset,
    ) = _ZIP64_EOCD.unpack(record)
    if record_payload_bytes + 12 != _ZIP64_EOCD.size + extensible_bytes:
        _raise(ZipPreflightErrorCode.invalid, "ZIP64 end-record size is invalid")
    if directory_offset + directory_bytes != relative_eocd_offset:
        _raise(ZipPreflightErrorCode.invalid, "ZIP64 central-directory offset is invalid")
    _require_single_disk(
        disk_number=disk_number,
        directory_disk=directory_disk,
        entries_on_disk=entries_on_disk,
        total_entries=total_entries,
    )
    return _DirectoryRecord(
        entry_count=total_entries,
        central_directory_bytes=directory_bytes,
        central_directory_offset=directory_offset,
        directory_end_offset=zip64_offset,
    )


def _require_single_disk(
    *,
    disk_number: int,
    directory_disk: int,
    entries_on_disk: int,
    total_entries: int,
) -> None:
    if disk_number != 0 or directory_disk != 0 or entries_on_disk != total_entries:
        _raise(ZipPreflightErrorCode.invalid, "multi-disk ZIP archives are unsupported")


def _scan_central_directory(
    source: BinaryIO,
    *,
    record: _DirectoryRecord,
    max_entry_count: int,
) -> int:
    # ZIP offsets are relative to the archive start, so infer any safe
    # prepended prefix from the actual end-record location as ``zipfile`` does.
    prefix_bytes = (
        record.directory_end_offset
        - record.central_directory_bytes
        - record.central_directory_offset
    )
    if prefix_bytes < 0:
        _raise(ZipPreflightErrorCode.invalid, "ZIP central-directory offset is invalid")
    absolute_offset = prefix_bytes + record.central_directory_offset
    remaining_bytes = record.central_directory_bytes
    source.seek(absolute_offset)
    entry_count = 0
    while remaining_bytes:
        if remaining_bytes < _CENTRAL_DIRECTORY_HEADER_BYTES:
            _raise(ZipPreflightErrorCode.invalid, "ZIP central directory is truncated")
        header = _read_exact(source, _CENTRAL_DIRECTORY_HEADER_BYTES)
        if not header.startswith(_CENTRAL_DIRECTORY_SIGNATURE):
            _raise(ZipPreflightErrorCode.invalid, "ZIP central directory is malformed")
        filename_bytes, extra_bytes, comment_bytes = struct.unpack_from("<3H", header, 28)
        variable_bytes = filename_bytes + extra_bytes + comment_bytes
        entry_bytes = _CENTRAL_DIRECTORY_HEADER_BYTES + variable_bytes
        if entry_bytes > remaining_bytes:
            _raise(ZipPreflightErrorCode.invalid, "ZIP central directory is truncated")
        entry_count += 1
        if entry_count > max_entry_count:
            _raise(
                ZipPreflightErrorCode.entry_count,
                "ZIP directory exceeds the entry-count limit",
            )
        source.seek(variable_bytes, 1)
        remaining_bytes -= entry_bytes
    return entry_count


def _read_at(source: BinaryIO, offset: int, byte_count: int) -> bytes:
    if offset < 0:
        _raise(ZipPreflightErrorCode.invalid, "ZIP metadata offset is invalid")
    source.seek(offset)
    return _read_exact(source, byte_count)


def _read_exact(source: BinaryIO, byte_count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = byte_count
    while remaining:
        raw_chunk = cast(object, source.read(remaining))
        if raw_chunk is None or not isinstance(raw_chunk, bytes):
            msg = "ZIP source did not return binary data"
            raise OSError(msg)
        if not raw_chunk:
            _raise(ZipPreflightErrorCode.invalid, "ZIP metadata is truncated")
        chunks.append(raw_chunk)
        remaining -= len(raw_chunk)
    return b"".join(chunks)


def _raise(code: ZipPreflightErrorCode, message: str) -> None:
    raise ZipPreflightError(code, message)
