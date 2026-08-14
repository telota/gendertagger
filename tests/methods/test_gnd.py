from __future__ import annotations

import gzip
from collections.abc import Sequence
from pathlib import Path

import pytest

from gendertagger.methods.gnd import GndConfig, GndLookupRecord, GndMethod, SqliteGndLookup
from gendertagger.methods.gnd_snapshot import (
    GND_LOOKUP_LOGICAL_TYPE,
    GndEntityType,
    compile_gnd_marcxml_lookup,
    iter_gnd_marcxml_records,
)
from gendertagger.models.classification import CanonicalLabel, PredictionStatus
from gendertagger.models.person import PersonInput

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_LOOKUP_SHA256 = "c" * 64
_CONFIG = GndConfig(lookup_sha256=_LOOKUP_SHA256)


class _Resolver:
    def __init__(self, path: Path = Path("/verified/gnd.sqlite3")) -> None:
        self.path = path
        self.calls: list[tuple[str, str]] = []

    def materialize(self, logical_type: str, sha256: str) -> Path:
        self.calls.append((logical_type, sha256))
        return self.path


class _Lookup:
    def __init__(self, records: dict[str, GndLookupRecord]) -> None:
        self._records = records

    def get_many(self, gnd_ids: Sequence[str]) -> dict[str, GndLookupRecord]:
        return {gnd_id: self._records[gnd_id] for gnd_id in gnd_ids if gnd_id in self._records}


def _record(
    gnd_id: str,
    *,
    entity_type: GndEntityType = GndEntityType.person,
    lookup_label: str = "Unbekannt",
    raw_gender_label: str | None = None,
) -> GndLookupRecord:
    return GndLookupRecord(
        gnd_id=gnd_id,
        entity_type=entity_type,
        raw_entity_types=("piz",),
        gender_uri=None,
        raw_gender_label=raw_gender_label,
        lookup_label=lookup_label,
        preferred_name="Authority name",
        record_status="n",
    )


def _method(records: dict[str, GndLookupRecord]) -> GndMethod:
    return GndMethod(
        lookup_asset_resolver=_Resolver(),
        lookup_factory=lambda _path: _Lookup(records),
    )


def test_descriptor_and_config_select_the_versioned_lookup() -> None:
    descriptor = GndMethod.descriptor
    assert descriptor.name == "gnd"
    assert descriptor.implementation_version == "gnd_v1"
    assert descriptor.normalization_version == "gnd_v1"
    assert descriptor.method_confidence_range is None

    with pytest.raises(ValueError, match="lookup_sha256"):
        GndConfig.model_validate({})
    with pytest.raises(ValueError, match="extra"):
        GndConfig.model_validate({"lookup_sha256": _LOOKUP_SHA256, "snapshot": "latest"})


def test_missing_input_or_snapshot_row_abstains_as_no_gnd() -> None:
    method = _method({})
    results = method.predict_batch(
        [PersonInput(tei_id="p1"), PersonInput(tei_id="p2", gnd_id="missing")],
        _CONFIG,
    )

    assert [result.status for result in results] == [
        PredictionStatus.abstain,
        PredictionStatus.abstain,
    ]
    assert [result.raw_label for result in results] == ["no_gnd", "no_gnd"]
    assert results[1].raw_output == {"gnd_id": "missing", "lookup_match": False}


def test_person_gender_uses_stable_lookup_label_and_preserves_source_evidence() -> None:
    method = _method(
        {
            "male-id": _record(
                "male-id",
                lookup_label="Männlich",
                raw_gender_label="männlich",
            ),
            "female-id": _record(
                "female-id",
                lookup_label="Weiblich",
                raw_gender_label="weiblich",
            ),
        }
    )

    male, female = method.predict_batch(
        [
            PersonInput(tei_id="p1", gnd_id="male-id"),
            PersonInput(tei_id="p2", gnd_id="female-id"),
        ],
        _CONFIG,
    )

    assert male.label is CanonicalLabel.male
    assert female.label is CanonicalLabel.female
    assert male.raw_output["source_gender_label"] == "männlich"
    assert male.raw_output["raw_entity_types"] == ["piz"]


def test_corporate_body_entity_type_is_an_authority_institution_result() -> None:
    method = _method(
        {
            "org-id": _record(
                "org-id",
                entity_type=GndEntityType.corporate_body,
            )
        }
    )

    (result,) = method.predict_batch([PersonInput(tei_id="p1", gnd_id="org-id")], _CONFIG)

    assert result.status is PredictionStatus.success
    assert result.label is CanonicalLabel.institution
    assert result.raw_label == "organisation"
    assert result.raw_output["entity_type"] == "corporate_body"


def test_nonperson_without_gender_is_substantive_unknown() -> None:
    method = _method({"place-id": _record("place-id", entity_type=GndEntityType.place)})

    (result,) = method.predict_batch([PersonInput(tei_id="p1", gnd_id="place-id")], _CONFIG)

    assert result.status is PredictionStatus.success
    assert result.label is CanonicalLabel.unknown
    assert result.raw_label == "Unbekannt"


def test_lookup_is_materialized_once_per_digest() -> None:
    resolver = _Resolver()
    built: list[Path] = []

    def factory(path: Path) -> _Lookup:
        built.append(path)
        return _Lookup({})

    method = GndMethod(lookup_asset_resolver=resolver, lookup_factory=factory)
    method.predict_batch([PersonInput(tei_id="p1")], _CONFIG)
    method.predict_batch([PersonInput(tei_id="p2")], _CONFIG)

    assert resolver.calls == [(GND_LOOKUP_LOGICAL_TYPE, _LOOKUP_SHA256)]
    assert built == [Path("/verified/gnd.sqlite3")]


_MARCXML = b"""<?xml version="1.0" encoding="UTF-8"?>
<collection xmlns="http://www.loc.gov/MARC21/slim">
  <record>
    <leader>00000n000000000000000000</leader>
    <controlfield tag="001">person-1</controlfield>
    <datafield tag="075"><subfield code="b">piz</subfield></datafield>
    <datafield tag="100"><subfield code="a">Muster, Karl</subfield></datafield>
    <datafield tag="375">
      <subfield code="a">1</subfield>
      <subfield code="2">iso5218</subfield>
    </datafield>
  </record>
  <record>
    <leader>00000c000000000000000000</leader>
    <controlfield tag="001">org-1</controlfield>
    <datafield tag="075"><subfield code="b">kiz</subfield></datafield>
    <datafield tag="110"><subfield code="a">Beispielverein</subfield></datafield>
  </record>
  <record>
    <leader>00000n000000000000000000</leader>
    <controlfield tag="001">family-1</controlfield>
    <datafield tag="075"><subfield code="b">pif</subfield></datafield>
    <datafield tag="079">
      <subfield code="b">p</subfield>
      <subfield code="v">pif</subfield>
    </datafield>
    <datafield tag="100"><subfield code="a">Familie Muster</subfield></datafield>
  </record>
  <record>
    <leader>00000n000000000000000000</leader>
    <controlfield tag="001">event-1</controlfield>
    <datafield tag="079">
      <subfield code="b">f</subfield>
      <subfield code="v">vie</subfield>
    </datafield>
    <datafield tag="111"><subfield code="a">Beispielkongress</subfield></datafield>
  </record>
</collection>
"""


def test_marcxml_compiler_preserves_gender_entity_type_and_status(tmp_path: Path) -> None:
    source = tmp_path / "gnd.xml"
    source.write_bytes(_MARCXML)
    lookup_path = tmp_path / "gnd.sqlite3"

    record_count = compile_gnd_marcxml_lookup(
        source,
        lookup_path,
        source_sha256="f" * 64,
        source_version="2026-08",
    )
    lookup = SqliteGndLookup(lookup_path)
    records = lookup.get_many(["event-1", "family-1", "org-1", "person-1", "missing"])

    assert record_count == 4
    assert records["person-1"].entity_type is GndEntityType.person
    assert records["person-1"].raw_entity_types == ("piz",)
    assert records["person-1"].raw_gender_label == "1"
    assert records["person-1"].lookup_label == "Männlich"
    assert records["person-1"].preferred_name == "Muster, Karl"
    assert records["person-1"].record_status == "n"
    assert records["org-1"].entity_type is GndEntityType.corporate_body
    assert records["org-1"].record_status == "c"
    assert records["family-1"].entity_type is GndEntityType.family
    assert records["family-1"].raw_entity_types == ("pif", "p")
    assert records["event-1"].entity_type is GndEntityType.conference_or_event
    assert records["event-1"].raw_entity_types == ("f", "vie")


def test_marcxml_parser_streams_gzip_source(tmp_path: Path) -> None:
    source = tmp_path / "gnd.xml.gz"
    with gzip.open(source, "wb") as handle:
        handle.write(_MARCXML)

    records = list(iter_gnd_marcxml_records(source))

    assert [record.gnd_id for record in records] == [
        "person-1",
        "org-1",
        "family-1",
        "event-1",
    ]


def test_gnd_compiler_rejects_an_empty_collection(tmp_path: Path) -> None:
    source = tmp_path / "gnd.xml"
    source.write_text(
        '<collection xmlns="http://www.loc.gov/MARC21/slim"/>',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="empty lookup"):
        compile_gnd_marcxml_lookup(
            source,
            tmp_path / "lookup.sqlite3",
            source_sha256="f" * 64,
        )


def test_gnd_compiler_merges_multiple_entity_dumps(tmp_path: Path) -> None:
    person_source = tmp_path / "person.xml"
    person_source.write_bytes(
        b"""<collection xmlns="http://www.loc.gov/MARC21/slim">
<record><controlfield tag="001">person-2</controlfield>
<datafield tag="100"><subfield code="a">Person Two</subfield></datafield>
<datafield tag="375"><subfield code="a">2</subfield></datafield></record>
</collection>"""
    )
    corporate_source = tmp_path / "corporate.xml"
    corporate_source.write_bytes(
        b"""<collection xmlns="http://www.loc.gov/MARC21/slim">
<record><controlfield tag="001">org-2</controlfield>
<datafield tag="110"><subfield code="a">Organization Two</subfield></datafield></record>
</collection>"""
    )
    lookup_path = tmp_path / "lookup.sqlite3"

    record_count = compile_gnd_marcxml_lookup(
        (person_source, corporate_source),
        lookup_path,
        source_sha256="f" * 64,
    )
    records = SqliteGndLookup(lookup_path).get_many(["person-2", "org-2"])

    assert record_count == 2
    assert records["person-2"].lookup_label == "Weiblich"
    assert records["org-2"].entity_type is GndEntityType.corporate_body


def test_gnd_compiler_rejects_a_partial_entity_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "person-only.xml"
    source.write_bytes(
        b"""<collection xmlns="http://www.loc.gov/MARC21/slim">
<record><controlfield tag="001">person-only</controlfield>
<datafield tag="100"><subfield code="a">Person Only</subfield></datafield></record>
</collection>"""
    )

    with pytest.raises(ValueError, match="both person and corporate-body"):
        compile_gnd_marcxml_lookup(
            source,
            tmp_path / "lookup.sqlite3",
            source_sha256="f" * 64,
        )
