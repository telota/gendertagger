from io import BytesIO

import pytest

from gendertagger.ingestion.tei import TEI_PARSER_VERSION, TeiImportError, TeiPersonParser
from gendertagger.models.person import PersonInput
from gendertagger.models.project import TeiImportProfile

VALID_TEI = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body><listPerson>
    <person xml:id="p1">
      <persName type="reg">
        <surname> Example </surname>
        <forename>Anna <name type="used">Maria</name></forename>
        <forename>Luise</forename>
      </persName>
      <persName type="alt" subtype="married">Anna Sample</persName>
      <birth>1810-01-01</birth>
      <death>1880</death>
      <note>Scholar <hi>and</hi> editor.</note>
      <idno type="uri">https://d-nb.info/gnd/123456789</idno>
      <idno type="uri">https://www.wikidata.org/entity/Q42</idno>
      <idno type="viaf">98765</idno>
    </person>
    <person xml:id="p2">
      <persName type="reg"><name>Mononym</name></persName>
    </person>
  </listPerson></body></text>
</TEI>
"""


def test_parser_extracts_versioned_source_fields() -> None:
    parser = TeiPersonParser()

    people = list(parser.iter_people(BytesIO(VALID_TEI)))

    assert parser.version == TEI_PARSER_VERSION
    assert parser.profile is TeiImportProfile.tei_p5_person_register_v1
    assert people == [
        PersonInput(
            tei_id="p1",
            surname="Example",
            forenames=["Anna Maria", "Luise"],
            birth="1810-01-01",
            death="1880",
            note="Scholar and editor.",
            alt_names=["Anna Sample"],
            gnd_id="123456789",
            external_ids={"wikidata": "Q42", "viaf": "98765"},
        ),
        PersonInput(tei_id="p2", surname="Mononym"),
    ]


def test_parser_rejects_doctype_without_resolving_external_entity() -> None:
    malicious = b"""<?xml version="1.0"?>
<!DOCTYPE TEI [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body><listPerson><person xml:id="p1"><note>&xxe;</note></person></listPerson></body></text>
</TEI>
"""

    with pytest.raises(TeiImportError, match="DOCTYPE"):
        list(TeiPersonParser().iter_people(BytesIO(malicious)))


@pytest.mark.parametrize(
    ("source", "diagnostic"),
    [
        (
            b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><person/></TEI>',
            "requires a non-blank xml:id",
        ),
        (
            b'<TEI xmlns="http://www.tei-c.org/ns/1.0">'
            b'<person xml:id="same"/><person xml:id="same"/></TEI>',
            "duplicate TEI xml:id",
        ),
        (b'<TEI><person xml:id="p1"/></TEI>', "TEI P5 namespace"),
        (b'<TEI xmlns="http://www.tei-c.org/ns/1.0">', "invalid TEI XML"),
    ],
)
def test_parser_rejects_invalid_registers(source: bytes, diagnostic: str) -> None:
    with pytest.raises(TeiImportError, match=diagnostic):
        list(TeiPersonParser().iter_people(BytesIO(source)))
