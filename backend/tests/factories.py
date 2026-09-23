"""Factories for canonical test records."""

from typing import Any

from gendertagger.models.person import PersonInput, PersonNameForm, PersonNameType


def tei_person_input(
    *,
    tei_id: str,
    surname: str | None = None,
    forenames: list[str] | None = None,
    alt_names: list[str] | None = None,
    **values: Any,
) -> PersonInput:
    """Build a minimal person consistent with the supported TEI import profile."""
    projected_forenames = forenames or []
    projected_alt_names = alt_names or []
    projected_surname: str | None
    if surname is None and not projected_forenames:
        projected_surname = tei_id
        regular_form = PersonNameForm(type=PersonNameType.regular, name=tei_id)
    else:
        projected_surname = surname
        regular_form = PersonNameForm(
            type=PersonNameType.regular,
            surname=surname,
            forenames=projected_forenames,
        )
    name_forms = [
        regular_form,
        *(
            PersonNameForm(type=PersonNameType.alternative, name=value)
            for value in projected_alt_names
        ),
    ]
    return PersonInput(
        tei_id=tei_id,
        surname=projected_surname,
        forenames=projected_forenames,
        alt_names=projected_alt_names,
        name_forms=name_forms,
        **values,
    )
