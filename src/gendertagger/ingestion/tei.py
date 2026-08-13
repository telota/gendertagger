"""Secure, versioned TEI P5 person-register extraction."""

import re
from collections.abc import Iterator
from typing import BinaryIO, cast
from urllib.parse import urlparse

from lxml import etree

from gendertagger.models.person import PersonInput
from gendertagger.models.project import TeiImportProfile

TEI_PARSER_VERSION = "tei_parser_v1"
_TEI_NAMESPACE = "http://www.tei-c.org/ns/1.0"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
_PERSON_TAG = f"{{{_TEI_NAMESPACE}}}person"
_PERS_NAME_TAG = f"{{{_TEI_NAMESPACE}}}persName"
_SURNAME_TAG = f"{{{_TEI_NAMESPACE}}}surname"
_FORENAME_TAG = f"{{{_TEI_NAMESPACE}}}forename"
_NAME_TAG = f"{{{_TEI_NAMESPACE}}}name"
_BIRTH_TAG = f"{{{_TEI_NAMESPACE}}}birth"
_DEATH_TAG = f"{{{_TEI_NAMESPACE}}}death"
_NOTE_TAG = f"{{{_TEI_NAMESPACE}}}note"
_IDNO_TAG = f"{{{_TEI_NAMESPACE}}}idno"
_EXTERNAL_ID_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class TeiImportError(ValueError):
    """Raised with a sanitized diagnostic when TEI extraction cannot complete."""


class TeiPersonParser:
    """Extract source-preserving person records under one fixed TEI profile."""

    version = TEI_PARSER_VERSION
    profile = TeiImportProfile.tei_p5_person_register_v1

    def iter_people(self, source: BinaryIO) -> Iterator[PersonInput]:
        """Yield validated people while disabling dangerous XML parser features."""
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
            raise TeiImportError(msg) from error
        if not root_seen:
            msg = "TEI source is empty"
            raise TeiImportError(msg)

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
    def _extract_person(cls, element: etree._Element) -> PersonInput:
        tei_id = (element.get(_XML_ID) or "").strip()
        if not tei_id:
            msg = "every TEI person requires a non-blank xml:id"
            raise TeiImportError(msg)

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
        gnd_id, external_ids = cls._external_ids(element)
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
    def _external_ids(cls, element: etree._Element) -> tuple[str | None, dict[str, str]]:
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
