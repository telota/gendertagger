"""Secure, versioned TEI P5 person-register extraction."""

import re
from collections.abc import Iterator
from typing import BinaryIO, cast
from urllib.parse import urlparse

from lxml import etree

from gendertagger.models.person import PersonInput, PersonNameForm, PersonNameType
from gendertagger.models.project import DEFAULT_TEI_IMPORT_PROFILE, TeiImportProfile

TEI_PARSER_V1_VERSION = "tei_parser_v1"
TEI_PARSER_VERSION = "tei_parser_v2"
_TEI_PROFILE_VERSIONS = {
    TeiImportProfile.tei_p5_person_register_v1: TEI_PARSER_V1_VERSION,
    TeiImportProfile.tei_p5_person_register_v2: TEI_PARSER_VERSION,
}
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
_EXTERNAL_ID_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class TeiImportError(ValueError):
    """Raised with a sanitized diagnostic when TEI extraction cannot complete."""


class TeiPersonParser:
    """Extract source-preserving person records under versioned TEI profiles."""

    profile = DEFAULT_TEI_IMPORT_PROFILE

    def iter_people(
        self,
        source: BinaryIO,
        *,
        profile: TeiImportProfile | None = None,
    ) -> Iterator[PersonInput]:
        """Yield validated people under one selected secure extraction profile."""
        resolved_profile = profile or self.profile
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
                person = self._extract_person(element, profile=resolved_profile)
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
            raise TeiImportError(msg) from error
        if not root_seen:
            msg = "TEI source is empty"
            raise TeiImportError(msg)

    @classmethod
    def version_for_profile(cls, profile: TeiImportProfile) -> str:
        """Return the parser implementation recorded for one import profile."""
        try:
            return _TEI_PROFILE_VERSIONS[profile]
        except KeyError as error:
            msg = f"unsupported TEI import profile {profile!r}"
            raise ValueError(msg) from error

    @classmethod
    def _extract_person(
        cls,
        element: etree._Element,
        *,
        profile: TeiImportProfile,
    ) -> PersonInput:
        extractors = {
            TeiImportProfile.tei_p5_person_register_v1: cls._extract_person_v1,
            TeiImportProfile.tei_p5_person_register_v2: cls._extract_person_v2,
        }
        try:
            extractor = extractors[profile]
        except KeyError as error:
            msg = f"unsupported TEI import profile {profile!r}"
            raise TeiImportError(msg) from error
        return extractor(element)

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
    def _extract_person_v1(cls, element: etree._Element) -> PersonInput:
        """Reproduce the original flattened person-name extraction behavior."""
        tei_id = cls._tei_id(element)
        regular_name = next(
            (name for name in element.findall(_PERS_NAME_TAG) if name.get("type") == "reg"),
            None,
        )
        surname: str | None = None
        forenames: list[str] = []
        if regular_name is not None:
            surname = cls._element_text(regular_name.find(_SURNAME_TAG))
            forenames = [
                text
                for forename in regular_name.findall(_FORENAME_TAG)
                if (text := cls._element_text(forename)) is not None
            ]
            if surname is None and not forenames:
                surname = cls._element_text(regular_name.find(_NAME_TAG))

        alt_names = [
            text
            for name in element.findall(_PERS_NAME_TAG)
            if name.get("type") == "alt"
            if (text := cls._element_text(name)) is not None
        ]
        gnd_id, external_ids = cls._external_ids_v1(element)
        return PersonInput(
            tei_id=tei_id,
            surname=surname,
            forenames=forenames,
            birth=cls._element_text(element.find(_BIRTH_TAG)),
            death=cls._element_text(element.find(_DEATH_TAG)),
            note=cls._element_text(element.find(_NOTE_TAG)),
            alt_names=alt_names,
            gnd_id=gnd_id,
            external_ids=external_ids,
        )

    @classmethod
    def _extract_person_v2(cls, element: etree._Element) -> PersonInput:
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
        gnd_id, external_ids = cls._external_ids_v2(element)
        return PersonInput(
            tei_id=tei_id,
            surname=regular_form.surname or regular_form.name,
            forenames=regular_form.forenames,
            birth=cls._element_text(element.find(_BIRTH_TAG)),
            death=cls._element_text(element.find(_DEATH_TAG)),
            note=cls._element_text(element.find(_NOTE_TAG)),
            alt_names=alt_names,
            name_forms=name_forms,
            gnd_id=gnd_id,
            external_ids=external_ids,
        )

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

    @staticmethod
    def _tei_id(element: etree._Element) -> str:
        tei_id = (element.get(_XML_ID) or "").strip()
        if not tei_id:
            msg = "every TEI person requires a non-blank xml:id"
            raise TeiImportError(msg)
        return tei_id

    @classmethod
    def _external_ids_v1(cls, element: etree._Element) -> tuple[str | None, dict[str, str]]:
        """Reproduce the original authority-identifier projection."""
        gnd_id: str | None = None
        external_ids: dict[str, str] = {}
        for identifier in element.findall(_IDNO_TAG):
            value = cls._element_text(identifier)
            if value is None:
                continue
            identifier_type = (identifier.get("type") or "").strip().lower().replace("-", "_")
            parsed_uri = urlparse(value)
            if identifier_type == "gnd" or "d-nb.info/gnd/" in value:
                candidate = parsed_uri.path.rstrip("/").rsplit("/", maxsplit=1)[-1] or value
                if gnd_id is None:
                    gnd_id = candidate
                continue
            if "wikidata.org/" in value:
                external_ids.setdefault(
                    "wikidata",
                    parsed_uri.path.rstrip("/").rsplit("/", maxsplit=1)[-1],
                )
                continue
            if identifier_type != "uri" and _EXTERNAL_ID_SCHEME_PATTERN.fullmatch(identifier_type):
                external_ids.setdefault(identifier_type, value)
        return gnd_id, external_ids

    @classmethod
    def _external_ids_v2(cls, element: etree._Element) -> tuple[str | None, dict[str, str]]:
        """Recognize typed IDs plus GND, Wikidata, and VIAF URI variants."""
        gnd_id, external_ids = cls._external_ids_v1(element)
        for identifier in element.findall(_IDNO_TAG):
            value = cls._element_text(identifier)
            if value is None:
                continue
            compact_value = "".join(value.split())
            parsed_uri = urlparse(compact_value)
            hostname = (parsed_uri.hostname or "").lower()
            candidate = parsed_uri.path.rstrip("/").rsplit("/", maxsplit=1)[-1]
            if gnd_id is None and hostname in {"d-nb.info", "www.d-nb.info"} and candidate:
                gnd_id = candidate
                continue
            if hostname in {"viaf.org", "www.viaf.org"} and candidate:
                external_ids.setdefault("viaf", candidate)
        return gnd_id, external_ids

    @staticmethod
    def _element_text(element: etree._Element | None) -> str | None:
        if element is None:
            return None
        raw_text = "".join(
            part.decode("utf-8") if isinstance(part, bytes) else part for part in element.itertext()
        )
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
