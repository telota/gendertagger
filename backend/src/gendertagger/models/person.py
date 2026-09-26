"""Canonical person input and source-name contracts."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gendertagger.models.common import UtcDatetime
from gendertagger.models.project import (
    SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH,
    normalize_source_member_logical_name,
)


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


class PersonEvent(BaseModel):
    """Source-preserved biographical event attached to one person."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str = Field(min_length=1, max_length=100)
    when: str | None = None
    note: str | None = None

    @field_validator("type", "when", "note")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            msg = "person event text fields must not be blank"
            raise ValueError(msg)
        return value


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
    events: list[PersonEvent] = Field(default_factory=list)
    alt_names: list[str] = Field(default_factory=list)
    name_forms: list[PersonNameForm] | None = Field(
        default=None,
        description=(
            "Ordered direct TEI persName forms, or null when structured names were not supplied."
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


class ParsedPerson(BaseModel):
    """One parsed person plus source facts excluded from classification input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    person: PersonInput
    source_gender_values: list[str | None] | None = Field(
        default=None,
        description=(
            "Direct TEI gender @value attributes in document order; an empty list means "
            "none were present, while null means the source profile does not capture them."
        ),
    )


class ImportedPerson(ParsedPerson):
    """One validated person plus its exact source-member record location."""

    source_member_name: str = Field(
        min_length=1,
        max_length=SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH,
    )
    source_record_locator: str = Field(min_length=1)

    @field_validator("source_member_name")
    @classmethod
    def _normalize_source_member_name(cls, value: str) -> str:
        return normalize_source_member_logical_name(value)

    @field_validator("source_record_locator")
    @classmethod
    def _validate_source_record_locator(cls, value: str) -> str:
        if not value.strip():
            msg = "source_record_locator must not be blank"
            raise ValueError(msg)
        return value


class PersonRecord(PersonInput):
    """Canonical read model for one person occurrence in an exact snapshot."""

    id: UUID
    dataset_snapshot_id: UUID
    source_member_name: str | None = Field(
        default=None,
        max_length=SOURCE_MEMBER_LOGICAL_NAME_MAX_LENGTH,
    )
    source_record_locator: str | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_source_provenance(self) -> Self:
        if (self.source_member_name is None) != (self.source_record_locator is None):
            msg = "person-record source provenance fields must be supplied together"
            raise ValueError(msg)
        if self.source_member_name is not None:
            self.source_member_name = normalize_source_member_logical_name(self.source_member_name)
        if self.source_record_locator is not None and not self.source_record_locator.strip():
            msg = "source_record_locator must not be blank"
            raise ValueError(msg)
        return self
