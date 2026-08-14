from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from gendertagger.ingestion.collection import (
    TeiCollectionError,
    TeiCollectionImporter,
)
from gendertagger.ingestion.package import (
    LooseDocument,
    PackageLimits,
    iter_loose_xml_members,
    iter_tar_gz_xml_members,
    iter_zip_xml_members,
)
from gendertagger.ingestion.tei import TeiPersonParser
from gendertagger.models.project import TeiImportProfile

pytestmark = pytest.mark.unit

LIMITS = PackageLimits(
    max_member_count=10,
    max_member_expanded_bytes=10_000,
    max_total_expanded_bytes=20_000,
    max_compression_ratio=1_000,
)


def _tei_person(tei_id: str, surname: str) -> bytes:
    return f"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
<person xml:id="{tei_id}"><persName type="reg"><surname>{surname}</surname></persName></person>
</listPerson></body></text></TEI>""".encode()


def _zip_source(entries: list[tuple[str, bytes]]) -> io.BytesIO:
    source = io.BytesIO()
    with zipfile.ZipFile(source, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    source.seek(0)
    return source


def _tar_source(entries: list[tuple[str, bytes]]) -> io.BytesIO:
    source = io.BytesIO()
    with tarfile.open(fileobj=source, mode="w:gz") as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    source.seek(0)
    return source


@pytest.mark.parametrize(
    ("profile", "expects_name_forms"),
    [
        (TeiImportProfile.tei_p5_person_register_v1, False),
        (TeiImportProfile.tei_p5_person_register_v2, True),
        (TeiImportProfile.tei_p5_person_register_v3, True),
    ],
)
def test_loose_collection_parses_in_member_order_with_profile_and_provenance(
    profile: TeiImportProfile,
    *,
    expects_name_forms: bool,
) -> None:
    members = iter_loose_xml_members(
        [
            LooseDocument("b.xml", io.BytesIO(_tei_person("p2", "Second"))),
            LooseDocument(
                "a.xml",
                io.BytesIO(_tei_person("pä1", "First")),
                source_locator="artifact:a",
            ),
        ],
        limits=LIMITS,
    )

    people = list(TeiCollectionImporter(TeiPersonParser()).iter_people(members, profile=profile))

    assert [collected.person.tei_id for collected in people] == ["pä1", "p2"]
    assert [collected.source_member_name for collected in people] == ["a.xml", "b.xml"]
    assert [collected.source_record_locator for collected in people] == [
        "xml:id=p%C3%A41",
        "xml:id=p2",
    ]
    assert all(
        (collected.person.name_forms is not None) is expects_name_forms for collected in people
    )


def test_collection_rejects_duplicate_xml_id_across_members() -> None:
    members = iter_loose_xml_members(
        [
            LooseDocument("a.xml", io.BytesIO(_tei_person("same", "First"))),
            LooseDocument("b.xml", io.BytesIO(_tei_person("same", "Second"))),
        ],
        limits=LIMITS,
    )

    with pytest.raises(TeiCollectionError, match="across source members"):
        list(
            TeiCollectionImporter(TeiPersonParser()).iter_people(
                members,
                profile=TeiImportProfile.tei_p5_person_register_v3,
            )
        )


@pytest.mark.parametrize("packaging", ["zip", "tar.gz"])
def test_archive_collection_parses_benign_members_with_exact_member_locators(
    packaging: str,
) -> None:
    entries = [
        ("letters/B.xml", _tei_person("p2", "Second")),
        ("A.xml", _tei_person("p1", "First")),
    ]
    if packaging == "zip":
        members = iter_zip_xml_members(
            _zip_source(entries),
            limits=LIMITS,
            package_locator="artifact:bundle",
        )
    else:
        members = iter_tar_gz_xml_members(
            _tar_source(entries),
            limits=LIMITS,
            package_locator="artifact:bundle",
        )

    people = list(
        TeiCollectionImporter(TeiPersonParser()).iter_people(
            members,
            profile=TeiImportProfile.tei_p5_person_register_v3,
        )
    )

    assert [collected.person.tei_id for collected in people] == ["p1", "p2"]
    assert [collected.source_member_name for collected in people] == ["A.xml", "letters/B.xml"]
    assert [collected.source_record_locator for collected in people] == [
        "xml:id=p1",
        "xml:id=p2",
    ]
