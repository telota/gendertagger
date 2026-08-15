"""Pure ``tei_p5_gender_v1`` export profile: inject ``<gender>`` annotations.

Operates on one member's exact immutable source bytes and returns a new,
derived document. The original artifact is never mutated in place.
"""

from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import cast

from lxml import etree

from gendertagger.models.export import ExportPersonRecord

TEI_EXPORT_PROFILE_VERSION = "tei_p5_gender_v1"

_TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
_PERSON_TAG = f"{{{_TEI_NAMESPACE}}}person"
_PERS_NAME_TAG = f"{{{_TEI_NAMESPACE}}}persName"
_GENDER_TAG = f"{{{_TEI_NAMESPACE}}}gender"


class TeiExportError(ValueError):
    """Raised when a labeled person cannot be located in its source member."""


def inject_gender_annotations(
    source_xml: bytes,
    records_by_tei_id: Mapping[str, ExportPersonRecord],
) -> bytes:
    """Return one member's bytes with a ``<gender>`` element per labeled person.

    A person absent from ``records_by_tei_id``, or present with ``label`` set
    to ``None`` (no usable decision), is left exactly as in the source. The
    inserted element lands after the last ``<persName>`` and before
    ``<birth>``/``<death>``/``<note>``, per the reference TEI export shape.

    Args:
        source_xml: The exact immutable bytes of one TEI source member.
        records_by_tei_id: Every person in this member with a resolved
            FinalDecision projection.

    Returns:
        A new, serialized TEI document. The source bytes are never mutated.

    Raises:
        TeiExportError: If a labeled person's ``xml:id`` is not present in
            this document.
    """
    parser = etree.XMLParser(
        load_dtd=False,
        no_network=True,
        resolve_entities=False,
        recover=False,
        huge_tree=False,
        remove_comments=False,
        remove_pis=False,
    )
    tree = etree.parse(BytesIO(source_xml), parser)
    root = tree.getroot()

    found_tei_ids: set[str] = set()
    for person_element in root.iter(_PERSON_TAG):
        tei_id = person_element.get(_XML_ID)
        if tei_id is None:
            continue
        record = records_by_tei_id.get(tei_id)
        if record is None:
            continue
        found_tei_ids.add(tei_id)
        if record.label is None:
            continue
        _insert_gender_element(person_element, record)

    labeled_tei_ids = {
        tei_id for tei_id, record in records_by_tei_id.items() if record.label is not None
    }
    missing = labeled_tei_ids - found_tei_ids
    if missing:
        msg = f"person records not found in source member: {', '.join(sorted(missing))}"
        raise TeiExportError(msg)

    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8")


def _insert_gender_element(
    person_element: etree._Element,
    record: ExportPersonRecord,
) -> None:
    # ExportPersonRecord's own validator guarantees resp/cert are set whenever
    # label is set; the caller only invokes this for labeled records.
    gender_element = etree.Element(_GENDER_TAG)
    gender_element.set("value", cast(str, record.label))
    gender_element.set("evidence", "assigned")
    gender_element.set("resp", cast(str, record.resp))
    gender_element.set("cert", cast(str, record.cert))

    persname_elements = person_element.findall(_PERS_NAME_TAG)
    insert_index = list(person_element).index(persname_elements[-1]) + 1 if persname_elements else 0
    person_element.insert(insert_index, gender_element)
