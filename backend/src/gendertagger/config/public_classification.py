"""Deployment-owned method exposure and bounded anonymous execution policy."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from gendertagger.models.method import METHOD_NAME_PATTERN

QUICK_PUBLIC_CLASSIFICATION_METHODS = frozenset({"gender_guesser", "parenthetical_qualifier"})


class PublicClassificationPolicy(BaseModel):
    """Allowlisted methods and operator-controlled configurations for anonymous classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    methods: list[str] = Field(
        default_factory=lambda: ["gender_guesser", "nomquamgender", "parenthetical_qualifier"],
        min_length=1,
        max_length=20,
    )
    method_configs: dict[str, dict[str, JsonValue]] = Field(default_factory=dict, repr=False)
    method_revisions: dict[str, str] = Field(default_factory=dict)
    synchronous_batch_size: int = Field(default=20, ge=1, le=20)
    job_lease_seconds: int = Field(default=3600, ge=60, le=86_400)

    @field_validator("methods")
    @classmethod
    def _validate_methods(cls, values: list[str]) -> list[str]:
        import re

        if len(values) != len(set(values)) or any(
            re.fullmatch(METHOD_NAME_PATTERN, value) is None for value in values
        ):
            msg = "public methods must be distinct snake-case identifiers"
            raise ValueError(msg)
        return values
