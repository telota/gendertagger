from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import JsonValue

from gendertagger.models.common import canonical_json_sha256
from gendertagger.models.person import (
    PersonEvent,
    PersonInput,
    PersonNameForm,
    PersonNameType,
    PersonRecord,
)
from gendertagger.services.execution import _person_input_fingerprint

pytestmark = pytest.mark.unit

PERSON_ID = UUID("40000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
CREATED_AT = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)


def _person(**overrides: object) -> PersonRecord:
    payload: dict[str, object] = {
        "id": PERSON_ID,
        "dataset_snapshot_id": SNAPSHOT_ID,
        "created_at": CREATED_AT,
        "tei_id": "p1",
        "surname": "Example",
        "forenames": ["Anna"],
        "birth": None,
        "death": None,
        "note": None,
        "alt_names": [],
        "name_forms": None,
        "gnd_id": None,
        "external_ids": {},
    }
    payload.update(overrides)
    return PersonRecord.model_validate(payload)


def test_legacy_name_metadata_keeps_the_original_input_fingerprint() -> None:
    person = _person()
    historical_payload: JsonValue = {
        "tei_id": "p1",
        "surname": "Example",
        "forenames": ["Anna"],
        "birth": None,
        "death": None,
        "note": None,
        "alt_names": [],
        "gnd_id": None,
        "external_ids": {},
    }

    assert _person_input_fingerprint(person) == canonical_json_sha256(historical_payload)


def test_structured_name_forms_participate_in_the_input_fingerprint() -> None:
    legacy_person = _person()
    structured_person = _person(
        name_forms=[
            PersonNameForm(
                type=PersonNameType.regular,
                surname="Example",
                forenames=["Anna"],
            )
        ]
    )
    structured_payload = structured_person.model_dump(
        mode="json",
        include={
            "tei_id",
            "surname",
            "forenames",
            "birth",
            "death",
            "note",
            "alt_names",
            "name_forms",
            "gnd_id",
            "external_ids",
        },
    )

    assert _person_input_fingerprint(structured_person) == canonical_json_sha256(structured_payload)
    assert _person_input_fingerprint(structured_person) != _person_input_fingerprint(legacy_person)


def test_nonempty_events_participate_in_the_input_fingerprint() -> None:
    without_event = _person()
    with_event = _person(events=[PersonEvent(type="wedding", when="1832-09-20")])
    event_payload = with_event.model_dump(
        mode="json",
        include=set(PersonInput.model_fields),
    )
    event_payload.pop("name_forms")

    assert _person_input_fingerprint(with_event) == canonical_json_sha256(event_payload)
    assert _person_input_fingerprint(with_event) != _person_input_fingerprint(without_event)
