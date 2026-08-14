from io import BytesIO

import pytest

from gendertagger.ingestion.tei import (
    TEI_PARSER_V1_VERSION,
    TEI_PARSER_VERSION,
    TeiImportError,
    TeiPersonParser,
)
from gendertagger.models.person import PersonInput, PersonNameForm, PersonNameType
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

STRUCTURED_NAMES_TEI = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
<listPerson><person xml:id="p1">
<persName type="reg"><surname>Example</surname><forename>Anna <name type="used">Maria</name></forename></persName>
<persName type="alt"><surname>Sample</surname><forename>Anna</forename><forename>Maria</forename></persName>
<persName type="alt"><name>Anna Example</name></persName>
<persName type="alt" subtype="birthname"><name>Origin</name></persName>
<persName type="alt" subtype="pseudonym"><surname>Writer</surname><forename>A.</forename></persName>
</person><person xml:id="p2"><persName type="reg"><name>Mononym</name></persName></person>
</listPerson></body></text></TEI>"""


def test_v1_parser_extracts_flat_source_fields_without_name_forms() -> None:
    parser = TeiPersonParser()

    people = list(
        parser.iter_people(
            BytesIO(VALID_TEI),
            profile=TeiImportProfile.tei_p5_person_register_v1,
        )
    )

    assert parser.profile is TeiImportProfile.tei_p5_person_register_v2
    assert (
        parser.version_for_profile(TeiImportProfile.tei_p5_person_register_v1)
        == TEI_PARSER_V1_VERSION
    )
    assert (
        parser.version_for_profile(TeiImportProfile.tei_p5_person_register_v2) == TEI_PARSER_VERSION
    )
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
    assert all(person.name_forms is None for person in people)


def test_v2_parser_preserves_structured_name_forms_in_document_order() -> None:
    parser = TeiPersonParser()

    [person, mononym] = list(parser.iter_people(BytesIO(STRUCTURED_NAMES_TEI)))

    assert person.surname == "Example"
    assert person.forenames == ["Anna Maria"]
    assert person.alt_names == [
        "Sample Anna Maria",
        "Anna Example",
        "Origin",
        "Writer A.",
    ]
    assert person.name_forms == [
        PersonNameForm(
            type=PersonNameType.regular,
            surname="Example",
            forenames=["Anna Maria"],
        ),
        PersonNameForm(
            type=PersonNameType.alternative,
            surname="Sample",
            forenames=["Anna", "Maria"],
        ),
        PersonNameForm(
            type=PersonNameType.alternative,
            name="Anna Example",
        ),
        PersonNameForm(
            type=PersonNameType.alternative,
            subtype="birthname",
            name="Origin",
        ),
        PersonNameForm(
            type=PersonNameType.alternative,
            subtype="pseudonym",
            surname="Writer",
            forenames=["A."],
        ),
    ]
    assert mononym.surname == "Mononym"
    assert mononym.forenames == []
    assert mononym.name_forms == [PersonNameForm(type=PersonNameType.regular, name="Mononym")]


def test_explicit_v1_profile_does_not_change_the_v2_default() -> None:
    parser = TeiPersonParser()

    [legacy_person, _] = list(
        parser.iter_people(
            BytesIO(STRUCTURED_NAMES_TEI),
            profile=TeiImportProfile.tei_p5_person_register_v1,
        )
    )
    [default_person, _] = list(parser.iter_people(BytesIO(STRUCTURED_NAMES_TEI)))

    assert legacy_person.name_forms is None
    assert default_person.name_forms is not None
    assert parser.profile is TeiImportProfile.tei_p5_person_register_v2


def test_v2_parser_supports_direct_text_and_empty_name_link_placeholders() -> None:
    source = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="p1">
      <persName type="reg" subtype="indexed"><?editorial keep?>Mononym</persName>
      <persName type="alt"><surname>Earlier</surname><forename/><nameLink/></persName>
      <persName type="alt">van<nameLink/>Helsing</persName>
    </person>
    </listPerson></body></text></TEI>"""

    [person] = list(TeiPersonParser().iter_people(BytesIO(source)))

    assert person.surname == "Mononym"
    assert person.alt_names == ["Earlier", "van Helsing"]
    assert person.name_forms == [
        PersonNameForm(
            type=PersonNameType.regular,
            subtype="indexed",
            name="Mononym",
        ),
        PersonNameForm(type=PersonNameType.alternative, surname="Earlier"),
        PersonNameForm(type=PersonNameType.alternative, name="van Helsing"),
    ]


def test_v2_parser_recognizes_authority_uris_without_importing_editorial_comments() -> None:
    source = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="gnd-legacy">
      <persName type="reg"><name>GND example</name></persName>
      <idno type="uri">http://d-nb.info/124159206</idno>
      <note>Visible<?oxy_comment_start comment="not person data"?> text<!-- hidden -->.</note>
    </person>
    <person xml:id="viaf">
      <persName type="reg"><name>VIAF example</name></persName>
      <idno type="uri">https://viaf.org/viaf/280885993</idno>
    </person>
    <person xml:id="gnd-comment">
      <persName type="reg"><name>Commented GND example</name></persName>
      <idno type="uri">https:/<?oxy_comment_start comment="hidden"?>/d-nb.info/gnd/117066028</idno>
    </person>
    </listPerson></body></text></TEI>"""

    legacy_gnd, viaf, commented_gnd = list(TeiPersonParser().iter_people(BytesIO(source)))

    assert legacy_gnd.gnd_id == "124159206"
    assert legacy_gnd.note == "Visible text."
    assert viaf.external_ids == {"viaf": "280885993"}
    assert commented_gnd.gnd_id == "117066028"


@pytest.mark.parametrize(
    ("pers_name", "diagnostic"),
    [
        (
            '<persName type="reg"><surname>One</surname><surname>Two</surname></persName>',
            "multiple surname elements",
        ),
        (
            '<persName type="reg"><surname>One</surname>, <forename>Anna</forename></persName>',
            "must not contain direct text",
        ),
        (
            '<persName type="reg"><surname>One</surname><addName>Other</addName></persName>',
            "unsupported child elements",
        ),
        (
            '<persName type="reg"><surname>One</surname><nameLink>von</nameLink></persName>',
            "non-empty TEI nameLink",
        ),
        (
            '<persName type="reg" xml:lang="de"><surname>One</surname></persName>',
            "unsupported attributes",
        ),
        (
            '<persName type="reg"><surname type="indexed">One</surname></persName>',
            "name components contain unsupported attributes",
        ),
    ],
)
def test_v2_parser_rejects_name_structure_it_cannot_preserve(
    pers_name: str,
    diagnostic: str,
) -> None:
    source = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>'
        f'<person xml:id="p1">{pers_name}</person>'
        "</listPerson></body></text></TEI>"
    ).encode()

    with pytest.raises(TeiImportError, match=diagnostic):
        list(TeiPersonParser().iter_people(BytesIO(source)))


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
            b'<person xml:id="same"><persName type="reg"><name>First</name></persName></person>'
            b'<person xml:id="same"><persName type="reg"><name>Second</name></persName></person>'
            b"</TEI>",
            "duplicate TEI xml:id",
        ),
        (b'<TEI><person xml:id="p1"/></TEI>', "TEI P5 namespace"),
        (b'<TEI xmlns="http://www.tei-c.org/ns/1.0">', "invalid TEI XML"),
    ],
)
def test_parser_rejects_invalid_registers(source: bytes, diagnostic: str) -> None:
    with pytest.raises(TeiImportError, match=diagnostic):
        list(TeiPersonParser().iter_people(BytesIO(source)))
