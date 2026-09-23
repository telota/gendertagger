"""Compile DNB MARC21-XML full dumps into immutable GND SQLite lookups."""

from __future__ import annotations

import gzip
import json
import sqlite3
from collections.abc import Generator, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Final, cast

from lxml import etree

from gendertagger.methods.sqlite_lookup import (
    LookupDatabaseMetadata,
    create_lookup_database,
    finalize_lookup_database,
)

GND_LOOKUP_LOGICAL_TYPE: Final = "gnd_lookup_snapshot"
GND_LOOKUP_SCHEMA_VERSION: Final = "gnd_lookup_v1"
GND_LOOKUP_COMPILER_VERSION: Final = "gnd_marcxml_compiler_v1"

_MARC_NAMESPACE: Final = "http://www.loc.gov/MARC21/slim"
_RECORD_TAGS: Final = (f"{{{_MARC_NAMESPACE}}}record", "record")
_HEADING_TAGS: Final = ("100", "110", "111", "130", "150", "151")
_MARC_LEADER_RECORD_STATUS_POSITION: Final = 5
_PREFERRED_NAME_SUBFIELDS: Final = frozenset({"a", "b", "c", "d", "g", "n", "p"})
_GENDER_MALE_URI: Final = "https://d-nb.info/standards/vocab/gnd/gender#male"
_GENDER_FEMALE_URI: Final = "https://d-nb.info/standards/vocab/gnd/gender#female"
_INSERT_BATCH_SIZE: Final = 5_000


class GndEntityType(StrEnum):
    """Entity families relevant to GND authority classification provenance."""

    person = "person"
    corporate_body = "corporate_body"
    family = "family"
    conference_or_event = "conference_or_event"
    work = "work"
    subject = "subject"
    place = "place"
    other = "other"


@dataclass(frozen=True, slots=True)
class GndSnapshotRecord:
    """One normalized row extracted from a source GND authority record."""

    gnd_id: str
    entity_type: GndEntityType
    raw_entity_types: tuple[str, ...]
    gender_uri: str | None
    raw_gender_label: str | None
    lookup_label: str
    preferred_name: str | None
    record_status: str | None

    def as_sqlite_row(
        self,
    ) -> tuple[str, str, str, str | None, str | None, str, str | None, str | None]:
        """Return the stable SQLite serialization of this record."""
        return (
            self.gnd_id,
            self.entity_type.value,
            json.dumps(self.raw_entity_types, ensure_ascii=False, separators=(",", ":")),
            self.gender_uri,
            self.raw_gender_label,
            self.lookup_label,
            self.preferred_name,
            self.record_status,
        )


@contextmanager
def _open_dump(path: Path) -> Generator[BinaryIO, None, None]:
    with path.open("rb") as source:
        is_gzip = source.read(2) == b"\x1f\x8b"
    if is_gzip:
        with gzip.open(path, "rb") as handle:
            yield cast(BinaryIO, handle)
        return
    with path.open("rb") as handle:
        yield handle


def _children_with_tag(
    record: etree._Element,
    element_name: str,
    tag: str,
) -> list[etree._Element]:
    return [
        child
        for child in record
        if etree.QName(child).localname == element_name and child.get("tag") == tag
    ]


def _subfield_values(field: etree._Element, code: str) -> list[str]:
    return [
        value
        for child in field
        if etree.QName(child).localname == "subfield"
        and child.get("code") == code
        and (value := (child.text or "").strip())
    ]


def _control_value(record: etree._Element, tag: str) -> str | None:
    fields = _children_with_tag(record, "controlfield", tag)
    if not fields:
        return None
    value = (fields[0].text or "").strip()
    return value or None


def _entity_type(
    record: etree._Element,
    raw_entity_types: tuple[str, ...],
) -> tuple[GndEntityType, etree._Element | None]:
    mappings = {
        "100": GndEntityType.person,
        "110": GndEntityType.corporate_body,
        "111": GndEntityType.conference_or_event,
        "130": GndEntityType.work,
        "150": GndEntityType.subject,
        "151": GndEntityType.place,
    }
    folded_types = {value.casefold() for value in raw_entity_types}
    for tag in _HEADING_TAGS:
        fields = _children_with_tag(record, "datafield", tag)
        if fields:
            entity_type = mappings[tag]
            if tag == "100" and "pif" in folded_types:
                entity_type = GndEntityType.family
            return entity_type, fields[0]

    if "pif" in folded_types:
        return GndEntityType.family, None
    if any(value == "b" or value == "u" or value.startswith("k") for value in folded_types):
        return GndEntityType.corporate_body, None
    if any(value == "f" or value.startswith("v") for value in folded_types):
        return GndEntityType.conference_or_event, None
    if any(value == "n" or value.startswith("p") for value in folded_types):
        return GndEntityType.person, None
    if any(value.startswith("g") for value in folded_types):
        return GndEntityType.place, None
    if any(value.startswith("w") for value in folded_types):
        return GndEntityType.work, None
    if any(value.startswith("s") for value in folded_types):
        return GndEntityType.subject, None
    return GndEntityType.other, None


def _preferred_name(heading: etree._Element | None) -> str | None:
    if heading is None:
        return None
    parts = [
        value
        for child in heading
        if etree.QName(child).localname == "subfield"
        and child.get("code") in _PREFERRED_NAME_SUBFIELDS
        and (value := (child.text or "").strip())
    ]
    return " ".join(parts) or None


def _gender(record: etree._Element) -> tuple[str | None, str | None, str]:
    fields = _children_with_tag(record, "datafield", "375")
    if not fields:
        return None, None, "Unbekannt"
    field = fields[0]
    labels = _subfield_values(field, "a")
    raw_label = labels[0] if labels else None
    identifiers = [*_subfield_values(field, "0"), *_subfield_values(field, "1")]
    gender_uri = identifiers[0] if identifiers else None
    folded_label = raw_label.casefold() if raw_label is not None else ""
    folded_uri = gender_uri.casefold() if gender_uri is not None else ""
    if (
        "female" in folded_uri
        or folded_label in {"2", "f", "female", "weiblich"}
        or "weiblich" in folded_label
    ):
        return gender_uri or _GENDER_FEMALE_URI, raw_label, "Weiblich"
    if (
        ("male" in folded_uri and "female" not in folded_uri)
        or folded_label in {"1", "m", "male", "männlich"}
        or "männlich" in folded_label
    ):
        return gender_uri or _GENDER_MALE_URI, raw_label, "Männlich"
    return gender_uri, raw_label, "Unbekannt"


def _record_status(record: etree._Element) -> str | None:
    leaders = [child for child in record if etree.QName(child).localname == "leader"]
    if not leaders:
        return None
    leader = (leaders[0].text or "").strip()
    if len(leader) <= _MARC_LEADER_RECORD_STATUS_POSITION:
        return None
    return leader[_MARC_LEADER_RECORD_STATUS_POSITION]


def _parse_record(record: etree._Element) -> GndSnapshotRecord | None:
    gnd_id = _control_value(record, "001")
    if gnd_id is None:
        return None
    raw_entity_types = tuple(
        dict.fromkeys(
            value
            for field_tag, subfield_codes in (("075", ("b",)), ("079", ("b", "v")))
            for field in _children_with_tag(record, "datafield", field_tag)
            for subfield_code in subfield_codes
            for value in _subfield_values(field, subfield_code)
        )
    )
    entity_type, heading = _entity_type(record, raw_entity_types)
    gender_uri, raw_gender_label, lookup_label = _gender(record)
    return GndSnapshotRecord(
        gnd_id=gnd_id,
        entity_type=entity_type,
        raw_entity_types=raw_entity_types,
        gender_uri=gender_uri,
        raw_gender_label=raw_gender_label,
        lookup_label=lookup_label,
        preferred_name=_preferred_name(heading),
        record_status=_record_status(record),
    )


def iter_gnd_marcxml_records(source_path: Path) -> Iterator[GndSnapshotRecord]:
    """Stream normalized authority records from MARC21-XML or MARC21-XML.gz."""
    with _open_dump(source_path) as handle:
        context = etree.iterparse(
            handle,
            events=("end",),
            tag=_RECORD_TAGS,
            resolve_entities=False,
            no_network=True,
            huge_tree=True,
        )
        for _, element in context:
            parsed = _parse_record(element)
            if parsed is not None:
                yield parsed
            element.clear()
            parent = element.getparent()
            if parent is not None:
                while element.getprevious() is not None:
                    del parent[0]


def _insert_records(
    connection: sqlite3.Connection,
    records: Sequence[GndSnapshotRecord],
) -> None:
    connection.executemany(
        """INSERT OR REPLACE INTO gnd_entries (
            gnd_id,
            entity_type,
            raw_entity_types,
            gender_uri,
            raw_gender_label,
            lookup_label,
            preferred_name,
            record_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (record.as_sqlite_row() for record in records),
    )


def compile_gnd_marcxml_lookup(
    source_path: Path | Sequence[Path],
    destination_path: Path,
    *,
    source_sha256: str,
    source_sha256s: Sequence[str] | None = None,
    source_version: str | None = None,
) -> int:
    """Compile one or more local DNB MARC21-XML dumps into a SQLite lookup."""
    paths = (source_path,) if isinstance(source_path, Path) else tuple(source_path)
    if not paths:
        msg = "at least one GND MARC21-XML source is required"
        raise ValueError(msg)
    connection = create_lookup_database(
        destination_path,
        LookupDatabaseMetadata(
            method_name="gnd",
            lookup_schema_version=GND_LOOKUP_SCHEMA_VERSION,
            compiler_version=GND_LOOKUP_COMPILER_VERSION,
            source_sha256=source_sha256,
            source_version=source_version,
            source_sha256s=() if source_sha256s is None else tuple(source_sha256s),
        ),
    )
    try:
        connection.execute(
            """CREATE TABLE gnd_entries (
                gnd_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                raw_entity_types TEXT NOT NULL,
                gender_uri TEXT,
                raw_gender_label TEXT,
                lookup_label TEXT NOT NULL,
                preferred_name TEXT,
                record_status TEXT
            ) WITHOUT ROWID"""
        )
        batch: list[GndSnapshotRecord] = []
        entity_types: set[str] = set()
        for source_path in paths:
            for record in iter_gnd_marcxml_records(source_path):
                entity_types.add(record.entity_type.value)
                batch.append(record)
                if len(batch) >= _INSERT_BATCH_SIZE:
                    _insert_records(connection, batch)
                    batch.clear()
        if batch:
            _insert_records(connection, batch)
        record_count = int(connection.execute("SELECT COUNT(*) FROM gnd_entries").fetchone()[0])
        if record_count == 0:
            msg = "GND MARC21-XML source produced an empty lookup"
            raise ValueError(msg)
        required_entity_types = {
            GndEntityType.person.value,
            GndEntityType.corporate_body.value,
        }
        if not required_entity_types.issubset(entity_types):
            msg = "GND lookup must contain both person and corporate-body authority records"
            raise ValueError(msg)
        finalize_lookup_database(connection, record_count=record_count)
    except BaseException:
        connection.close()
        destination_path.unlink(missing_ok=True)
        raise
    connection.close()
    return record_count
