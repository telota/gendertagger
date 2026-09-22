"""Cross-document TEI person collection parsing with source provenance."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol, runtime_checkable
from urllib.parse import quote

from gendertagger.ingestion.package import SourceMember
from gendertagger.ingestion.tei import TeiImportError, TeiPersonParser
from gendertagger.models.person import ImportedPerson


@runtime_checkable
class _ClosableIterator(Protocol):
    def close(self) -> None:
        """Close an iterator and any package resources it owns."""
        ...


class TeiCollectionError(TeiImportError):
    """Raised when individually valid TEI members conflict as a collection."""


class TeiCollectionImporter:
    """Apply one versioned TEI parser across a deterministic member sequence."""

    def __init__(self, parser: TeiPersonParser) -> None:
        self._parser = parser

    def iter_people(
        self,
        members: Iterable[SourceMember],
    ) -> Iterator[ImportedPerson]:
        """Yield people and reject canonical TEI IDs repeated across members."""
        seen_tei_ids: dict[str, str] = {}
        member_iterator = iter(members)
        try:
            for member in member_iterator:
                for person in self._parser.iter_people(member.source):
                    previous_member = seen_tei_ids.get(person.tei_id)
                    if previous_member is not None:
                        msg = (
                            f"duplicate TEI xml:id {person.tei_id!r} across source members "
                            f"{previous_member!r} and {member.logical_name!r}"
                        )
                        raise TeiCollectionError(msg)
                    seen_tei_ids[person.tei_id] = member.logical_name
                    yield ImportedPerson(
                        person=person,
                        source_member_name=member.logical_name,
                        source_record_locator=_person_locator(person.tei_id),
                    )
        finally:
            if isinstance(member_iterator, _ClosableIterator):
                member_iterator.close()


def _person_locator(tei_id: str) -> str:
    encoded_id = quote(tei_id, safe="-._~")
    return f"xml:id={encoded_id}"
