from datetime import UTC, datetime
from uuid import UUID

import pytest

from gendertagger.models.person import (
    PersonEvent,
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


def test_current_input_fingerprint_includes_nulls_and_empty_defaults() -> None:
    expected = "4a6d078ba8ae729059ddcfd396ef9c4dcee5160715f35e81a1d205a6f8110a19"

    assert _person_input_fingerprint(_person()) == expected
    assert _person_input_fingerprint(_person(events=[], name_forms=None)) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tei_id", "p2"),
        ("surname", "Different"),
        ("forenames", ["Marie"]),
        ("birth", "1800-01-01"),
        ("death", "1870-01-01"),
        ("note", "Source-preserved biographical note"),
        ("events", [PersonEvent(type="wedding", when="1832-09-20")]),
        ("alt_names", ["Anna Alias"]),
        (
            "name_forms",
            [
                PersonNameForm(
                    type=PersonNameType.regular,
                    surname="Example",
                    forenames=["Anna"],
                )
            ],
        ),
        ("gnd_id", "118540238"),
        ("external_ids", {"wikidata": "Q123"}),
    ],
)
def test_every_canonical_input_field_is_significant(field: str, value: object) -> None:
    original = _person()
    changed = _person(**{field: value})

    assert _person_input_fingerprint(changed) != _person_input_fingerprint(original)


@pytest.mark.parametrize(
    ("field", "values", "other_fields"),
    [
        ("forenames", ["Anna", "Marie"], {}),
        ("alt_names", ["Anna Alias", "Marie Alias"], {}),
        (
            "events",
            [
                PersonEvent(type="wedding", when="1832-09-20"),
                PersonEvent(type="appointment", note="Court appointment"),
            ],
            {},
        ),
        (
            "name_forms",
            [
                PersonNameForm(
                    type=PersonNameType.regular,
                    surname="Example",
                    forenames=["Anna"],
                ),
                PersonNameForm(type=PersonNameType.alternative, name="Anna Alias"),
            ],
            {"alt_names": ["Anna Alias"]},
        ),
    ],
)
def test_ordered_input_collections_are_significant(
    field: str, values: list[object], other_fields: dict[str, object]
) -> None:
    original = _person(**other_fields, **{field: values})
    reordered = _person(**other_fields, **{field: list(reversed(values))})

    assert _person_input_fingerprint(reordered) != _person_input_fingerprint(original)


def test_external_identifier_object_key_order_is_insignificant() -> None:
    original = _person(external_ids={"wikidata": "Q123", "viaf": "456"})
    reordered = _person(external_ids={"viaf": "456", "wikidata": "Q123"})

    assert _person_input_fingerprint(reordered) == _person_input_fingerprint(original)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", UUID("40000000-0000-0000-0000-000000000002")),
        ("dataset_snapshot_id", UUID("20000000-0000-0000-0000-000000000002")),
        ("source_member_name", "other.xml"),
        ("source_record_locator", "2"),
        ("created_at", datetime(2026, 8, 15, 10, 0, tzinfo=UTC)),
    ],
)
def test_persistence_and_source_occurrence_fields_are_excluded(field: str, value: object) -> None:
    provenance: dict[str, object] = {
        "source_member_name": "source.xml",
        "source_record_locator": "1",
    }
    original = _person(**provenance)
    changed = _person(**(provenance | {field: value}))

    assert _person_input_fingerprint(changed) == _person_input_fingerprint(original)


def test_source_locator_presence_does_not_change_input_fingerprint() -> None:
    unlocated = _person()
    located = _person(source_member_name="source.xml", source_record_locator="1")

    assert _person_input_fingerprint(located) == _person_input_fingerprint(unlocated)
