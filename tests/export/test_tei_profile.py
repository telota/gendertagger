from __future__ import annotations

from uuid import uuid4

import pytest
from lxml import etree

from gendertagger.export.tei_profile import TeiExportError, inject_gender_annotations
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.export import ExportPersonRecord

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
_NS = {"tei": _TEI_NAMESPACE, "xml": "http://www.w3.org/XML/1998/namespace"}

_SOURCE = f"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="{_TEI_NAMESPACE}" xml:id="S1">
  <teiHeader><fileDesc><titleStmt><title>Register</title></titleStmt>
  <publicationStmt><p>-</p></publicationStmt><sourceDesc><p>-</p></sourceDesc></fileDesc></teiHeader>
  <text><body><listPerson>
    <person xml:id="p1">
      <persName type="reg"><surname>Example</surname><forename>Anna</forename></persName>
      <birth>1800</birth>
      <death>1870</death>
      <note>A note.</note>
    </person>
    <person xml:id="p2">
      <persName type="reg"><surname>Untouched</surname></persName>
    </person>
  </listPerson></body></text>
</TEI>
""".encode()


def _record(tei_id: str, *, label: str | None) -> ExportPersonRecord:
    if label is None:
        return ExportPersonRecord(
            tei_id=tei_id,
            person_record_id=uuid4(),
            label=None,
            agreement_tier=AgreementTier.no_answer,
            certainty_tier=CertaintyTier.no_data,
            is_human_reviewed=False,
        )
    return ExportPersonRecord(
        tei_id=tei_id,
        person_record_id=uuid4(),
        label=CanonicalLabel(label),
        evidence="assigned",
        resp="#gendertagger",
        cert="high",
        agreement_tier=AgreementTier.unanimous,
        certainty_tier=CertaintyTier.high,
        is_human_reviewed=False,
    )


def test_gender_element_lands_after_persname_and_before_birth() -> None:
    output = inject_gender_annotations(_SOURCE, {"p1": _record("p1", label="female")})

    root = etree.fromstring(output)
    person = root.find(".//tei:person[@xml:id='p1']", namespaces=_NS)
    assert person is not None
    child_tags = [etree.QName(child).localname for child in person]
    assert child_tags == ["persName", "gender", "birth", "death", "note"]
    gender = person.find("tei:gender", namespaces=_NS)
    assert gender is not None
    assert gender.get("value") == "female"
    assert gender.get("evidence") == "assigned"
    assert gender.get("resp") == "#gendertagger"
    assert gender.get("cert") == "high"


def test_person_without_a_final_label_is_left_untouched() -> None:
    output = inject_gender_annotations(_SOURCE, {"p1": _record("p1", label=None)})

    root = etree.fromstring(output)
    person = root.find(".//tei:person[@xml:id='p1']", namespaces=_NS)
    assert person is not None
    assert person.find("tei:gender", namespaces=_NS) is None


def test_person_absent_from_the_export_selection_is_left_untouched() -> None:
    output = inject_gender_annotations(_SOURCE, {"p1": _record("p1", label="male")})

    root = etree.fromstring(output)
    untouched = root.find(".//tei:person[@xml:id='p2']", namespaces=_NS)
    assert untouched is not None
    assert untouched.find("tei:gender", namespaces=_NS) is None


def test_gender_element_lands_directly_after_person_when_no_birth_death_note() -> None:
    source = f"""<?xml version="1.0" encoding="UTF-8"?>
    <TEI xmlns="{_TEI_NAMESPACE}" xml:id="S1">
      <teiHeader><fileDesc><titleStmt><title>Register</title></titleStmt>
      <publicationStmt><p>-</p></publicationStmt><sourceDesc><p>-</p></sourceDesc></fileDesc></teiHeader>
      <text><body><listPerson>
        <person xml:id="p3">
          <persName type="reg"><surname>Minimal</surname></persName>
        </person>
      </listPerson></body></text>
    </TEI>
    """.encode()

    output = inject_gender_annotations(source, {"p3": _record("p3", label="male")})

    root = etree.fromstring(output)
    person = root.find(".//tei:person[@xml:id='p3']", namespaces=_NS)
    assert person is not None
    child_tags = [etree.QName(child).localname for child in person]
    assert child_tags == ["persName", "gender"]


def test_a_person_missing_from_the_document_raises() -> None:
    with pytest.raises(TeiExportError, match="ghost"):
        inject_gender_annotations(_SOURCE, {"ghost": _record("ghost", label="male")})
