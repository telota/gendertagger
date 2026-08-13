"""Canonical person input contracts."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    gnd_id: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)

    @field_validator("tei_id")
    @classmethod
    def _validate_tei_id(cls, value: str) -> str:
        if not value.strip():
            msg = "tei_id must not be empty"
            raise ValueError(msg)
        return value
