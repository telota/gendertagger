from io import BytesIO

import pytest

from gendertagger.ingestion.tei import (
    TEI_PARSER_V1_VERSION,
    TEI_PARSER_V2_VERSION,
    TEI_PARSER_V3_VERSION,
    TEI_PARSER_VERSION,
    TeiImportError,
    TeiPersonParser,
    TeiSourceReadError,
)
from gendertagger.models.person import PersonEvent, PersonInput, PersonNameForm, PersonNameType
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


class _UnreadableSource(BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        del size
        raise OSError("simulated staged-artifact read failure")


def test_v1_parser_extracts_flat_source_fields_without_name_forms() -> None:
    parser = TeiPersonParser()

    people = list(
        parser.iter_people(
            BytesIO(VALID_TEI),
            profile=TeiImportProfile.tei_p5_person_register_v1,
        )
    )

    assert parser.profile is TeiImportProfile.tei_p5_person_register_v3
    assert (
        parser.version_for_profile(TeiImportProfile.tei_p5_person_register_v1)
        == TEI_PARSER_V1_VERSION
    )
    assert (
        parser.version_for_profile(TeiImportProfile.tei_p5_person_register_v2)
        == TEI_PARSER_V2_VERSION
    )
    assert (
        parser.version_for_profile(TeiImportProfile.tei_p5_person_register_v3)
        == TEI_PARSER_V3_VERSION
        == TEI_PARSER_VERSION
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


@pytest.mark.parametrize(
    "profile",
    [
        TeiImportProfile.tei_p5_person_register_v2,
        TeiImportProfile.tei_p5_person_register_v3,
    ],
)
def test_structured_profiles_preserve_name_forms_in_document_order(
    profile: TeiImportProfile,
) -> None:
    parser = TeiPersonParser()

    [person, mononym] = list(parser.iter_people(BytesIO(STRUCTURED_NAMES_TEI), profile=profile))

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


def test_explicit_v1_profile_does_not_change_the_v3_default() -> None:
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
    assert parser.profile is TeiImportProfile.tei_p5_person_register_v3


def test_v3_preserves_direct_events_but_older_profiles_do_not_import_them() -> None:
    source = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="p1">
      <persName type="reg"><name>Example</name></persName>
      <sex value="female" evidence="assigned" resp="#legacy" cert="high"/>
      <event type="wedding" when="1832-09-20">
        <note>Married <?oxy_comment_start comment="editorial"?>in Berlin<!-- hidden -->.</note>
      </event>
    </person>
    </listPerson></body></text></TEI>"""
    parser = TeiPersonParser()

    [modern] = list(parser.iter_people(BytesIO(source)))
    [legacy] = list(
        parser.iter_people(
            source=BytesIO(source), profile=TeiImportProfile.tei_p5_person_register_v1
        )
    )
    [structured_legacy] = list(
        parser.iter_people(
            source=BytesIO(source), profile=TeiImportProfile.tei_p5_person_register_v2
        )
    )

    assert modern.events == [
        PersonEvent(type="wedding", when="1832-09-20", note="Married in Berlin.")
    ]
    assert legacy.events == []
    assert structured_legacy.events == []
    assert "sex" not in PersonInput.model_fields


def test_v3_parser_supports_direct_text_and_empty_name_link_placeholders() -> None:
    source = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="p1">
      <persName type="reg" subtype="indexed"><?editorial keep?>Mononym</persName>
      <persName type="alt"><surname>Earlier</surname><forename/><nameLink/></persName>
      <persName type="alt">van<nameLink/>Helsing</persName>
      <persName type="alt"><surname>Family</surname>
        <forename>van<nameLink/>Helsing<?oxy_comment_start comment="hidden"?> Jr.<!-- hidden -->, III</forename>
        <forename><persName key="#indexed">Anna</persName> Maria</forename>
      </persName>
    </person>
    </listPerson></body></text></TEI>"""

    [person] = list(TeiPersonParser().iter_people(BytesIO(source)))

    assert person.surname == "Mononym"
    assert person.alt_names == ["Earlier", "van Helsing", "Family van Helsing Jr., III Anna Maria"]
    assert person.name_forms == [
        PersonNameForm(
            type=PersonNameType.regular,
            subtype="indexed",
            name="Mononym",
        ),
        PersonNameForm(type=PersonNameType.alternative, surname="Earlier"),
        PersonNameForm(type=PersonNameType.alternative, name="van Helsing"),
        PersonNameForm(
            type=PersonNameType.alternative,
            surname="Family",
            forenames=["van Helsing Jr., III", "Anna Maria"],
        ),
    ]


def test_v2_retains_committed_direct_text_and_empty_name_link_behavior() -> None:
    source = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="p1">
      <persName type="reg" subtype="indexed"><?editorial keep?>Mononym</persName>
      <persName type="alt"><surname>Earlier</surname><forename/><nameLink/></persName>
      <persName type="alt">van<nameLink/>Helsing</persName>
    </person>
    </listPerson></body></text></TEI>"""

    [person] = TeiPersonParser().iter_people(
        BytesIO(source),
        profile=TeiImportProfile.tei_p5_person_register_v2,
    )

    assert person.name_forms == [
        PersonNameForm(
            type=PersonNameType.regular,
            subtype="indexed",
            name="Mononym",
        ),
        PersonNameForm(type=PersonNameType.alternative, surname="Earlier"),
        PersonNameForm(type=PersonNameType.alternative, name="van Helsing"),
    ]


def test_v1_and_v2_retain_historical_text_join_while_v3_inserts_safe_boundaries() -> None:
    source = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="p1">
      <persName type="reg"><surname>Example</surname><forename>van<nameLink/>Helsing</forename></persName>
      <note>Visible<?oxy_comment_start comment="hidden"?> text<!-- hidden -->.</note>
      <idno type="uri">https:/<?oxy_comment_start comment="hidden"?>/d-nb.info/gnd/123456789</idno>
    </person>
    </listPerson></body></text></TEI>"""
    parser = TeiPersonParser()

    [legacy] = parser.iter_people(
        BytesIO(source),
        profile=TeiImportProfile.tei_p5_person_register_v1,
    )
    [structured_legacy] = parser.iter_people(
        BytesIO(source),
        profile=TeiImportProfile.tei_p5_person_register_v2,
    )
    [modern] = parser.iter_people(BytesIO(source))

    assert legacy.forenames == structured_legacy.forenames == ["vanHelsing"]
    assert modern.forenames == ["van Helsing"]
    assert legacy.note == structured_legacy.note == modern.note == "Visible text."
    assert legacy.gnd_id == structured_legacy.gnd_id == modern.gnd_id == "123456789"


def test_v2_retains_descendant_flattening_that_v3_rejects() -> None:
    source = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="p1">
      <persName type="reg"><surname>One<foo/>Two</surname></persName>
    </person>
    </listPerson></body></text></TEI>"""
    parser = TeiPersonParser()

    [structured_legacy] = parser.iter_people(
        BytesIO(source),
        profile=TeiImportProfile.tei_p5_person_register_v2,
    )

    assert structured_legacy.surname == "OneTwo"
    with pytest.raises(TeiImportError, match="unsupported descendant elements"):
        list(parser.iter_people(BytesIO(source)))


@pytest.mark.parametrize(
    "profile",
    [
        TeiImportProfile.tei_p5_person_register_v2,
        TeiImportProfile.tei_p5_person_register_v3,
    ],
)
def test_structured_profiles_preserve_supported_legacy_authority_uri_projection(
    profile: TeiImportProfile,
) -> None:
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

    legacy_gnd, viaf, commented_gnd = list(
        TeiPersonParser().iter_people(BytesIO(source), profile=profile)
    )

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
@pytest.mark.parametrize(
    "profile",
    [
        TeiImportProfile.tei_p5_person_register_v2,
        TeiImportProfile.tei_p5_person_register_v3,
    ],
)
def test_structured_profiles_reject_committed_unsupported_direct_name_structure(
    pers_name: str,
    diagnostic: str,
    profile: TeiImportProfile,
) -> None:
    source = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>'
        f'<person xml:id="p1">{pers_name}</person>'
        "</listPerson></body></text></TEI>"
    ).encode()

    with pytest.raises(TeiImportError, match=diagnostic):
        list(TeiPersonParser().iter_people(BytesIO(source), profile=profile))


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


def test_parser_distinguishes_source_read_failure_from_invalid_tei() -> None:
    with pytest.raises(TeiSourceReadError, match="could not be read"):
        list(TeiPersonParser().iter_people(_UnreadableSource(VALID_TEI)))

    with pytest.raises(TeiImportError, match="invalid TEI XML") as malformed:
        list(TeiPersonParser().iter_people(BytesIO(b'<TEI xmlns="http://www.tei-c.org/ns/1.0">')))
    assert not isinstance(malformed.value, TeiSourceReadError)
