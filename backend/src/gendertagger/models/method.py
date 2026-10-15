"""Canonical method metadata contracts."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

METHOD_NAME_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"


class MethodConfidenceRange(BaseModel):
    """Inclusive range for one method's uncalibrated confidence values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def _validate_ordered_bounds(self) -> Self:
        if self.minimum >= self.maximum:
            msg = "method confidence minimum must be less than maximum"
            raise ValueError(msg)
        return self


class MethodDescriptor(BaseModel):
    """Stable scientific and provenance metadata for a method adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(
        pattern=METHOD_NAME_PATTERN,
        description="Stable lowercase snake-case method identifier.",
    )
    implementation_version: str = Field(
        min_length=1,
        description="Version of the adapter implementation used for predictions.",
    )
    normalization_version: str = Field(
        min_length=1,
        description="Version of the adapter-owned raw-label normalization behavior.",
    )
    method_confidence_range: MethodConfidenceRange | None = Field(
        default=None,
        description=(
            "Inclusive range for method-specific confidence values, or null when the method "
            "does not report confidence."
        ),
    )

    @field_validator("implementation_version", "normalization_version")
    @classmethod
    def _validate_nonblank_version(cls, value: str) -> str:
        if not value.strip():
            msg = "method versions must not be blank"
            raise ValueError(msg)
        return value


class RunnableMethod(MethodDescriptor):
    """A registered method as the `/methods` listing reports it, with its current readiness.

    `available` is a deployment fact, not scientific metadata, so it lives here rather than on
    `MethodDescriptor` itself, which run and execution records also embed as immutable provenance.
    """

    available: bool = Field(
        description=(
            "Whether this method can run with no configuration beyond what this deployment "
            "already has in place (a lookup/model asset, or a default the adapter itself "
            "supplies) — not whether the method name is merely registered."
        ),
    )
