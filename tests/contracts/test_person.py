from __future__ import annotations

import pytest
from pydantic import ValidationError

from gendertagger.models.person import PersonInput, PersonNameForm, PersonNameType

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
        "name_forms": None,
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
        "name_forms": None,
        "gnd_id": "118540238",
        "external_ids": {"wikidata": "Q123", "local_register": "A/17"},
    }

    person = PersonInput.model_validate(payload)
    restored = PersonInput.model_validate_json(person.model_dump_json())

    assert person.model_dump(mode="json") == payload
    assert restored == person


def test_person_name_form_defaults_are_isolated() -> None:
    first = PersonNameForm(type=PersonNameType.regular, surname="Example")
    second = PersonNameForm(type=PersonNameType.regular, surname="Sample")

    first.forenames.append("Anna")

    assert second.forenames == []


def test_person_name_forms_round_trip_preserves_structure_and_order() -> None:
    payload: dict[str, object] = {
        "tei_id": "person-1",
        "surname": "Example",
        "forenames": ["Anna"],
        "birth": None,
        "death": None,
        "note": None,
        "alt_names": ["Sample Anna", "Origin"],
        "name_forms": [
            {
                "type": "reg",
                "subtype": None,
                "name": None,
                "surname": "Example",
                "forenames": ["Anna"],
            },
            {
                "type": "alt",
                "subtype": None,
                "name": None,
                "surname": "Sample",
                "forenames": ["Anna"],
            },
            {
                "type": "alt",
                "subtype": "birthname",
                "name": "Origin",
                "surname": None,
                "forenames": [],
            },
        ],
        "gnd_id": None,
        "external_ids": {},
    }

    person = PersonInput.model_validate(payload)
    restored = PersonInput.model_validate_json(person.model_dump_json())

    assert person.model_dump(mode="json") == payload
    assert restored == person


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "reg"},
        {"type": "alt", "name": "Alias", "surname": "Example"},
        {"type": "alt", "name": "Alias", "forenames": ["Anna"]},
        {"type": "other", "name": "Alias"},
        {"type": "alt", "name": "Alias", "unknown": True},
    ],
)
def test_person_name_form_rejects_invalid_contracts(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PersonNameForm.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "alt", "name": " "},
        {"type": "alt", "surname": "\t"},
        {"type": "alt", "surname": "Example", "forenames": [""]},
        {"type": "alt", "subtype": "\n", "name": "Alias"},
    ],
)
def test_person_name_form_rejects_blank_components(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PersonNameForm.model_validate(payload)


def test_person_name_form_preserves_an_open_source_subtype_for_either_type() -> None:
    regular = PersonNameForm(type=PersonNameType.regular, subtype="indexed", name="Alias")
    alternative = PersonNameForm(
        type=PersonNameType.alternative,
        subtype="project_specific",
        name="Alias",
    )

    assert regular.subtype == "indexed"
    assert alternative.subtype == "project_specific"


@pytest.mark.parametrize(
    "overrides",
    [
        {"name_forms": [PersonNameForm(type=PersonNameType.alternative, name="Alias")]},
        {
            "name_forms": [
                PersonNameForm(type=PersonNameType.regular, surname="Example"),
                PersonNameForm(type=PersonNameType.regular, surname="Example"),
            ]
        },
        {"surname": "Other"},
        {"forenames": ["Else"]},
        {"alt_names": ["Different alias"]},
    ],
)
def test_person_input_requires_name_forms_to_match_flat_projections(
    overrides: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "tei_id": "person-1",
        "surname": "Example",
        "forenames": ["Anna"],
        "alt_names": ["Alias"],
        "name_forms": [
            PersonNameForm(
                type=PersonNameType.regular,
                surname="Example",
                forenames=["Anna"],
            ),
            PersonNameForm(type=PersonNameType.alternative, name="Alias"),
        ],
    }
    payload.update(overrides)

    with pytest.raises(ValidationError):
        PersonInput.model_validate(payload)


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
        "name_forms",
        "gnd_id",
        "external_ids",
    }
    assert schema["required"] == ["tei_id"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["tei_id"]["minLength"] == 1
