"""Strict TEI-equivalent JSON, CSV, and XLSX person-register ingestion."""

from __future__ import annotations

import csv
import importlib
import io
import json
import math
import re
import stat
import sys
import threading
import unicodedata
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import BinaryIO, NoReturn, Protocol, cast

from lxml import etree
from pydantic import ValidationError

from gendertagger.ingestion.authority import (
    AuthorityIdentifierError,
    add_external_identifier,
)
from gendertagger.ingestion.zip_safety import (
    ZipPreflightError,
    ZipPreflightErrorCode,
    preflight_zip_directory,
)
from gendertagger.models.person import (
    ImportedPerson,
    PersonEvent,
    PersonInput,
    PersonNameForm,
    PersonNameType,
)
from gendertagger.models.project import TabularImportProfile

TABULAR_PERSON_PARSER_VERSION = "tabular_person_parser_v1"
TEI_EQUIVALENT_PERSON_REGISTER_PROFILE = TabularImportProfile.tei_equivalent_person_register_v1
TEI_EQUIVALENT_HEADERS = (
    "xml:id",
    "persName",
    "birth",
    "death",
    "event",
    "note",
    "idno",
)

_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_READ_BUFFER_BYTES = 64 * 1024
_JSON_ARRAY_COLUMNS = frozenset({"persName", "event", "idno"})
_OPTIONAL_SCALAR_COLUMNS = frozenset({"birth", "death", "note"})
_OOXML_WORKSHEET_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)
_OOXML_ACTIVE_CONTENT_MARKERS = ("macro", "vba", "dialogsheet")
_XLSX_CELL_OR_RANGE_PATTERN = re.compile(
    r"^\$?(?P<start_column>[A-Za-z]{1,3})\$?(?P<start_row>[1-9][0-9]*)"
    r"(?::\$?(?P<end_column>[A-Za-z]{1,3})\$?(?P<end_row>[1-9][0-9]*))?$"
)
_MAX_JSON_INTEGER_DIGITS = 1_000
# Bounds row-number strings before int() conversion.
_MAX_XLSX_ROW_DIGITS = 10
_ASCII_CONTROL_CHARACTERS = frozenset(map(chr, [*range(32), 127]))
_CSV_FIELD_SIZE_LIMIT_LOCK = threading.RLock()


class TabularImportError(ValueError):
    """Raised with a bounded, source-safe tabular validation diagnostic."""


class TabularSourceReadError(TabularImportError):
    """Raised when infrastructure prevents reading a tabular source."""


class TabularDependencyError(TabularSourceReadError):
    """Raised when an optional format dependency is not installed."""


@dataclass(frozen=True, slots=True)
class TabularImportPolicy:
    """Independent resource ceilings for one untrusted tabular source."""

    max_source_bytes: int = 25 * 1024 * 1024
    max_records: int = 100_000
    max_cell_bytes: int = 1_000_000
    max_json_depth: int = 20
    max_json_nodes: int = 1_000_000
    max_xlsx_archive_members: int = 1_000
    max_xlsx_member_expanded_bytes: int = 25 * 1024 * 1024
    max_xlsx_total_expanded_bytes: int = 100 * 1024 * 1024
    max_xlsx_compression_ratio: float = 100.0

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_source_bytes,
            self.max_records,
            self.max_cell_bytes,
            self.max_json_depth,
            self.max_json_nodes,
            self.max_xlsx_archive_members,
            self.max_xlsx_member_expanded_bytes,
            self.max_xlsx_total_expanded_bytes,
        )
        if any(limit <= 0 for limit in integer_limits):
            msg = "tabular import limits must be positive"
            raise ValueError(msg)
        if (
            not math.isfinite(self.max_xlsx_compression_ratio)
            or self.max_xlsx_compression_ratio <= 0
        ):
            msg = "max_xlsx_compression_ratio must be finite and positive"
            raise ValueError(msg)


class _Cell(Protocol):
    value: object
    data_type: str


class _Worksheet(Protocol):
    title: str
    sheet_state: str
    max_row: int
    max_column: int

    def iter_rows(
        self,
        *,
        min_row: int | None = None,
        max_row: int | None = None,
    ) -> Iterator[Sequence[_Cell]]: ...


class _Workbook(Protocol):
    sheetnames: list[str]
    worksheets: list[_Worksheet]

    def __getitem__(self, name: str) -> _Worksheet: ...

    def close(self) -> None: ...


def version_for_profile(profile: TabularImportProfile) -> str:
    """Return the implementation version for one supported tabular profile."""
    versions: dict[TabularImportProfile, str] = {
        TEI_EQUIVALENT_PERSON_REGISTER_PROFILE: TABULAR_PERSON_PARSER_VERSION,
    }
    try:
        return versions[profile]
    except KeyError as error:
        msg = f"unsupported tabular import profile {profile!r}"
        raise ValueError(msg) from error


class TeiEquivalentPersonRegisterParser:
    """Parse strict TEI-equivalent rows into canonical person inputs."""

    profile = TEI_EQUIVALENT_PERSON_REGISTER_PROFILE

    def __init__(self, policy: TabularImportPolicy | None = None) -> None:
        self._policy = policy or TabularImportPolicy()

    def iter_json(
        self,
        source: BinaryIO,
        *,
        source_member_name: str = "source.json",
    ) -> Iterator[ImportedPerson]:
        """Yield people from one bounded UTF-8 JSON array."""
        payload = self._read_source(source)
        document = self._decode_json_document(payload, context="JSON source")
        if not isinstance(document, list):
            msg = "JSON source must contain one top-level array"
            raise TabularImportError(msg)
        self._validate_json_limits(document)
        if len(document) > self._policy.max_records:
            msg = "JSON source exceeds the record-count limit"
            raise TabularImportError(msg)

        yield from self._iter_records(
            document,
            source_member_name=source_member_name,
            first_record_number=1,
        )

    def iter_csv(
        self,
        source: BinaryIO,
        *,
        source_member_name: str = "source.csv",
    ) -> Iterator[ImportedPerson]:
        """Yield people from one bounded fixed-dialect UTF-8 CSV table."""
        payload = self._read_source(source)
        text = self._decode_utf8(payload, source_type="CSV")
        reader = csv.reader(
            io.StringIO(text, newline=""),
            delimiter=",",
            quotechar='"',
            doublequote=True,
            skipinitialspace=False,
            strict=True,
        )
        try:
            header = _next_csv_row(
                reader,
                max_field_characters=self._policy.max_source_bytes,
            )
        except StopIteration as error:
            msg = "CSV source requires a header row"
            raise TabularImportError(msg) from error
        except csv.Error as error:
            msg = "CSV header is malformed"
            raise TabularImportError(msg) from error
        self._validate_header(header, source_type="CSV")

        seen_tei_ids: set[str] = set()
        record_count = 0
        try:
            row_number = 1
            while True:
                try:
                    row = _next_csv_row(
                        reader,
                        max_field_characters=self._policy.max_source_bytes,
                    )
                except StopIteration:
                    break
                row_number += 1
                if not row or all(value == "" for value in row):
                    continue
                record_count += 1
                if record_count > self._policy.max_records:
                    msg = "CSV source exceeds the record-count limit"
                    raise TabularImportError(msg)
                if len(row) != len(TEI_EQUIVALENT_HEADERS):
                    msg = f"record row:{row_number} has the wrong number of columns"
                    raise TabularImportError(msg)
                self._validate_cell_sizes(row, locator=f"row:{row_number}")
                record = self._csv_like_record(row, locator=f"row:{row_number}")
                yield self._imported_person(
                    record,
                    source_member_name=source_member_name,
                    source_record_locator=f"row:{row_number}",
                    seen_tei_ids=seen_tei_ids,
                )
        except csv.Error as error:
            msg = f"CSV source is malformed near row:{reader.line_num}"
            raise TabularImportError(msg) from error

    def iter_xlsx(
        self,
        source: BinaryIO,
        *,
        source_member_name: str = "source.xlsx",
    ) -> Iterator[ImportedPerson]:
        """Yield people from one bounded, coercion-free XLSX worksheet."""
        payload = self._read_source(source)
        self._validate_xlsx_container(payload)
        workbook = self._load_xlsx(payload)
        try:
            worksheet = self._persons_worksheet(workbook)
            self._validate_workbook_sheets(workbook, persons=worksheet)
            rows = worksheet.iter_rows()
            try:
                header_cells = next(rows)
            except StopIteration as error:
                msg = "XLSX persons worksheet requires a header row"
                raise TabularImportError(msg) from error
            header = self._xlsx_string_row(header_cells, row_number=1)
            self._validate_header(header, source_type="XLSX")

            seen_tei_ids: set[str] = set()
            record_count = 0
            for row_number, cells in enumerate(rows, start=2):
                values = self._xlsx_string_row(cells, row_number=row_number)
                if not values or all(value == "" for value in values):
                    continue
                record_count += 1
                if record_count > self._policy.max_records:
                    msg = "XLSX source exceeds the record-count limit"
                    raise TabularImportError(msg)
                if len(values) != len(TEI_EQUIVALENT_HEADERS):
                    msg = f"record row:{row_number} has the wrong number of columns"
                    raise TabularImportError(msg)
                self._validate_cell_sizes(values, locator=f"row:{row_number}")
                record = self._csv_like_record(values, locator=f"row:{row_number}")
                yield self._imported_person(
                    record,
                    source_member_name=source_member_name,
                    source_record_locator=f"row:{row_number}",
                    seen_tei_ids=seen_tei_ids,
                )
        finally:
            workbook.close()

    def _iter_records(
        self,
        records: Sequence[object],
        *,
        source_member_name: str,
        first_record_number: int,
    ) -> Iterator[ImportedPerson]:
        seen_tei_ids: set[str] = set()
        for record_number, record in enumerate(records, start=first_record_number):
            locator = f"row:{record_number}"
            yield self._imported_person(
                record,
                source_member_name=source_member_name,
                source_record_locator=locator,
                seen_tei_ids=seen_tei_ids,
            )

    def _imported_person(
        self,
        raw_record: object,
        *,
        source_member_name: str,
        source_record_locator: str,
        seen_tei_ids: set[str],
    ) -> ImportedPerson:
        record = self._exact_object(
            raw_record,
            required_keys=TEI_EQUIVALENT_HEADERS,
            optional_keys=(),
            locator=source_record_locator,
            column=None,
        )
        tei_id = self._required_string(
            record["xml:id"],
            locator=source_record_locator,
            column="xml:id",
        )
        if tei_id in seen_tei_ids:
            self._raise_record_error(source_record_locator, "xml:id", "value is duplicated")
        seen_tei_ids.add(tei_id)

        name_forms = self._name_forms(record["persName"], locator=source_record_locator)
        regular_form = next(
            name_form for name_form in name_forms if name_form.type is PersonNameType.regular
        )
        alt_names = [
            name_form.projected_text()
            for name_form in name_forms
            if name_form.type is PersonNameType.alternative
        ]
        events = self._events(record["event"], locator=source_record_locator)
        gnd_id, external_ids = self._external_ids(
            record["idno"],
            locator=source_record_locator,
        )
        try:
            person = PersonInput(
                tei_id=tei_id,
                surname=regular_form.surname or regular_form.name,
                forenames=regular_form.forenames,
                birth=self._optional_string(
                    record["birth"],
                    locator=source_record_locator,
                    column="birth",
                ),
                death=self._optional_string(
                    record["death"],
                    locator=source_record_locator,
                    column="death",
                ),
                note=self._optional_string(
                    record["note"],
                    locator=source_record_locator,
                    column="note",
                ),
                events=events,
                alt_names=alt_names,
                name_forms=name_forms,
                gnd_id=gnd_id,
                external_ids=external_ids,
            )
            return ImportedPerson(
                person=person,
                source_member_name=source_member_name,
                source_record_locator=source_record_locator,
            )
        except ValidationError as error:
            msg = f"record {source_record_locator} violates the person input contract"
            raise TabularImportError(msg) from error

    def _name_forms(self, value: object, *, locator: str) -> list[PersonNameForm]:
        forms = self._required_array(value, locator=locator, column="persName")
        name_forms: list[PersonNameForm] = []
        for index, raw_form in enumerate(forms):
            form_locator = f"persName[{index}]"
            mapping = self._mapping(raw_form, locator=locator, column=form_locator)
            keys = set(mapping)
            common_keys = {"type", "subtype"}
            if "name" in mapping:
                required = {"type", "name"}
                allowed = common_keys | {"name"}
                representation = "unstructured"
            else:
                required = {"type", "forename"}
                allowed = common_keys | {"surname", "forename"}
                representation = "structured"
            if not required.issubset(keys) or not keys.issubset(allowed):
                self._raise_record_error(locator, form_locator, "object shape is invalid")
            name_type = self._required_string(
                mapping["type"],
                locator=locator,
                column=f"{form_locator}.type",
            )
            subtype = self._optional_string(
                mapping.get("subtype"),
                locator=locator,
                column=f"{form_locator}.subtype",
            )
            try:
                if representation == "unstructured":
                    name_form = PersonNameForm(
                        type=PersonNameType(name_type),
                        subtype=subtype,
                        name=self._required_string(
                            mapping["name"],
                            locator=locator,
                            column=f"{form_locator}.name",
                        ),
                    )
                else:
                    surname = self._optional_string(
                        mapping.get("surname"),
                        locator=locator,
                        column=f"{form_locator}.surname",
                    )
                    forenames = [
                        self._required_string(
                            forename,
                            locator=locator,
                            column=f"{form_locator}.forename[{forename_index}]",
                        )
                        for forename_index, forename in enumerate(
                            self._required_array(
                                mapping["forename"],
                                locator=locator,
                                column=f"{form_locator}.forename",
                            )
                        )
                    ]
                    name_form = PersonNameForm(
                        type=PersonNameType(name_type),
                        subtype=subtype,
                        surname=surname,
                        forenames=forenames,
                    )
            except (ValidationError, ValueError) as error:
                self._raise_record_error(locator, form_locator, "name form is invalid", cause=error)
            name_forms.append(name_form)

        if sum(form.type is PersonNameType.regular for form in name_forms) != 1:
            self._raise_record_error(locator, "persName", "requires exactly one regular form")
        return name_forms

    def _events(self, value: object, *, locator: str) -> list[PersonEvent]:
        events: list[PersonEvent] = []
        for index, raw_event in enumerate(
            self._required_array(value, locator=locator, column="event")
        ):
            event_locator = f"event[{index}]"
            mapping = self._exact_object(
                raw_event,
                required_keys=("type",),
                optional_keys=("when", "note"),
                locator=locator,
                column=event_locator,
            )
            try:
                events.append(
                    PersonEvent(
                        type=self._required_string(
                            mapping["type"],
                            locator=locator,
                            column=f"{event_locator}.type",
                        ),
                        when=self._optional_string(
                            mapping.get("when"),
                            locator=locator,
                            column=f"{event_locator}.when",
                        ),
                        note=self._optional_string(
                            mapping.get("note"),
                            locator=locator,
                            column=f"{event_locator}.note",
                        ),
                    )
                )
            except ValidationError as error:
                self._raise_record_error(locator, event_locator, "event is invalid", cause=error)
        return events

    def _external_ids(
        self,
        value: object,
        *,
        locator: str,
    ) -> tuple[str | None, dict[str, str]]:
        identifiers: dict[str, str] = {}
        for index, raw_identifier in enumerate(
            self._required_array(value, locator=locator, column="idno")
        ):
            identifier_locator = f"idno[{index}]"
            mapping = self._exact_object(
                raw_identifier,
                required_keys=("type", "value"),
                optional_keys=(),
                locator=locator,
                column=identifier_locator,
            )
            identifier_type = self._required_string(
                mapping["type"],
                locator=locator,
                column=f"{identifier_locator}.type",
            )
            identifier_value = self._required_string(
                mapping["value"],
                locator=locator,
                column=f"{identifier_locator}.value",
            )
            try:
                add_external_identifier(
                    identifiers,
                    identifier_type=identifier_type,
                    value=identifier_value,
                )
            except AuthorityIdentifierError as error:
                self._raise_record_error(
                    locator,
                    identifier_locator,
                    str(error),
                    cause=error,
                )

        gnd_id = identifiers.pop("gnd", None)
        return gnd_id, identifiers

    def _csv_like_record(self, row: Sequence[str], *, locator: str) -> dict[str, object]:
        record: dict[str, object] = {}
        for header, cell in zip(TEI_EQUIVALENT_HEADERS, row, strict=True):
            if header in _JSON_ARRAY_COLUMNS:
                if cell == "":
                    self._raise_record_error(locator, header, "requires a JSON array")
                decoded = self._decode_json_text(
                    cell, context=f"record {locator} column {header!r}"
                )
                self._validate_json_limits(decoded)
                if not isinstance(decoded, list):
                    self._raise_record_error(locator, header, "must contain a JSON array")
                record[header] = decoded
            else:
                record[header] = None if header in _OPTIONAL_SCALAR_COLUMNS and cell == "" else cell
        return record

    def _read_source(self, source: BinaryIO) -> bytes:
        chunks: list[bytes] = []
        byte_count = 0
        try:
            while True:
                remaining = self._policy.max_source_bytes - byte_count
                raw_chunk = cast(object, source.read(min(_READ_BUFFER_BYTES, remaining + 1)))
                if raw_chunk is None:
                    msg = "tabular source did not return bytes"
                    raise TabularSourceReadError(msg)
                if not isinstance(raw_chunk, bytes):
                    msg = "tabular source must be binary"
                    raise TabularSourceReadError(msg)
                chunk = raw_chunk
                if not chunk:
                    break
                chunks.append(chunk)
                byte_count += len(chunk)
                if byte_count > self._policy.max_source_bytes:
                    msg = "tabular source exceeds the byte-size limit"
                    raise TabularImportError(msg)
        except OSError as error:
            msg = "tabular source could not be read"
            raise TabularSourceReadError(msg) from error
        return b"".join(chunks)

    def _decode_json_document(self, payload: bytes, *, context: str) -> object:
        text = self._decode_utf8(payload, source_type="JSON")
        return self._decode_json_text(text, context=context)

    @staticmethod
    def _decode_utf8(payload: bytes, *, source_type: str) -> str:
        try:
            return payload.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            msg = f"{source_type} source must use UTF-8"
            raise TabularImportError(msg) from error

    @staticmethod
    def _decode_json_text(text: str, *, context: str) -> object:
        try:
            return json.loads(
                text,
                object_pairs_hook=_object_without_duplicate_keys,
                parse_constant=_reject_json_constant,
                parse_int=_parse_bounded_json_integer,
            )
        except _DuplicateJsonKeyError as error:
            msg = f"{context} contains a duplicate object key"
            raise TabularImportError(msg) from error
        except _OversizedJsonIntegerError as error:
            msg = f"{context} contains an integer exceeding the digit limit"
            raise TabularImportError(msg) from error
        except (json.JSONDecodeError, RecursionError) as error:
            if isinstance(error, json.JSONDecodeError):
                msg = f"{context} is invalid near line {error.lineno}, column {error.colno}"
            else:
                msg = f"{context} exceeds the supported nesting depth"
            raise TabularImportError(msg) from error
        except _InvalidJsonConstantError as error:
            msg = f"{context} contains a non-finite numeric value"
            raise TabularImportError(msg) from error

    def _validate_json_limits(self, value: object) -> None:
        stack: list[tuple[object, int]] = [(value, 1)]
        node_count = 0
        while stack:
            current, depth = stack.pop()
            node_count += 1
            if node_count > self._policy.max_json_nodes:
                msg = "JSON value exceeds the node-count limit"
                raise TabularImportError(msg)
            if depth > self._policy.max_json_depth:
                msg = "JSON value exceeds the nesting-depth limit"
                raise TabularImportError(msg)
            if isinstance(current, Mapping):
                stack.extend((item, depth + 1) for item in current.values())
            elif isinstance(current, list):
                stack.extend((item, depth + 1) for item in current)

    def _validate_header(self, header: Sequence[str], *, source_type: str) -> None:
        self._validate_cell_sizes(header, locator="header")
        if len(header) != len(set(header)):
            msg = f"{source_type} header contains duplicate columns"
            raise TabularImportError(msg)
        header_set = set(header)
        expected_set = set(TEI_EQUIVALENT_HEADERS)
        if header_set - expected_set:
            msg = f"{source_type} header contains unknown columns"
            raise TabularImportError(msg)
        if expected_set - header_set:
            msg = f"{source_type} header is missing required columns"
            raise TabularImportError(msg)
        if tuple(header) != TEI_EQUIVALENT_HEADERS:
            msg = f"{source_type} columns are not in the required order"
            raise TabularImportError(msg)

    def _validate_cell_sizes(self, values: Sequence[str], *, locator: str) -> None:
        if any("\x00" in value for value in values):
            msg = f"record {locator} contains U+0000 in a string value"
            raise TabularImportError(msg)
        if any(self._utf8_byte_size(value) > self._policy.max_cell_bytes for value in values):
            msg = f"record {locator} contains a cell exceeding the byte limit"
            raise TabularImportError(msg)

    def _validate_xlsx_container(self, payload: bytes) -> None:
        with self._open_xlsx_archive(payload) as archive:
            members = self._collect_xlsx_members(archive)

            content_types_member = members.get("[content_types].xml")
            if content_types_member is None:
                msg = "XLSX workbook could not be decoded"
                raise TabularImportError(msg)
            worksheet_parts = self._validate_xlsx_content_types(
                archive,
                content_types_member[1],
            )
            for folded_name, (_, info) in members.items():
                if folded_name.endswith(".rels"):
                    self._validate_xlsx_relationships(archive, info)
                if folded_name.startswith("xl/worksheets/") and folded_name.endswith(".xml"):
                    worksheet_parts.add(folded_name)
            for worksheet_part in worksheet_parts:
                member = members.get(worksheet_part)
                if member is None:
                    msg = "XLSX workbook could not be decoded"
                    raise TabularImportError(msg)
                self._validate_xlsx_worksheet_xml(archive, member[1])

    def _open_xlsx_archive(self, payload: bytes) -> zipfile.ZipFile:
        source = io.BytesIO(payload)
        try:
            preflight_zip_directory(
                source,
                max_entry_count=self._policy.max_xlsx_archive_members,
            )
        except ZipPreflightError as error:
            if error.code is ZipPreflightErrorCode.entry_count:
                msg = "XLSX source exceeds the archive-member limit"
            elif error.code is ZipPreflightErrorCode.metadata_size:
                msg = "XLSX source exceeds the archive-metadata limit"
            else:
                msg = "XLSX source is not a valid ZIP container"
            raise TabularImportError(msg) from error
        try:
            archive = zipfile.ZipFile(source, mode="r")
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as error:
            msg = "XLSX source is not a valid ZIP container"
            raise TabularImportError(msg) from error
        return archive

    def _collect_xlsx_members(
        self,
        archive: zipfile.ZipFile,
    ) -> dict[str, tuple[str, zipfile.ZipInfo]]:
        infos = archive.infolist()
        if len(infos) > self._policy.max_xlsx_archive_members:
            msg = "XLSX source exceeds the archive-member limit"
            raise TabularImportError(msg)
        normalized_names: set[str] = set()
        members: dict[str, tuple[str, zipfile.ZipInfo]] = {}
        total_expanded = 0
        for info in infos:
            normalized_name = _normalize_xlsx_member_name(info.filename)
            folded_name = unicodedata.normalize("NFC", normalized_name).casefold()
            if folded_name in normalized_names:
                msg = "XLSX source contains duplicate normalized archive names"
                raise TabularImportError(msg)
            normalized_names.add(folded_name)
            if info.flag_bits & 0x1:
                msg = "XLSX source contains an encrypted archive member"
                raise TabularImportError(msg)
            _require_regular_xlsx_member(info)
            if _is_active_xlsx_part(folded_name):
                msg = "XLSX macros are not supported"
                raise TabularImportError(msg)
            if folded_name.startswith("xl/externallinks/"):
                msg = "XLSX external links are not supported"
                raise TabularImportError(msg)
            if info.file_size > self._policy.max_xlsx_member_expanded_bytes:
                msg = "XLSX archive member exceeds the expanded-byte limit"
                raise TabularImportError(msg)
            total_expanded += info.file_size
            if total_expanded > self._policy.max_xlsx_total_expanded_bytes:
                msg = "XLSX source exceeds the total expanded-byte limit"
                raise TabularImportError(msg)
            if _compression_ratio(info.file_size, info.compress_size) > (
                self._policy.max_xlsx_compression_ratio
            ):
                msg = "XLSX source exceeds the compression-ratio limit"
                raise TabularImportError(msg)
            self._read_and_validate_xlsx_member(archive, info)
            members[folded_name] = (normalized_name, info)
        return members

    def _read_and_validate_xlsx_member(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
    ) -> None:
        expanded = 0
        try:
            with archive.open(info, mode="r") as member:
                while chunk := member.read(_READ_BUFFER_BYTES):
                    expanded += len(chunk)
                    if expanded > self._policy.max_xlsx_member_expanded_bytes:
                        msg = "XLSX archive member exceeds the expanded-byte limit"
                        raise TabularImportError(msg)
        except (NotImplementedError, RuntimeError, zipfile.BadZipFile) as error:
            msg = "XLSX archive member could not be decoded"
            raise TabularImportError(msg) from error
        if expanded != info.file_size:
            msg = "XLSX archive member size disagrees with its header"
            raise TabularImportError(msg)

    def _validate_xlsx_content_types(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
    ) -> set[str]:
        worksheet_parts: set[str] = set()
        for event, element in self._iter_xlsx_xml_member(archive, info):
            if event != "start" or _xml_local_name(element) not in {"Default", "Override"}:
                continue
            content_type = (element.get("ContentType") or "").strip().casefold()
            if any(marker in content_type for marker in _OOXML_ACTIVE_CONTENT_MARKERS):
                msg = "XLSX macros and dialog sheets are not supported"
                raise TabularImportError(msg)
            raw_part_name = (element.get("PartName") or "").lstrip("/")
            if raw_part_name:
                part_name = _normalize_xlsx_member_name(raw_part_name).casefold()
                if _is_active_xlsx_part(part_name):
                    msg = "XLSX macros and dialog sheets are not supported"
                    raise TabularImportError(msg)
                if content_type == _OOXML_WORKSHEET_CONTENT_TYPE:
                    worksheet_parts.add(part_name)
        return worksheet_parts

    def _validate_xlsx_relationships(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
    ) -> None:
        for event, element in self._iter_xlsx_xml_member(archive, info):
            if event != "start" or _xml_local_name(element) != "Relationship":
                continue
            target_mode = (element.get("TargetMode") or "").strip().casefold()
            if target_mode == "external":
                msg = "XLSX external links are not supported"
                raise TabularImportError(msg)

    def _validate_xlsx_worksheet_xml(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
    ) -> None:
        row_count = 0
        cells_in_row = 0
        max_rows = self._policy.max_records + 1
        max_columns = len(TEI_EQUIVALENT_HEADERS)
        for event, element in self._iter_xlsx_xml_member(archive, info):
            if event != "start":
                continue
            local_name = _xml_local_name(element)
            if local_name == "dimension":
                _validate_xlsx_reference(
                    element.get("ref") or "",
                    max_rows=max_rows,
                    max_columns=max_columns,
                    context="worksheet dimension",
                )
            elif local_name == "row":
                row_count += 1
                cells_in_row = 0
                if row_count > max_rows:
                    msg = "XLSX source exceeds the worksheet-row limit"
                    raise TabularImportError(msg)
                row_reference = element.get("r")
                if row_reference is not None:
                    _validate_xlsx_row_number(row_reference, max_rows=max_rows)
            elif local_name == "c":
                cells_in_row += 1
                if cells_in_row > max_columns:
                    msg = "XLSX source exceeds the worksheet-column limit"
                    raise TabularImportError(msg)
                cell_reference = element.get("r")
                if cell_reference is not None:
                    _validate_xlsx_reference(
                        cell_reference,
                        max_rows=max_rows,
                        max_columns=max_columns,
                        context="cell reference",
                    )
            elif local_name == "f":
                msg = "XLSX formula cells are not supported"
                raise TabularImportError(msg)
            elif local_name in {"mergeCells", "mergeCell"}:
                msg = "XLSX merged cells are not supported"
                raise TabularImportError(msg)
            elif local_name in {"hyperlinks", "hyperlink"}:
                msg = "XLSX external links are not supported"
                raise TabularImportError(msg)

    def _iter_xlsx_xml_member(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
    ) -> Iterator[tuple[str, etree._Element]]:
        try:
            with archive.open(info, mode="r") as member:
                yield from _iter_secure_ooxml_events(cast(BinaryIO, member))
        except TabularImportError:
            raise
        except (
            etree.XMLSyntaxError,
            NotImplementedError,
            RuntimeError,
            ValueError,
            zipfile.BadZipFile,
        ) as error:
            msg = "XLSX workbook could not be decoded"
            raise TabularImportError(msg) from error

    @staticmethod
    def _load_xlsx(payload: bytes) -> _Workbook:
        try:
            openpyxl = importlib.import_module("openpyxl")
        except ImportError as error:
            msg = "XLSX import requires the openpyxl dependency"
            raise TabularDependencyError(msg) from error
        load_workbook = cast(Callable[..., object], openpyxl.load_workbook)
        try:
            workbook = load_workbook(
                io.BytesIO(payload),
                read_only=True,
                data_only=False,
                keep_vba=False,
                keep_links=False,
            )
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, etree.XMLSyntaxError) as error:
            msg = "XLSX workbook could not be decoded"
            raise TabularImportError(msg) from error
        return cast(_Workbook, workbook)

    @staticmethod
    def _persons_worksheet(workbook: _Workbook) -> _Worksheet:
        if "persons" not in workbook.sheetnames:
            msg = "XLSX source requires a worksheet named 'persons'"
            raise TabularImportError(msg)
        worksheet = workbook["persons"]
        if worksheet.sheet_state != "visible":
            msg = "XLSX persons worksheet must be visible"
            raise TabularImportError(msg)
        return worksheet

    def _validate_workbook_sheets(
        self,
        workbook: _Workbook,
        *,
        persons: _Worksheet,
    ) -> None:
        for worksheet in workbook.worksheets:
            has_data = False
            for row_number, row in enumerate(worksheet.iter_rows(), start=1):
                if row_number > self._policy.max_records + 1:
                    msg = "XLSX source exceeds the worksheet-row limit"
                    raise TabularImportError(msg)
                if len(row) > len(TEI_EQUIVALENT_HEADERS):
                    msg = "XLSX source exceeds the worksheet-column limit"
                    raise TabularImportError(msg)
                for cell in row:
                    if cell.data_type == "f" or (
                        isinstance(cell.value, str) and cell.value.startswith("=")
                    ):
                        msg = "XLSX formula cells are not supported"
                        raise TabularImportError(msg)
                    if cell.value is not None:
                        has_data = True
                        if not isinstance(cell.value, str):
                            msg = "XLSX source values must be strings"
                            raise TabularImportError(msg)
                        if self._utf8_byte_size(cell.value) > self._policy.max_cell_bytes:
                            msg = "XLSX source contains a cell exceeding the byte limit"
                            raise TabularImportError(msg)
            if worksheet is not persons and has_data:
                msg = "XLSX source contains data outside the persons worksheet"
                raise TabularImportError(msg)

    @staticmethod
    def _xlsx_string_row(cells: Sequence[_Cell], *, row_number: int) -> list[str]:
        values: list[str] = []
        for cell in cells:
            if cell.value is None:
                values.append("")
                continue
            if not isinstance(cell.value, str):
                msg = f"record row:{row_number} contains a non-string XLSX value"
                raise TabularImportError(msg)
            values.append(cell.value)
        while values and values[-1] == "":
            values.pop()
        return values

    def _required_string(self, value: object, *, locator: str, column: str) -> str:
        if not isinstance(value, str) or not value.strip():
            self._raise_record_error(locator, column, "requires a non-blank string")
        if "\x00" in value:
            self._raise_record_error(locator, column, "must not contain U+0000")
        if self._utf8_byte_size(value) > self._policy.max_cell_bytes:
            self._raise_record_error(locator, column, "exceeds the byte limit")
        return value

    def _optional_string(
        self,
        value: object,
        *,
        locator: str,
        column: str,
    ) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            self._raise_record_error(locator, column, "must be a string or null")
        if "\x00" in value:
            self._raise_record_error(locator, column, "must not contain U+0000")
        if self._utf8_byte_size(value) > self._policy.max_cell_bytes:
            self._raise_record_error(locator, column, "exceeds the byte limit")
        return value

    @staticmethod
    def _utf8_byte_size(value: str) -> int:
        try:
            return len(value.encode("utf-8"))
        except UnicodeEncodeError as error:
            msg = "tabular source contains text that is not valid Unicode"
            raise TabularImportError(msg) from error

    def _required_array(self, value: object, *, locator: str, column: str) -> list[object]:
        if not isinstance(value, list):
            self._raise_record_error(locator, column, "requires an array")
        return value

    def _mapping(self, value: object, *, locator: str, column: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
            self._raise_record_error(locator, column, "requires an object")
        return cast(Mapping[str, object], value)

    def _exact_object(
        self,
        value: object,
        *,
        required_keys: Sequence[str],
        optional_keys: Sequence[str],
        locator: str,
        column: str | None,
    ) -> Mapping[str, object]:
        mapping = self._mapping(value, locator=locator, column=column or "record")
        keys = set(mapping)
        if not set(required_keys).issubset(keys) or not keys.issubset(
            set(required_keys) | set(optional_keys)
        ):
            self._raise_record_error(locator, column, "object fields do not match the profile")
        return mapping

    @staticmethod
    def _raise_record_error(
        locator: str,
        column: str | None,
        detail: str,
        *,
        cause: BaseException | None = None,
    ) -> NoReturn:
        location = f"record {locator}"
        if column is not None:
            location += f" column {column!r}"
        msg = f"{location}: {detail}"
        if cause is None:
            raise TabularImportError(msg)
        raise TabularImportError(msg) from cause


class _DuplicateJsonKeyError(ValueError):
    pass


class _InvalidJsonConstantError(ValueError):
    pass


class _OversizedJsonIntegerError(ValueError):
    pass


def _next_csv_row(
    reader: Iterator[list[str]],
    *,
    max_field_characters: int,
) -> list[str]:
    """Read one row under an explicit, briefly held global CSV field limit."""
    # csv.field_size_limit is process-global. Hold the lock only for the
    # synchronous next() call and restore the prior value before yielding any
    # imported record to application code.
    with _CSV_FIELD_SIZE_LIMIT_LOCK:
        previous_limit = csv.field_size_limit()
        csv.field_size_limit(min(max_field_characters, sys.maxsize))
        try:
            return next(reader)
        finally:
            csv.field_size_limit(previous_limit)


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError
        result[key] = value
    return result


def _reject_json_constant(_: str) -> object:
    raise _InvalidJsonConstantError


def _parse_bounded_json_integer(value: str) -> int:
    if len(value.removeprefix("-")) > _MAX_JSON_INTEGER_DIGITS:
        raise _OversizedJsonIntegerError
    return int(value)


def _iter_secure_ooxml_events(source: BinaryIO) -> Iterator[tuple[str, etree._Element]]:
    context = etree.iterparse(
        source,
        events=("start", "end"),
        load_dtd=False,
        no_network=True,
        resolve_entities=False,
        recover=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )
    root_seen = False
    for event, element in context:
        if not root_seen and event == "start":
            root_seen = True
            document = element.getroottree()
            if document.docinfo.internalDTD is not None or document.docinfo.externalDTD is not None:
                msg = "XLSX XML parts containing a DOCTYPE are not supported"
                raise TabularImportError(msg)
        yield event, element
        if event == "end":
            element.clear()
    if not root_seen:
        msg = "XLSX workbook contains an empty XML part"
        raise TabularImportError(msg)


def _xml_local_name(element: etree._Element) -> str:
    try:
        return etree.QName(element).localname
    except ValueError:
        return ""


def _is_active_xlsx_part(folded_name: str) -> bool:
    basename = folded_name.rsplit("/", maxsplit=1)[-1]
    return (
        basename.startswith("vba")
        or folded_name.startswith(("xl/macrosheets/", "xl/intlmacrosheets/", "xl/dialogsheets/"))
        or "macroenabled" in folded_name
    )


def _validate_xlsx_reference(
    reference: str,
    *,
    max_rows: int,
    max_columns: int,
    context: str,
) -> None:
    match = _XLSX_CELL_OR_RANGE_PATTERN.fullmatch(reference)
    if match is None:
        msg = f"XLSX {context} is invalid"
        raise TabularImportError(msg)
    row_values = [match.group("start_row"), match.group("end_row")]
    column_values = [match.group("start_column"), match.group("end_column")]
    if any(value is not None and len(value) > _MAX_XLSX_ROW_DIGITS for value in row_values):
        msg = "XLSX source exceeds the worksheet-row limit"
        raise TabularImportError(msg)
    if any(value is not None and int(value) > max_rows for value in row_values):
        msg = "XLSX source exceeds the worksheet-row limit"
        raise TabularImportError(msg)
    if any(
        value is not None and _xlsx_column_number(value) > max_columns for value in column_values
    ):
        msg = "XLSX source exceeds the worksheet-column limit"
        raise TabularImportError(msg)


def _validate_xlsx_row_number(value: str, *, max_rows: int) -> None:
    if (
        not value.isascii()
        or not value.isdigit()
        or len(value) > _MAX_XLSX_ROW_DIGITS
        or int(value) > max_rows
    ):
        msg = "XLSX source exceeds the worksheet-row limit"
        raise TabularImportError(msg)


def _xlsx_column_number(value: str) -> int:
    number = 0
    for character in value.upper():
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _normalize_xlsx_member_name(value: str) -> str:
    if (
        not value
        or "\\" in value
        or value.startswith("/")
        or _WINDOWS_DRIVE_PREFIX.match(value)
        or any(character in _ASCII_CONTROL_CHARACTERS for character in value)
    ):
        msg = "XLSX source contains an unsafe archive-member name"
        raise TabularImportError(msg)
    normalized = value.rstrip("/")
    parts = normalized.split("/")
    if not normalized or any(part in {"", ".", ".."} for part in parts):
        msg = "XLSX source contains an unsafe archive-member name"
        raise TabularImportError(msg)
    return normalized


def _require_regular_xlsx_member(info: zipfile.ZipInfo) -> None:
    unix_mode = info.external_attr >> 16
    file_type = stat.S_IFMT(unix_mode)
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        msg = "XLSX source contains a non-regular archive member"
        raise TabularImportError(msg)


def _compression_ratio(expanded_bytes: int, compressed_bytes: int) -> float:
    if expanded_bytes == 0:
        return 0.0
    if compressed_bytes <= 0:
        return math.inf
    return expanded_bytes / compressed_bytes
