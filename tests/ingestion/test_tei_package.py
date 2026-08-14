from __future__ import annotations

import io
import stat
import struct
import tarfile
import zipfile
from collections.abc import Iterable

import pytest

from gendertagger.ingestion.package import (
    LooseDocument,
    PackageLimits,
    SourceMember,
    TeiPackageError,
    iter_loose_xml_members,
    iter_tar_gz_xml_members,
    iter_zip_xml_members,
    normalize_logical_name,
)

pytestmark = pytest.mark.unit

XML_A = b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><person xml:id="a"/></TEI>'
XML_B = b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><person xml:id="b"/></TEI>'


class _NonSeekableBytesIO(io.BytesIO):
    def seekable(self) -> bool:
        return False

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        del offset, whence
        raise io.UnsupportedOperation("stream is not seekable")

    def tell(self) -> int:
        raise io.UnsupportedOperation("stream has no position")


def _limits(**overrides: int | float) -> PackageLimits:
    values: dict[str, int | float] = {
        "max_member_count": 10,
        "max_member_expanded_bytes": 10_000,
        "max_total_expanded_bytes": 20_000,
        "max_compression_ratio": 1_000.0,
    }
    values.update(overrides)
    return PackageLimits(**values)  # type: ignore[arg-type]


def _consume(members: Iterable[SourceMember]) -> list[tuple[str, str, bytes]]:
    return [
        (
            member.logical_name,
            member.source_locator,
            member.source.read(),
        )
        for member in members
    ]


def _zip_bytes(
    entries: list[tuple[str | zipfile.ZipInfo, bytes]],
    *,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, mode="w", compression=compression) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return target.getvalue()


def _zip64_directory_bytes(archive: bytes, *, entry_count: int) -> bytes:
    """Replace one classic EOCD with a small synthetic ZIP64 end-record set."""
    eocd_offset = archive.rfind(b"PK\x05\x06")
    assert eocd_offset >= 0
    classic_eocd = bytearray(archive[eocd_offset:])
    directory_bytes = int.from_bytes(classic_eocd[12:16], "little")
    directory_offset = int.from_bytes(classic_eocd[16:20], "little")
    classic_eocd[8:12] = b"\xff\xff\xff\xff"
    classic_eocd[12:20] = b"\xff" * 8
    zip64_eocd = struct.pack(
        "<4sQ2H2L4Q",
        b"PK\x06\x06",
        44,
        45,
        45,
        0,
        0,
        entry_count,
        entry_count,
        directory_bytes,
        directory_offset,
    )
    zip64_locator = struct.pack(
        "<4sLQL",
        b"PK\x06\x07",
        0,
        eocd_offset,
        1,
    )
    return archive[:eocd_offset] + zip64_eocd + zip64_locator + classic_eocd


def _tar_gz_bytes(
    entries: list[tuple[tarfile.TarInfo, bytes]],
    *,
    tar_format: int = tarfile.DEFAULT_FORMAT,
) -> bytes:
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w:gz", format=tar_format) as archive:
        for info, payload in entries:
            archive.addfile(info, io.BytesIO(payload) if info.isfile() else None)
    return target.getvalue()


def _tar_file(name: str, payload: bytes) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    return info, payload


@pytest.mark.parametrize(
    "raw_name",
    [
        "",
        "/absolute.xml",
        "C:/drive.xml",
        "../escape.xml",
        "dir/../escape.xml",
        "dir/./person.xml",
        "dir//person.xml",
        "dir\\person.xml",
        "nul\x00.xml",
        "line\nbreak.xml",
        "right-to-left-override-\u202e.xml",
    ],
)
def test_logical_name_normalization_rejects_unsafe_or_ambiguous_paths(raw_name: str) -> None:
    with pytest.raises(TeiPackageError):
        normalize_logical_name(raw_name)


def test_loose_members_normalize_nfc_sort_names_and_preserve_locators() -> None:
    documents = [
        LooseDocument("b.xml", io.BytesIO(XML_B), source_locator="artifact:b"),
        LooseDocument("names/A\u0308.xml", io.BytesIO(XML_A)),
    ]

    consumed = _consume(iter_loose_xml_members(documents, limits=_limits()))

    assert consumed == [
        ("b.xml", "artifact:b", XML_B),
        ("names/Ä.xml", "loose:names/%C3%84.xml", XML_A),
    ]


def test_loose_members_reject_nfc_casefold_basename_collisions() -> None:
    documents = [
        LooseDocument("one/A\u0308.xml", io.BytesIO(XML_A)),
        LooseDocument("two/ä.XML", io.BytesIO(XML_B)),
    ]

    with pytest.raises(TeiPackageError, match="basenames"):
        _consume(iter_loose_xml_members(documents, limits=_limits()))


def test_loose_members_enforce_count_per_member_and_total_limits_while_reading() -> None:
    with pytest.raises(TeiPackageError, match="member-count"):
        _consume(
            iter_loose_xml_members(
                [
                    LooseDocument("a.xml", io.BytesIO(XML_A)),
                    LooseDocument("b.xml", io.BytesIO(XML_B)),
                ],
                limits=_limits(max_member_count=1),
            )
        )

    with pytest.raises(TeiPackageError, match="expanded-byte"):
        _consume(
            iter_loose_xml_members(
                [LooseDocument("a.xml", io.BytesIO(XML_A))],
                limits=_limits(max_member_expanded_bytes=len(XML_A) - 1),
            )
        )

    with pytest.raises(TeiPackageError, match="total expanded-byte"):
        _consume(
            iter_loose_xml_members(
                [
                    LooseDocument("a.xml", io.BytesIO(XML_A)),
                    LooseDocument("b.xml", io.BytesIO(XML_B)),
                ],
                limits=_limits(max_total_expanded_bytes=len(XML_A) + len(XML_B) - 1),
            )
        )


def test_loose_member_openers_keep_only_one_source_open_at_a_time() -> None:
    active_sources = 0
    peak_active_sources = 0

    class _TrackedSource(io.BytesIO):
        def __init__(self, payload: bytes) -> None:
            nonlocal active_sources, peak_active_sources
            super().__init__(payload)
            active_sources += 1
            peak_active_sources = max(peak_active_sources, active_sources)

        def close(self) -> None:
            nonlocal active_sources
            if not self.closed:
                active_sources -= 1
            super().close()

    documents = [
        LooseDocument("b.xml", source_opener=lambda: _TrackedSource(XML_B)),
        LooseDocument("a.xml", source_opener=lambda: _TrackedSource(XML_A)),
    ]

    consumed = _consume(iter_loose_xml_members(documents, limits=_limits()))

    assert [name for name, _, _ in consumed] == ["a.xml", "b.xml"]
    assert peak_active_sources == 1
    assert active_sources == 0


def test_single_stream_mode_can_disable_the_loose_xml_filename_policy() -> None:
    document = LooseDocument("register.tei", io.BytesIO(XML_A))
    with pytest.raises(TeiPackageError, match="non-XML"):
        _consume(iter_loose_xml_members([document], limits=_limits()))

    consumed = _consume(
        iter_loose_xml_members(
            [LooseDocument("register.tei", io.BytesIO(XML_A))],
            limits=_limits(),
            require_xml_suffix=False,
        )
    )

    assert [(name, payload) for name, _, payload in consumed] == [("register.tei", XML_A)]


def test_zip_reader_ignores_valid_directories_and_yields_xml_in_normalized_order() -> None:
    archive = _zip_bytes(
        [
            ("register/", b""),
            ("register/b.xml", XML_B),
            ("a.xml", XML_A),
        ]
    )

    consumed = _consume(
        iter_zip_xml_members(
            io.BytesIO(archive),
            limits=_limits(),
            package_locator="artifact:zip",
        )
    )

    assert consumed == [
        ("a.xml", "artifact:zip!/a.xml", XML_A),
        ("register/b.xml", "artifact:zip!/register/b.xml", XML_B),
    ]


def test_zip_and_tar_gz_readers_accept_non_seekable_package_streams() -> None:
    zip_archive = _zip_bytes([("a.xml", XML_A)])
    tar_archive = _tar_gz_bytes([_tar_file("a.xml", XML_A)])

    zip_members = _consume(iter_zip_xml_members(_NonSeekableBytesIO(zip_archive), limits=_limits()))
    tar_members = _consume(
        iter_tar_gz_xml_members(_NonSeekableBytesIO(tar_archive), limits=_limits())
    )

    assert [(name, payload) for name, _, payload in zip_members] == [("a.xml", XML_A)]
    assert [(name, payload) for name, _, payload in tar_members] == [("a.xml", XML_A)]


@pytest.mark.parametrize("member_name", ["../escape.xml", "nested.zip", "notes.txt"])
def test_zip_reader_rejects_unsafe_nested_or_non_xml_names(member_name: str) -> None:
    archive = _zip_bytes([(member_name, XML_A)])

    with pytest.raises(TeiPackageError):
        _consume(iter_zip_xml_members(io.BytesIO(archive), limits=_limits()))


def test_zip_reader_rejects_invalid_bytes_and_empty_collections() -> None:
    with pytest.raises(TeiPackageError, match="invalid ZIP"):
        _consume(iter_zip_xml_members(io.BytesIO(b"not a ZIP"), limits=_limits()))

    with pytest.raises(TeiPackageError, match="no XML"):
        _consume(iter_zip_xml_members(io.BytesIO(_zip_bytes([])), limits=_limits()))


def test_zip_reader_rejects_encrypted_links_devices_and_normalized_duplicates() -> None:
    encrypted = bytearray(_zip_bytes([("a.xml", XML_A)]))
    local_header = encrypted.index(b"PK\x03\x04")
    central_header = encrypted.index(b"PK\x01\x02")
    encrypted[local_header + 6 : local_header + 8] = (
        int.from_bytes(encrypted[local_header + 6 : local_header + 8], "little") | 1
    ).to_bytes(2, "little")
    encrypted[central_header + 8 : central_header + 10] = (
        int.from_bytes(encrypted[central_header + 8 : central_header + 10], "little") | 1
    ).to_bytes(2, "little")
    with pytest.raises(TeiPackageError, match="encrypted"):
        _consume(iter_zip_xml_members(io.BytesIO(encrypted), limits=_limits()))

    symlink = zipfile.ZipInfo("link.xml")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(TeiPackageError, match="symbolic link"):
        _consume(
            iter_zip_xml_members(
                io.BytesIO(_zip_bytes([(symlink, b"target.xml")])),
                limits=_limits(),
            )
        )

    device = zipfile.ZipInfo("device.xml")
    device.create_system = 3
    device.external_attr = (stat.S_IFCHR | 0o600) << 16
    with pytest.raises(TeiPackageError, match="non-regular"):
        _consume(
            iter_zip_xml_members(
                io.BytesIO(_zip_bytes([(device, b"")])),
                limits=_limits(),
            )
        )

    duplicate = _zip_bytes([("one/A.xml", XML_A), ("two/a.XML", XML_B)])
    with pytest.raises(TeiPackageError, match="basenames"):
        _consume(iter_zip_xml_members(io.BytesIO(duplicate), limits=_limits()))


def test_zip_reader_rejects_a_nul_hidden_by_zipfile_filename_sanitization() -> None:
    archive = bytearray(_zip_bytes([("a.xmlxevil", XML_A)]))
    local_header = archive.index(b"PK\x03\x04")
    central_header = archive.index(b"PK\x01\x02")
    archive[local_header + 30 + 5] = 0
    archive[central_header + 46 + 5] = 0

    with pytest.raises(TeiPackageError, match="unsafe or invalid"):
        _consume(iter_zip_xml_members(io.BytesIO(archive), limits=_limits()))


def test_zip_reader_enforces_declared_expansion_and_compression_limits() -> None:
    archive = _zip_bytes([("a.xml", XML_A), ("b.xml", XML_B)])
    with pytest.raises(TeiPackageError, match="member-count"):
        _consume(
            iter_zip_xml_members(
                io.BytesIO(archive),
                limits=_limits(max_member_count=1),
            )
        )
    with pytest.raises(TeiPackageError, match="expanded-byte"):
        _consume(
            iter_zip_xml_members(
                io.BytesIO(archive),
                limits=_limits(max_member_expanded_bytes=len(XML_A) - 1),
            )
        )
    with pytest.raises(TeiPackageError, match="total expanded-byte"):
        _consume(
            iter_zip_xml_members(
                io.BytesIO(archive),
                limits=_limits(max_total_expanded_bytes=len(XML_A) + len(XML_B) - 1),
            )
        )

    compressed_bomb = _zip_bytes(
        [("bomb.xml", b"<TEI>" + b" " * 20_000 + b"</TEI>")],
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(TeiPackageError, match="compression-ratio"):
        _consume(
            iter_zip_xml_members(
                io.BytesIO(compressed_bomb),
                limits=_limits(
                    max_member_expanded_bytes=30_000,
                    max_total_expanded_bytes=30_000,
                    max_compression_ratio=2.0,
                ),
            )
        )


def test_zip_reader_preflights_classic_and_zip64_counts_before_zipfile_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classic = bytearray(_zip_bytes([("a.xml", XML_A)]))
    classic_eocd = classic.rfind(b"PK\x05\x06")
    assert classic_eocd >= 0
    classic[classic_eocd + 8 : classic_eocd + 12] = (50_000).to_bytes(2, "little") * 2
    zip64 = _zip64_directory_bytes(
        _zip_bytes([("a.xml", XML_A)]),
        entry_count=2_000_000,
    )

    def reject_zipfile_construction(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ZipFile must not be constructed before count preflight")

    monkeypatch.setattr(zipfile, "ZipFile", reject_zipfile_construction)
    for archive in (bytes(classic), zip64):
        with pytest.raises(TeiPackageError, match="member-count"):
            _consume(
                iter_zip_xml_members(
                    io.BytesIO(archive),
                    limits=_limits(max_member_count=1),
                )
            )


def test_zip_reader_preflights_central_directory_metadata_before_zipfile_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = zipfile.ZipInfo("a.xml")
    info.comment = b"x" * 65_535
    archive = _zip_bytes([(info, XML_A)])

    def reject_zipfile_construction(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ZipFile must not be constructed before metadata preflight")

    monkeypatch.setattr(zipfile, "ZipFile", reject_zipfile_construction)
    with pytest.raises(TeiPackageError, match="metadata-size"):
        _consume(
            iter_zip_xml_members(
                io.BytesIO(archive),
                limits=_limits(max_member_count=1),
            )
        )


def test_zip_reader_counts_directory_records_instead_of_trusting_eocd_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = bytearray(_zip_bytes([("a.xml", XML_A), ("b.xml", XML_B)]))
    eocd_offset = archive.rfind(b"PK\x05\x06")
    assert eocd_offset >= 0
    archive[eocd_offset + 8 : eocd_offset + 12] = (1).to_bytes(2, "little") * 2

    def reject_zipfile_construction(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ZipFile must not be constructed before directory scan")

    monkeypatch.setattr(zipfile, "ZipFile", reject_zipfile_construction)
    with pytest.raises(TeiPackageError, match="member-count"):
        _consume(
            iter_zip_xml_members(
                io.BytesIO(archive),
                limits=_limits(max_member_count=1),
            )
        )


def test_zip_reader_accepts_valid_small_zip64_directory() -> None:
    archive = _zip64_directory_bytes(
        _zip_bytes([("a.xml", XML_A)]),
        entry_count=1,
    )

    consumed = _consume(iter_zip_xml_members(io.BytesIO(archive), limits=_limits()))

    assert [(name, payload) for name, _, payload in consumed] == [("a.xml", XML_A)]


def test_tar_gz_reader_ignores_directories_and_yields_regular_xml_in_order() -> None:
    directory = tarfile.TarInfo("register")
    directory.type = tarfile.DIRTYPE
    archive = _tar_gz_bytes(
        [
            (directory, b""),
            _tar_file("register/b.xml", XML_B),
            _tar_file("a.xml", XML_A),
        ]
    )

    consumed = _consume(
        iter_tar_gz_xml_members(
            io.BytesIO(archive),
            limits=_limits(),
            package_locator="artifact:tar",
        )
    )

    assert consumed == [
        ("a.xml", "artifact:tar!/a.xml", XML_A),
        ("register/b.xml", "artifact:tar!/register/b.xml", XML_B),
    ]


@pytest.mark.parametrize(
    "member_type",
    [
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
        tarfile.FIFOTYPE,
    ],
)
def test_tar_gz_reader_rejects_links_devices_and_other_non_regular_members(
    member_type: bytes,
) -> None:
    unsafe = tarfile.TarInfo("unsafe.xml")
    unsafe.type = member_type
    unsafe.linkname = "target.xml"
    archive = _tar_gz_bytes([(unsafe, b"")])

    with pytest.raises(TeiPackageError, match="non-regular"):
        _consume(iter_tar_gz_xml_members(io.BytesIO(archive), limits=_limits()))


@pytest.mark.parametrize("member_name", ["../escape.xml", "nested.tar.gz", "notes.csv"])
def test_tar_gz_reader_rejects_unsafe_nested_or_non_xml_names(member_name: str) -> None:
    archive = _tar_gz_bytes([_tar_file(member_name, XML_A)])

    with pytest.raises(TeiPackageError):
        _consume(iter_tar_gz_xml_members(io.BytesIO(archive), limits=_limits()))


def test_tar_gz_reader_rejects_invalid_bytes_and_empty_collections() -> None:
    with pytest.raises(TeiPackageError, match=r"invalid TAR\.GZ"):
        _consume(iter_tar_gz_xml_members(io.BytesIO(b"not a TAR.GZ"), limits=_limits()))

    empty = _tar_gz_bytes([])
    with pytest.raises(TeiPackageError, match="no XML"):
        _consume(iter_tar_gz_xml_members(io.BytesIO(empty), limits=_limits()))


def test_tar_gz_reader_rejects_duplicates_and_enforces_all_expansion_limits() -> None:
    duplicate = _tar_gz_bytes([_tar_file("one/A.xml", XML_A), _tar_file("two/a.XML", XML_B)])
    with pytest.raises(TeiPackageError, match="basenames"):
        _consume(iter_tar_gz_xml_members(io.BytesIO(duplicate), limits=_limits()))

    archive = _tar_gz_bytes([_tar_file("a.xml", XML_A), _tar_file("b.xml", XML_B)])
    with pytest.raises(TeiPackageError, match="member-count"):
        _consume(
            iter_tar_gz_xml_members(
                io.BytesIO(archive),
                limits=_limits(max_member_count=1),
            )
        )
    with pytest.raises(TeiPackageError, match="expanded-byte"):
        _consume(
            iter_tar_gz_xml_members(
                io.BytesIO(archive),
                limits=_limits(max_member_expanded_bytes=len(XML_A) - 1),
            )
        )
    with pytest.raises(TeiPackageError, match="total expanded-byte"):
        _consume(
            iter_tar_gz_xml_members(
                io.BytesIO(archive),
                limits=_limits(max_total_expanded_bytes=len(XML_A) + len(XML_B) - 1),
            )
        )

    compressed_bomb = _tar_gz_bytes([_tar_file("bomb.xml", b"<TEI>" + b" " * 20_000 + b"</TEI>")])
    with pytest.raises(TeiPackageError, match="compression-ratio"):
        _consume(
            iter_tar_gz_xml_members(
                io.BytesIO(compressed_bomb),
                limits=_limits(
                    max_member_expanded_bytes=30_000,
                    max_total_expanded_bytes=40_000,
                    max_compression_ratio=2.0,
                ),
            )
        )


def test_tar_gz_reader_counts_pax_and_gnu_metadata_against_expansion_limit() -> None:
    pax_info = tarfile.TarInfo("a.xml")
    pax_info.size = len(XML_A)
    pax_info.pax_headers = {"comment": "x" * 50_000}
    pax_archive = _tar_gz_bytes(
        [(pax_info, XML_A)],
        tar_format=tarfile.PAX_FORMAT,
    )

    gnu_info = tarfile.TarInfo(f"{'x' * 50_000}.xml")
    gnu_info.size = len(XML_A)
    gnu_archive = _tar_gz_bytes(
        [(gnu_info, XML_A)],
        tar_format=tarfile.GNU_FORMAT,
    )

    for archive in (pax_archive, gnu_archive):
        with pytest.raises(TeiPackageError, match="total expanded-byte"):
            _consume(
                iter_tar_gz_xml_members(
                    io.BytesIO(archive),
                    limits=_limits(max_total_expanded_bytes=20_000),
                )
            )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_member_count", 0),
        ("max_member_expanded_bytes", 0),
        ("max_total_expanded_bytes", -1),
        ("max_compression_ratio", float("inf")),
    ],
)
def test_package_limits_require_positive_finite_values(field: str, value: int | float) -> None:
    with pytest.raises(ValueError, match="must be"):
        _limits(**{field: value})
