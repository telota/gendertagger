import csv
import importlib
import io
import json
import re
import stat
import struct
import zipfile
from collections.abc import Callable
from typing import Any

import pytest

from gendertagger.ingestion.tabular import (
    TEI_EQUIVALENT_HEADERS,
    TabularImportError,
    TabularImportPolicy,
    TabularSourceReadError,
    TeiEquivalentPersonRegisterParser,
)
from gendertagger.models.person import PersonEvent, PersonInput, PersonNameForm, PersonNameType

# openpyxl ships no type information; the workbook fixtures only use its dynamic API.
openpyxl: Any = importlib.import_module("openpyxl")


def _source_record() -> dict[str, object]:
    return {
        "xml:id": "p1",
        "persName": [
            {
                "type": "reg",
                "surname": "Example",
                "forename": ["Anna Maria", "Luise"],
            },
            {
                "type": "alt",
                "subtype": "birthname",
                "surname": "Sample",
                "forename": ["Anna", "Marie"],
            },
            {"type": "alt", "name": "A. Example"},
        ],
        "birth": "um 1810",
        "death": None,
        "event": [
            {"type": "wedding", "when": "1832-09-20", "note": "Berlin"},
            {"type": "appointment"},
        ],
        "note": "Scholar and editor.",
        "idno": [
            {"type": "uri", "value": "https://d-nb.info/gnd/123456789"},
            {"type": "uri", "value": "https://viaf.org/viaf/98765"},
            {"type": "uri", "value": "https://www.wikidata.org/entity/Q42"},
            {"type": "local-catalogue", "value": "abc-123"},
        ],
    }


def _expected_person() -> PersonInput:
    name_forms = [
        PersonNameForm(
            type=PersonNameType.regular,
            surname="Example",
            forenames=["Anna Maria", "Luise"],
        ),
        PersonNameForm(
            type=PersonNameType.alternative,
            subtype="birthname",
            surname="Sample",
            forenames=["Anna", "Marie"],
        ),
        PersonNameForm(type=PersonNameType.alternative, name="A. Example"),
    ]
    return PersonInput(
        tei_id="p1",
        surname="Example",
        forenames=["Anna Maria", "Luise"],
        birth="um 1810",
        note="Scholar and editor.",
        events=[
            PersonEvent(type="wedding", when="1832-09-20", note="Berlin"),
            PersonEvent(type="appointment"),
        ],
        alt_names=["Sample Anna Marie", "A. Example"],
        name_forms=name_forms,
        gnd_id="123456789",
        external_ids={
            "viaf": "98765",
            "wikidata": "Q42",
            "local_catalogue": "abc-123",
        },
    )


def _json_source(records: list[dict[str, object]]) -> bytes:
    return json.dumps(records, ensure_ascii=False).encode()


def _csv_source(records: list[dict[str, object]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=",", lineterminator="\r\n")
    writer.writerow(TEI_EQUIVALENT_HEADERS)
    for record in records:
        writer.writerow(
            [
                record["xml:id"],
                json.dumps(record["persName"], ensure_ascii=False),
                record["birth"] or "",
                record["death"] or "",
                json.dumps(record["event"], ensure_ascii=False),
                record["note"] or "",
                json.dumps(record["idno"], ensure_ascii=False),
            ]
        )
    return output.getvalue().encode()


def _xlsx_source(
    records: list[dict[str, object]],
    *,
    mutate: Callable[[object, object], None] | None = None,
) -> bytes:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "persons"
    worksheet.append(list(TEI_EQUIVALENT_HEADERS))
    for record in records:
        worksheet.append(
            [
                record["xml:id"],
                json.dumps(record["persName"], ensure_ascii=False),
                record["birth"] or None,
                record["death"] or None,
                json.dumps(record["event"], ensure_ascii=False),
                record["note"] or None,
                json.dumps(record["idno"], ensure_ascii=False),
            ]
        )
    if mutate is not None:
        mutate(workbook, worksheet)
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _hide_persons_worksheet(workbook: Any, worksheet: Any) -> None:
    workbook.create_sheet("blank")
    worksheet.sheet_state = "hidden"


def _rewrite_zip_members(
    source: bytes,
    *,
    replacements: dict[str, bytes] | None = None,
    additions: dict[str, bytes] | None = None,
) -> bytes:
    replacement_values = {**(replacements or {}), **(additions or {})}
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(source), mode="r") as source_archive,
        zipfile.ZipFile(output, mode="w") as target_archive,
    ):
        existing_names = set(source_archive.namelist())
        for info in source_archive.infolist():
            payload = replacement_values.get(info.filename, source_archive.read(info))
            target_archive.writestr(info, payload)
        for name, payload in (additions or {}).items():
            if name not in existing_names:
                target_archive.writestr(name, payload)
    return output.getvalue()


def _xlsx_member(source: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(source), mode="r") as archive:
        return archive.read(name)


def test_json_csv_and_xlsx_produce_equivalent_person_inputs() -> None:
    parser = TeiEquivalentPersonRegisterParser()
    record = _source_record()

    [json_person] = parser.iter_json(
        io.BytesIO(_json_source([record])),
        source_member_name="register.json",
    )
    [csv_person] = parser.iter_csv(
        io.BytesIO(b"\xef\xbb\xbf" + _csv_source([record])),
        source_member_name="register.csv",
    )
    [xlsx_person] = parser.iter_xlsx(
        io.BytesIO(_xlsx_source([record])),
        source_member_name="register.xlsx",
    )

    assert json_person.person == csv_person.person == xlsx_person.person == _expected_person()
    assert json_person.source_record_locator == "row:1"
    assert csv_person.source_record_locator == xlsx_person.source_record_locator == "row:2"
    assert json_person.source_member_name == "register.json"
    assert csv_person.source_member_name == "register.csv"
    assert xlsx_person.source_member_name == "register.xlsx"


def test_json_rejects_duplicate_object_keys() -> None:
    source = b'[{"xml:id":"p1","xml:id":"p2"}]'

    with pytest.raises(TabularImportError, match="duplicate object key"):
        list(TeiEquivalentPersonRegisterParser().iter_json(io.BytesIO(source)))


def test_json_rejects_oversized_integer_as_a_permanent_format_error() -> None:
    source = b'[{"xml:id":' + (b"9" * 5_000) + b"}]"

    with pytest.raises(TabularImportError, match="integer exceeding the digit limit"):
        list(TeiEquivalentPersonRegisterParser().iter_json(io.BytesIO(source)))


@pytest.mark.parametrize(
    ("document", "diagnostic"),
    [
        ({}, "top-level array"),
        ([{"xml:id": "p1"}], "object fields do not match"),
        ([{**_source_record(), "unknown": "value"}], "object fields do not match"),
        ([{**_source_record(), "birth": 1810}], "must be a string or null"),
    ],
)
def test_json_rejects_wrong_shapes(document: object, diagnostic: str) -> None:
    with pytest.raises(TabularImportError, match=diagnostic):
        list(
            TeiEquivalentPersonRegisterParser().iter_json(io.BytesIO(json.dumps(document).encode()))
        )


def test_json_rejects_duplicate_person_ids_without_echoing_the_value() -> None:
    records = [_source_record(), _source_record()]

    with pytest.raises(TabularImportError, match=r"row:2.*duplicated") as caught:
        list(TeiEquivalentPersonRegisterParser().iter_json(io.BytesIO(_json_source(records))))

    assert "p1" not in str(caught.value)


def test_json_enforces_byte_record_node_and_depth_limits() -> None:
    record = _source_record()

    with pytest.raises(TabularImportError, match="byte-size limit"):
        list(
            TeiEquivalentPersonRegisterParser(TabularImportPolicy(max_source_bytes=2)).iter_json(
                io.BytesIO(_json_source([record]))
            )
        )
    with pytest.raises(TabularImportError, match="record-count limit"):
        list(
            TeiEquivalentPersonRegisterParser(TabularImportPolicy(max_records=1)).iter_json(
                io.BytesIO(_json_source([record, record]))
            )
        )
    with pytest.raises(TabularImportError, match="node-count limit"):
        list(
            TeiEquivalentPersonRegisterParser(TabularImportPolicy(max_json_nodes=2)).iter_json(
                io.BytesIO(_json_source([record]))
            )
        )
    with pytest.raises(TabularImportError, match="nesting-depth limit"):
        list(
            TeiEquivalentPersonRegisterParser(TabularImportPolicy(max_json_depth=2)).iter_json(
                io.BytesIO(_json_source([record]))
            )
        )


def test_name_forms_require_one_regular_form_and_preserve_repeated_forenames() -> None:
    record = _source_record()
    record["persName"] = [{"type": "alt", "surname": "Sample", "forename": ["Anna", "Marie"]}]

    with pytest.raises(TabularImportError, match="exactly one regular form"):
        list(TeiEquivalentPersonRegisterParser().iter_json(io.BytesIO(_json_source([record]))))


def test_identifier_normalization_rejects_duplicate_schemes() -> None:
    record = _source_record()
    record["idno"] = [
        {"type": "gnd", "value": "123456789"},
        {"type": "uri", "value": "https://d-nb.info/gnd/987654321"},
    ]

    with pytest.raises(TabularImportError, match="duplicate normalized identifier schemes"):
        list(TeiEquivalentPersonRegisterParser().iter_json(io.BytesIO(_json_source([record]))))


def test_identifier_type_errors_include_only_the_safe_record_location() -> None:
    record = _source_record()
    record["idno"] = [{"type": "NOT SAFE!", "value": "secret-value"}]

    with pytest.raises(TabularImportError, match=r"row:1.*idno\[0\].*type is invalid") as caught:
        list(TeiEquivalentPersonRegisterParser().iter_json(io.BytesIO(_json_source([record]))))

    assert "NOT SAFE" not in str(caught.value)
    assert "secret-value" not in str(caught.value)


@pytest.mark.parametrize(
    ("header", "diagnostic"),
    [
        ([*TEI_EQUIVALENT_HEADERS[:-1], "note"], "duplicate columns"),
        ([*TEI_EQUIVALENT_HEADERS[:-1], "unknown"], "unknown columns"),
        (list(TEI_EQUIVALENT_HEADERS[:-1]), "missing required columns"),
        (
            [TEI_EQUIVALENT_HEADERS[1], TEI_EQUIVALENT_HEADERS[0], *TEI_EQUIVALENT_HEADERS[2:]],
            "required order",
        ),
    ],
)
def test_csv_requires_the_exact_header(header: list[str], diagnostic: str) -> None:
    output = io.StringIO(newline="")
    csv.writer(output).writerow(header)

    with pytest.raises(TabularImportError, match=diagnostic):
        list(TeiEquivalentPersonRegisterParser().iter_csv(io.BytesIO(output.getvalue().encode())))


def test_csv_rejects_bad_encoding_malformed_rows_and_oversized_cells() -> None:
    parser = TeiEquivalentPersonRegisterParser()
    with pytest.raises(TabularImportError, match="UTF-8"):
        list(parser.iter_csv(io.BytesIO(b"\xff")))

    wrong_width = ",".join(TEI_EQUIVALENT_HEADERS).encode() + b"\r\np1,[]\r\n"
    with pytest.raises(TabularImportError, match="wrong number of columns"):
        list(parser.iter_csv(io.BytesIO(wrong_width)))

    with pytest.raises(TabularImportError, match="byte limit"):
        list(
            TeiEquivalentPersonRegisterParser(TabularImportPolicy(max_cell_bytes=3)).iter_csv(
                io.BytesIO(_csv_source([_source_record()]))
            )
        )


def test_cell_limit_counts_utf8_bytes_instead_of_unicode_characters() -> None:
    record: dict[str, object] = {
        "xml:id": "p1",
        "persName": [{"type": "reg", "surname": "A", "forename": []}],
        "birth": None,
        "death": None,
        "event": [],
        "note": "äääää",
        "idno": [],
    }

    with pytest.raises(TabularImportError, match=r"note.*byte limit"):
        list(
            TeiEquivalentPersonRegisterParser(TabularImportPolicy(max_cell_bytes=9)).iter_json(
                io.BytesIO(_json_source([record]))
            )
        )


def test_json_and_csv_reject_u0000_before_persistence() -> None:
    record = _source_record()
    record["note"] = "unsafe\x00text"

    with pytest.raises(TabularImportError, match=r"U\+0000"):
        list(TeiEquivalentPersonRegisterParser().iter_json(io.BytesIO(_json_source([record]))))
    with pytest.raises(TabularImportError, match=r"U\+0000"):
        list(TeiEquivalentPersonRegisterParser().iter_csv(io.BytesIO(_csv_source([record]))))


def test_csv_uses_configured_cell_limit_above_python_implicit_default() -> None:
    previous_limit = csv.field_size_limit()
    csv.field_size_limit(64)
    try:
        [imported] = TeiEquivalentPersonRegisterParser(
            TabularImportPolicy(max_cell_bytes=100_000)
        ).iter_csv(io.BytesIO(_csv_source([_source_record()])))
        assert csv.field_size_limit() == 64
    finally:
        csv.field_size_limit(previous_limit)

    assert imported.person.tei_id == "p1"


class _UnreadableSource(io.BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        del size
        raise OSError("simulated read failure")


def test_source_read_failures_are_distinguished() -> None:
    with pytest.raises(TabularSourceReadError, match="could not be read"):
        list(TeiEquivalentPersonRegisterParser().iter_json(_UnreadableSource()))


@pytest.mark.parametrize(
    ("mutate", "diagnostic"),
    [
        (lambda _workbook, sheet: setattr(sheet["C2"], "value", 1810), "must be strings"),
        (lambda _workbook, sheet: setattr(sheet["C2"], "value", "=1+1"), "formula cells"),
        (lambda _workbook, sheet: sheet.merge_cells("A2:B2"), "merged cells"),
        (
            lambda workbook, _sheet: setattr(workbook.create_sheet("extra")["A1"], "value", "data"),
            "outside the persons worksheet",
        ),
        (_hide_persons_worksheet, "must be visible"),
    ],
)
def test_xlsx_rejects_ambiguous_or_coerced_workbook_content(
    mutate: Callable[[object, object], None],
    diagnostic: str,
) -> None:
    source = _xlsx_source([_source_record()], mutate=mutate)

    with pytest.raises(TabularImportError, match=diagnostic):
        list(TeiEquivalentPersonRegisterParser().iter_xlsx(io.BytesIO(source)))


def test_xlsx_rejects_non_regular_container_members() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w") as archive:
        info = zipfile.ZipInfo("xl/workbook.xml")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target")

    with pytest.raises(TabularImportError, match="non-regular archive member"):
        list(TeiEquivalentPersonRegisterParser().iter_xlsx(io.BytesIO(output.getvalue())))


def test_xlsx_wraps_malformed_workbook_xml() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w") as archive:
        archive.writestr("[Content_Types].xml", b"not XML")

    with pytest.raises(TabularImportError, match="workbook could not be decoded"):
        list(TeiEquivalentPersonRegisterParser().iter_xlsx(io.BytesIO(output.getvalue())))


def test_xlsx_rejects_macro_and_external_link_entries() -> None:
    original = _xlsx_source([_source_record()])
    for additions, diagnostic in [
        ({"xl/vbaProject.bin": b"unsafe"}, "macros"),
        ({"xl/macrosheets/sheet1.xml": b"<worksheet/>"}, "macros"),
        ({"xl/externalLinks/externalLink1.xml": b"unsafe"}, "external links"),
        (
            {
                "xl/worksheets/_rels/sheet1.xml.rels": (
                    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                    b'2006/relationships"><Relationship Id="rId1" Type="external" '
                    b'Target="https://example.invalid" TargetMode="Extern&#97;l"/>'
                    b"</Relationships>"
                )
            },
            "external links",
        ),
    ]:
        source = _rewrite_zip_members(original, additions=additions)

        with pytest.raises(TabularImportError, match=diagnostic):
            list(TeiEquivalentPersonRegisterParser().iter_xlsx(io.BytesIO(source)))


def test_xlsx_rejects_vba_content_type_without_trusting_the_part_name() -> None:
    original = _xlsx_source([_source_record()])
    content_types = _xlsx_member(original, "[Content_Types].xml")
    replacement = content_types.replace(
        b"</Types>",
        (
            b'<Override PartName="/xl/custom.xml" '
            b'ContentType="application/vnd.ms-office.vbaProject"/></Types>'
        ),
    )
    assert replacement != content_types
    source = _rewrite_zip_members(
        original,
        replacements={"[Content_Types].xml": replacement},
        additions={"xl/custom.xml": b"unsafe"},
    )

    with pytest.raises(TabularImportError, match="macros and dialog sheets"):
        list(TeiEquivalentPersonRegisterParser().iter_xlsx(io.BytesIO(source)))


def test_xlsx_rejects_oversized_dimension_before_loading_openpyxl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _xlsx_source([_source_record()])
    worksheet = _xlsx_member(original, "xl/worksheets/sheet1.xml")
    oversized = re.sub(
        rb'<dimension ref="[^"]+"\s*/>',
        b'<dimension ref="A1:XFD1048576"/>',
        worksheet,
        count=1,
    )
    assert oversized != worksheet
    source = _rewrite_zip_members(
        original,
        replacements={"xl/worksheets/sheet1.xml": oversized},
    )

    def fail_if_loaded(name: str, package: str | None = None) -> object:
        del package
        if name == "openpyxl":
            raise AssertionError("openpyxl must not load an oversized worksheet")
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(importlib, "import_module", fail_if_loaded)

    with pytest.raises(TabularImportError, match="worksheet-row limit"):
        list(TeiEquivalentPersonRegisterParser().iter_xlsx(io.BytesIO(source)))


def test_xlsx_streams_workbook_and_accepts_a_bounded_sheet_without_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _xlsx_source([_source_record()])
    worksheet = _xlsx_member(original, "xl/worksheets/sheet1.xml")
    without_dimension = re.sub(
        rb'<dimension ref="[^"]+"\s*/>',
        b"",
        worksheet,
        count=1,
    )
    assert without_dimension != worksheet
    source = _rewrite_zip_members(
        original,
        replacements={"xl/worksheets/sheet1.xml": without_dimension},
    )
    real_load_workbook = openpyxl.load_workbook
    observed_read_only: list[bool] = []

    def tracking_load_workbook(filename: object, **kwargs: object) -> object:
        observed_read_only.append(kwargs.get("read_only") is True)
        return real_load_workbook(filename, **kwargs)

    monkeypatch.setattr(openpyxl, "load_workbook", tracking_load_workbook)

    [imported] = TeiEquivalentPersonRegisterParser().iter_xlsx(io.BytesIO(source))

    assert imported.person == _expected_person()
    assert observed_read_only == [True]


def test_xlsx_preflights_hostile_declared_entry_count_before_zipfile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = bytearray(_xlsx_source([_source_record()]))
    eocd_offset = source.rfind(b"PK\x05\x06")
    assert eocd_offset >= 0
    hostile_count = TabularImportPolicy().max_xlsx_archive_members + 1
    struct.pack_into("<HH", source, eocd_offset + 8, hostile_count, hostile_count)

    def fail_if_opened(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ZipFile must not materialize a hostile directory")

    monkeypatch.setattr(zipfile, "ZipFile", fail_if_opened)

    with pytest.raises(TabularImportError, match="archive-member limit"):
        list(TeiEquivalentPersonRegisterParser().iter_xlsx(io.BytesIO(source)))
