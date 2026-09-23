import io
import json

import pytest

from gendertagger.ingestion.authority import (
    AuthorityIdentifierError,
    normalize_external_identifier,
)
from gendertagger.ingestion.tabular import (
    TabularImportError,
    TeiEquivalentPersonRegisterParser,
)
from gendertagger.ingestion.tei import TeiImportError, TeiPersonParser


@pytest.mark.parametrize(
    ("identifier_type", "value", "expected"),
    [
        ("gnd", "123456789", ("gnd", "123456789")),
        ("gnd", "https://d-nb.info/gnd/123456789", ("gnd", "123456789")),
        ("uri", "http://www.d-nb.info/123456789", ("gnd", "123456789")),
        ("viaf", "https://viaf.org/viaf/98765", ("viaf", "98765")),
        (
            "wikidata",
            "https://www.wikidata.org/entity/Q42",
            ("wikidata", "Q42"),
        ),
        ("uri", "https://example.invalid/person/1", None),
        ("uri", "https://d-nb.info.evil.example/gnd/123456789", None),
        (
            "local-catalogue",
            "https://example.invalid/abc",
            ("local_catalogue", "https://example.invalid/abc"),
        ),
    ],
)
def test_strict_authority_normalizer_matches_only_canonical_authority_uris(
    identifier_type: str,
    value: str,
    expected: tuple[str, str] | None,
) -> None:
    assert normalize_external_identifier(identifier_type, value) == expected


@pytest.mark.parametrize(
    ("identifier_type", "value", "diagnostic"),
    [
        (
            "gnd",
            "https://d-nb.info.evil.example/gnd/123456789",
            "canonical authority URI",
        ),
        (
            "gnd",
            "https://viaf.org/viaf/98765",
            "conflicts with the identifier URI",
        ),
        (
            "local-catalogue",
            "https://www.wikidata.org/entity/Q42",
            "conflicts with the authority URI",
        ),
    ],
)
def test_strict_authority_normalizer_rejects_typed_uri_conflicts(
    identifier_type: str,
    value: str,
    diagnostic: str,
) -> None:
    with pytest.raises(AuthorityIdentifierError, match=diagnostic):
        normalize_external_identifier(identifier_type, value)


def test_tei_v3_and_tabular_typed_authority_uris_have_identical_projection() -> None:
    tei = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="p1"><persName type="reg"><name>Example</name></persName>
      <idno type="gnd">https://d-nb.info/gnd/123456789</idno>
      <idno type="viaf">https://viaf.org/viaf/98765</idno>
      <idno type="wikidata">https://www.wikidata.org/entity/Q42</idno>
      <idno type="local-catalogue">abc-123</idno>
    </person></listPerson></body></text></TEI>"""
    tabular = [
        {
            "xml:id": "p1",
            "persName": [{"type": "reg", "name": "Example"}],
            "birth": None,
            "death": None,
            "event": [],
            "note": None,
            "idno": [
                {"type": "gnd", "value": "https://d-nb.info/gnd/123456789"},
                {"type": "viaf", "value": "https://viaf.org/viaf/98765"},
                {
                    "type": "wikidata",
                    "value": "https://www.wikidata.org/entity/Q42",
                },
                {"type": "local-catalogue", "value": "abc-123"},
            ],
        }
    ]

    [tei_person] = TeiPersonParser().iter_people(io.BytesIO(tei))
    [tabular_person] = TeiEquivalentPersonRegisterParser().iter_json(
        io.BytesIO(json.dumps(tabular).encode())
    )

    assert tei_person.gnd_id == tabular_person.person.gnd_id == "123456789"
    assert (
        tei_person.external_ids
        == tabular_person.person.external_ids
        == {
            "viaf": "98765",
            "wikidata": "Q42",
            "local_catalogue": "abc-123",
        }
    )


def test_tei_v3_and_tabular_reject_the_same_authority_conflict_and_duplicate() -> None:
    conflict_tei = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="p1"><persName type="reg"><name>Example</name></persName>
      <idno type="gnd">https://viaf.org/viaf/98765</idno>
    </person></listPerson></body></text></TEI>"""
    duplicate_tei = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
    <person xml:id="p1"><persName type="reg"><name>Example</name></persName>
      <idno type="gnd">123456789</idno>
      <idno type="uri">https://d-nb.info/gnd/987654321</idno>
    </person></listPerson></body></text></TEI>"""
    tabular_record = {
        "xml:id": "p1",
        "persName": [{"type": "reg", "name": "Example"}],
        "birth": None,
        "death": None,
        "event": [],
        "note": None,
        "idno": [{"type": "gnd", "value": "https://viaf.org/viaf/98765"}],
    }

    with pytest.raises(TeiImportError, match="conflicts with the identifier URI"):
        list(TeiPersonParser().iter_people(io.BytesIO(conflict_tei)))
    with pytest.raises(TeiImportError, match="duplicate normalized identifier schemes"):
        list(TeiPersonParser().iter_people(io.BytesIO(duplicate_tei)))
    with pytest.raises(TabularImportError, match="conflicts with the identifier URI"):
        list(
            TeiEquivalentPersonRegisterParser().iter_json(
                io.BytesIO(json.dumps([tabular_record]).encode())
            )
        )
