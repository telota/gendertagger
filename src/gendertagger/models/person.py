"""Canonical person input and source-name contracts."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gendertagger.models.common import UtcDatetime


class PersonNameType(StrEnum):
    """Supported direct TEI ``persName`` roles in the person-register profile."""

    regular = "reg"
    alternative = "alt"


class PersonNameForm(BaseModel):
    """Source-rich projection of one direct TEI ``persName`` in document order.

    A name form uses either an unstructured value (from TEI ``name`` or direct
    ``persName`` text) or structured ``surname`` and ``forename`` components.
    Inline markup remains preserved by the immutable source artifact; component
    text is normalized only for whitespace by the import profile.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: PersonNameType
    subtype: str | None = Field(default=None, max_length=100)
    name: str | None = None
    surname: str | None = None
    forenames: list[str] = Field(default_factory=list)

    @field_validator("subtype", "name", "surname")
    @classmethod
    def _validate_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            msg = "person name-form text fields must not be blank"
            raise ValueError(msg)
        return value

    @field_validator("forenames")
    @classmethod
    def _validate_forenames(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            msg = "person name-form forenames must not contain blank values"
            raise ValueError(msg)
        return values

    @model_validator(mode="after")
    def _validate_representation(self) -> Self:
        has_unstructured_name = self.name is not None
        has_structured_name = self.surname is not None or bool(self.forenames)
        if has_unstructured_name == has_structured_name:
            msg = "a person name form requires exactly one name representation"
            raise ValueError(msg)
        return self

    def projected_text(self) -> str:
        """Return the stable flat text used by compatibility/search projections."""
        if self.name is not None:
            return self.name
        return " ".join(value for value in (self.surname, *self.forenames) if value is not None)


class PersonInput(BaseModel):
    """Source-preserving person data supplied to classification methods."""

    model_config = ConfigDict(extra="forbid")

    tei_id: str = Field(
        min_length=1,
        description="Non-blank TEI xml:id identifying the person within its project.",
    )
    surname: str | None = None
    forenames: list[str] = Field(default_factory=list)
    birth: str | None = None
    death: str | None = None
    note: str | None = None
    alt_names: list[str] = Field(default_factory=list)
    name_forms: list[PersonNameForm] | None = Field(
        default=None,
        description=(
            "Ordered direct TEI persName forms, or null when the import profile did not "
            "capture structured names."
        ),
    )
    gnd_id: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)

    @field_validator("tei_id")
    @classmethod
    def _validate_tei_id(cls, value: str) -> str:
        if not value.strip():
            msg = "tei_id must not be empty"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_name_projections(self) -> Self:
        if self.name_forms is None:
            return self

        regular_forms = [
            name_form for name_form in self.name_forms if name_form.type is PersonNameType.regular
        ]
        if len(regular_forms) != 1:
            msg = "captured person name forms require exactly one regular form"
            raise ValueError(msg)

        regular_form = regular_forms[0]
        expected_surname = regular_form.surname or regular_form.name
        expected_alt_names = [
            name_form.projected_text()
            for name_form in self.name_forms
            if name_form.type is PersonNameType.alternative
        ]
        if self.surname != expected_surname:
            msg = "surname must match the captured regular name form"
            raise ValueError(msg)
        if self.forenames != regular_form.forenames:
            msg = "forenames must match the captured regular name form"
            raise ValueError(msg)
        if self.alt_names != expected_alt_names:
            msg = "alt_names must match the captured alternative name forms"
            raise ValueError(msg)
        return self


class PersonRecord(PersonInput):
    """Canonical read model for one person occurrence in an exact snapshot."""

    id: UUID
    dataset_snapshot_id: UUID
    created_at: UtcDatetime
