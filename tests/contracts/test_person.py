from __future__ import annotations

import pytest
from pydantic import ValidationError

from gendertagger.models.person import PersonInput

pytestmark = pytest.mark.contract


def test_person_input_minimal_payload_uses_isolated_defaults() -> None:
    first = PersonInput(tei_id="person-1")
    second = PersonInput(tei_id="person-2")

    first.forenames.append("Anna")
    first.alt_names.append("A. Example")
    first.external_ids["wikidata"] = "Q1"

    assert second.model_dump() == {
        "tei_id": "person-2",
        "surname": None,
        "forenames": [],
        "birth": None,
        "death": None,
        "note": None,
        "alt_names": [],
        "gnd_id": None,
        "external_ids": {},
    }


def test_person_input_round_trip_preserves_historical_source_strings() -> None:
    payload = {
        "tei_id": "person-Ä.17",
        "surname": "d'Arcy",
        "forenames": ["Anne-Marie", "Élise"],
        "birth": "um 1770?",
        "death": "nach 1832",
        "note": "Genannt „Lise“; Datierung unsicher.",
        "alt_names": ["Anne Marie d'Arcy", "Lise"],
        "gnd_id": "118540238",
        "external_ids": {"wikidata": "Q123", "local_register": "A/17"},
    }

    person = PersonInput.model_validate(payload)
    restored = PersonInput.model_validate_json(person.model_dump_json())

    assert person.model_dump(mode="json") == payload
    assert restored == person


@pytest.mark.parametrize("tei_id", ["", " ", "\t\n"])
def test_person_input_rejects_blank_tei_id(tei_id: str) -> None:
    with pytest.raises(ValidationError):
        PersonInput(tei_id=tei_id)


def test_person_input_rejects_missing_tei_id_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PersonInput.model_validate({})

    with pytest.raises(ValidationError):
        PersonInput.model_validate({"tei_id": "person-1", "xml_id": "legacy-id"})


def test_person_input_json_schema_exposes_stable_public_shape() -> None:
    schema = PersonInput.model_json_schema()

    assert set(schema["properties"]) == {
        "tei_id",
        "surname",
        "forenames",
        "birth",
        "death",
        "note",
        "alt_names",
        "gnd_id",
        "external_ids",
    }
    assert schema["required"] == ["tei_id"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["tei_id"]["minLength"] == 1
