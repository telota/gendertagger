"""Secure, versioned TEI P5 person-register extraction."""

import re
from collections.abc import Iterator
from typing import BinaryIO, cast

from lxml import etree

from gendertagger.ingestion.authority import (
    AuthorityIdentifierError,
    add_external_identifier,
)
from gendertagger.models.person import PersonEvent, PersonInput, PersonNameForm, PersonNameType

TEI_PARSER_VERSION = "tei_parser_v3"
_TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
_PERSON_TAG = f"{{{_TEI_NAMESPACE}}}person"
_PERS_NAME_TAG = f"{{{_TEI_NAMESPACE}}}persName"
_SURNAME_TAG = f"{{{_TEI_NAMESPACE}}}surname"
_FORENAME_TAG = f"{{{_TEI_NAMESPACE}}}forename"
_NAME_TAG = f"{{{_TEI_NAMESPACE}}}name"
_NAME_LINK_TAG = f"{{{_TEI_NAMESPACE}}}nameLink"
_BIRTH_TAG = f"{{{_TEI_NAMESPACE}}}birth"
_DEATH_TAG = f"{{{_TEI_NAMESPACE}}}death"
_NOTE_TAG = f"{{{_TEI_NAMESPACE}}}note"
_IDNO_TAG = f"{{{_TEI_NAMESPACE}}}idno"
_EVENT_TAG = f"{{{_TEI_NAMESPACE}}}event"
_EXTERNAL_ID_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class TeiImportError(ValueError):
    """Raised with a sanitized diagnostic when TEI extraction cannot complete."""


class TeiSourceReadError(TeiImportError):
    """Raised when infrastructure prevents reading the staged TEI source."""


class TeiPersonParser:
    """Extract source-preserving person records from the supported TEI profile."""

    def iter_people(
        self,
        source: BinaryIO,
    ) -> Iterator[PersonInput]:
        """Yield validated people under the secure TEI extraction profile."""
        seen_tei_ids: set[str] = set()
        root_seen = False
        try:
            context = etree.iterparse(
                source,
                events=("start", "end"),
                load_dtd=False,
                no_network=True,
                resolve_entities=False,
                recover=False,
                huge_tree=False,
                remove_comments=False,
                remove_pis=False,
            )
            for event, element in context:
                if not root_seen and event == "start":
                    root_seen = True
                    self._validate_document_root(element)
                if event != "end" or element.tag != _PERSON_TAG:
                    continue
                person = self._extract_person(element)
                if person.tei_id in seen_tei_ids:
                    msg = f"duplicate TEI xml:id {person.tei_id!r}"
                    raise TeiImportError(msg)
                seen_tei_ids.add(person.tei_id)
                yield person
                self._clear_element(element)
        except TeiImportError:
            raise
        except etree.XMLSyntaxError as error:
            msg = f"invalid TEI XML at line {error.lineno}, column {error.position[1]}"
            raise TeiImportError(msg) from error
        except OSError as error:
            msg = "TEI source could not be read"
            raise TeiSourceReadError(msg) from error
        if not root_seen:
            msg = "TEI source is empty"
            raise TeiImportError(msg)

    @classmethod
    def _extract_person(
        cls,
        element: etree._Element,
    ) -> PersonInput:
        """Preserve direct TEI name forms while retaining stable flat projections."""
        tei_id = cls._tei_id(element)
        name_forms = [cls._extract_name_form(name) for name in element.findall(_PERS_NAME_TAG)]
        regular_forms = [
            name_form for name_form in name_forms if name_form.type is PersonNameType.regular
        ]
        if len(regular_forms) != 1:
            msg = f"TEI person {tei_id!r} requires exactly one regular persName"
            raise TeiImportError(msg)

        regular_form = regular_forms[0]
        alt_names = [
            name_form.projected_text()
            for name_form in name_forms
            if name_form.type is PersonNameType.alternative
        ]
        gnd_id, external_ids = cls._external_ids(element)
        return PersonInput(
            tei_id=tei_id,
            surname=regular_form.surname or regular_form.name,
            forenames=regular_form.forenames,
            birth=cls._element_text(element.find(_BIRTH_TAG)),
            death=cls._element_text(element.find(_DEATH_TAG)),
            note=cls._element_text(element.find(_NOTE_TAG)),
            events=[cls._extract_event(event) for event in element.findall(_EVENT_TAG)],
            alt_names=alt_names,
            name_forms=name_forms,
            gnd_id=gnd_id,
            external_ids=external_ids,
        )

    @staticmethod
    def _validate_document_root(root: etree._Element) -> None:
        document = root.getroottree()
        internal_dtd = cast(object | None, document.docinfo.internalDTD)
        external_dtd = cast(object | None, document.docinfo.externalDTD)
        if internal_dtd is not None or external_dtd is not None:
            msg = "TEI documents containing a DOCTYPE are not accepted"
            raise TeiImportError(msg)
        try:
            namespace = etree.QName(root).namespace
        except ValueError as error:
            msg = "TEI document root is invalid"
            raise TeiImportError(msg) from error
        if namespace != _TEI_NAMESPACE:
            msg = "TEI document must use the TEI P5 namespace"
            raise TeiImportError(msg)

    @classmethod
    def _extract_event(cls, element: etree._Element) -> PersonEvent:
        """Preserve one supported direct TEI event without importing nested names."""
        unsupported_attributes = set(element.attrib) - {"type", "when"}
        if unsupported_attributes:
            msg = "direct TEI event contains unsupported attributes"
            raise TeiImportError(msg)

        event_type = (element.get("type") or "").strip()
        if not event_type:
            msg = "direct TEI event requires a non-blank type"
            raise TeiImportError(msg)

        notes = element.findall(_NOTE_TAG)
        child_tags = [cast(object, child.tag) for child in element]
        if any(isinstance(child_tag, str) and child_tag != _NOTE_TAG for child_tag in child_tags):
            msg = "direct TEI event contains unsupported child elements"
            raise TeiImportError(msg)
        if len(notes) > 1:
            msg = "direct TEI event must not contain multiple note elements"
            raise TeiImportError(msg)
        if cls._direct_text(element) is not None:
            msg = "direct TEI event must not contain text outside its note"
            raise TeiImportError(msg)
        if notes and notes[0].attrib:
            msg = "direct TEI event note contains unsupported attributes"
            raise TeiImportError(msg)

        try:
            return PersonEvent(
                type=event_type,
                when=cls._optional_attribute(element, "when"),
                note=cls._element_text(notes[0]) if notes else None,
            )
        except ValueError as error:
            msg = "direct TEI event has invalid source values"
            raise TeiImportError(msg) from error

    @staticmethod
    def _optional_attribute(element: etree._Element, name: str) -> str | None:
        value = element.get(name)
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @classmethod
    def _extract_name_form(cls, element: etree._Element) -> PersonNameForm:
        name_type = element.get("type")
        if name_type not in {PersonNameType.regular.value, PersonNameType.alternative.value}:
            msg = "direct TEI persName requires type 'reg' or 'alt'"
            raise TeiImportError(msg)

        unsupported_attributes = set(element.attrib) - {"type", "subtype"}
        if unsupported_attributes:
            msg = "direct TEI persName contains unsupported attributes"
            raise TeiImportError(msg)

        supported_tags = {_NAME_TAG, _SURNAME_TAG, _FORENAME_TAG, _NAME_LINK_TAG}
        child_tags = (cast(object, child.tag) for child in element)
        if any(
            isinstance(child_tag, str) and child_tag not in supported_tags
            for child_tag in child_tags
        ):
            msg = "direct TEI persName contains unsupported child elements"
            raise TeiImportError(msg)

        name_links = element.findall(_NAME_LINK_TAG)
        if any(
            name_link.attrib or len(name_link) or cls._element_text(name_link) is not None
            for name_link in name_links
        ):
            msg = "non-empty TEI nameLink is not supported by this import profile"
            raise TeiImportError(msg)

        unstructured_names = element.findall(_NAME_TAG)
        if len(unstructured_names) > 1:
            msg = "a direct TEI persName must not contain multiple name elements"
            raise TeiImportError(msg)
        surnames = element.findall(_SURNAME_TAG)
        if len(surnames) > 1:
            msg = "a direct TEI persName must not contain multiple surname elements"
            raise TeiImportError(msg)
        forenames_elements = element.findall(_FORENAME_TAG)
        if any(
            component.attrib for component in (*unstructured_names, *surnames, *forenames_elements)
        ):
            msg = "direct TEI name components contain unsupported attributes"
            raise TeiImportError(msg)
        for component in (*unstructured_names, *surnames, *forenames_elements):
            cls._validate_name_component_markup(component)

        direct_text = cls._direct_text(element)
        component_count = len(unstructured_names) + len(surnames) + len(forenames_elements)
        if direct_text is not None and component_count:
            msg = "a component-based TEI persName must not contain direct text"
            raise TeiImportError(msg)

        name = cls._element_text(unstructured_names[0]) if unstructured_names else direct_text
        surname = cls._element_text(surnames[0]) if surnames else None
        forenames = [
            text
            for forename in forenames_elements
            if (text := cls._element_text(forename)) is not None
        ]
        try:
            return PersonNameForm(
                type=PersonNameType(name_type),
                subtype=element.get("subtype"),
                name=name,
                surname=surname,
                forenames=forenames,
            )
        except ValueError as error:
            msg = "direct TEI persName has an invalid name representation"
            raise TeiImportError(msg) from error

    @staticmethod
    def _direct_text(element: etree._Element) -> str | None:
        raw_text = " ".join((element.text or "", *(child.tail or "" for child in element)))
        text = " ".join(raw_text.split())
        return text or None

    @classmethod
    def _validate_name_component_markup(cls, component: etree._Element) -> None:
        """Accept only inline name markup represented by the supported corpus profile."""
        for descendant in component.iterdescendants():
            descendant_tag = cast(object, descendant.tag)
            if not isinstance(descendant_tag, str):
                continue
            if descendant_tag == _NAME_TAG:
                if set(descendant.attrib) - {"type"}:
                    msg = "TEI name component inline name contains unsupported attributes"
                    raise TeiImportError(msg)
                continue
            if descendant_tag == _PERS_NAME_TAG:
                if set(descendant.attrib) - {"key"}:
                    msg = "TEI name component inline persName contains unsupported attributes"
                    raise TeiImportError(msg)
                continue
            if descendant_tag == _NAME_LINK_TAG:
                if (
                    descendant.attrib
                    or len(descendant)
                    or cls._element_text(descendant) is not None
                ):
                    msg = "non-empty TEI nameLink is not supported by this import profile"
                    raise TeiImportError(msg)
                continue
            msg = "TEI name component contains unsupported descendant elements"
            raise TeiImportError(msg)

    @staticmethod
    def _tei_id(element: etree._Element) -> str:
        tei_id = (element.get(_XML_ID) or "").strip()
        if not tei_id:
            msg = "every TEI person requires a non-blank xml:id"
            raise TeiImportError(msg)
        return tei_id

    @classmethod
    def _external_ids(cls, element: etree._Element) -> tuple[str | None, dict[str, str]]:
        """Apply strict shared authority normalization."""
        identifiers: dict[str, str] = {}
        for identifier in element.findall(_IDNO_TAG):
            value = cls._element_text(identifier)
            if value is None:
                continue
            try:
                add_external_identifier(
                    identifiers,
                    identifier_type=identifier.get("type") or "",
                    value=value,
                )
            except AuthorityIdentifierError as error:
                msg = f"direct TEI idno is invalid: {error}"
                raise TeiImportError(msg) from error
        gnd_id = identifiers.pop("gnd", None)
        external_ids = identifiers
        return gnd_id, external_ids

    @staticmethod
    def _element_text(element: etree._Element | None) -> str | None:
        if element is None:
            return None
        parts = [
            part.decode("utf-8") if isinstance(part, bytes) else part for part in element.itertext()
        ]
        raw_text = ""
        for part in parts:
            if not part:
                continue
            if (
                not raw_text
                or raw_text[-1].isspace()
                or part[0].isspace()
                or part[0] in ",.;:!?)]}"
                or raw_text[-1] in "([{"
            ):
                raw_text += part
            else:
                raw_text += f" {part}"
        text = " ".join(raw_text.split())
        return text or None

    @staticmethod
    def _clear_element(element: etree._Element) -> None:
        parent = element.getparent()
        tail = element.tail
        element.clear()
        element.tail = tail
        if parent is None:
            return
        while element.getprevious() is not None:
            del parent[0]
