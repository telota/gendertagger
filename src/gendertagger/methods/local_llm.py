"""Adapter for OpenAI-compatible LLMs using a minimal httpx wrapper."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field, ValidationError

from gendertagger.methods.base import (
    GenderMethod,
    MethodConfig,
    MethodDependencyError,
    validate_prediction_batch,
)
from gendertagger.methods.normalization import LOCAL_LLM_NORMALIZATION, normalize_raw_label
from gendertagger.models.classification import PredictionResult, PredictionStatus
from gendertagger.models.method import MethodConfidenceRange, MethodDescriptor
from gendertagger.models.person import PersonInput

LOCAL_LLM_DESCRIPTOR = MethodDescriptor(
    name="local_llm",
    implementation_version="local_llm_v1",
    normalization_version=LOCAL_LLM_NORMALIZATION.normalization_version,
    method_confidence_range=MethodConfidenceRange(minimum=0.0, maximum=1.0),
)


class LocalLlmConfig(MethodConfig):
    """Configuration for the Local LLM method."""

    model: str = Field(description="The name of the LLM model to request.")
    base_url: str = Field(description="Base URL for the OpenAI-compatible API.")
    api_key: str = Field(default="ollama", description="API key to use.")
    system_prompt: str | None = Field(
        default="You are an expert archivist identifying the gender of historical persons.",
        description="Optional system prompt to prepend to messages.",
    )
    temperature: float = Field(default=0.0, description="Temperature for the generation.")
    max_validation_retries: int = Field(
        default=2, description="Maximum number of times to retry on a validation failure."
    )


class PersonClassification(BaseModel):
    """Structured output expected from the LLM."""

    gender: Literal["female", "male", "institution", "unknown"]
    confidence: float
    certainty: Literal["high", "low", "uncertain"]
    reasoning: str | None = None


T = TypeVar("T", bound=BaseModel)


class LlmClient:
    """A thin HTTP wrapper to call OpenAI-compatible structured output APIs."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float,
        max_validation_retries: int,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.temperature = temperature
        self.max_validation_retries = max_validation_retries

    def structured(
        self,
        client: Any,
        prompt: str,
        output_type: type[T],
        *,
        system: str | None = None,
    ) -> tuple[T, dict[str, Any]]:
        """Request structured output with a semantic retry loop.

        Returns a tuple of the validated model instance and a metadata dictionary
        containing provenance (attempt_count, raw_output, etc).
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        schema = output_type.model_json_schema()
        last_error = None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        metadata: dict[str, Any] = {
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "schema_name": output_type.__name__,
            "attempt_count": 0,
        }

        for attempt in range(self.max_validation_retries + 1):
            metadata["attempt_count"] = attempt + 1
            if last_error:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous output failed validation:\n"
                            f"{last_error}\n\n"
                            "Return a corrected result following the JSON schema exactly."
                        ),
                    }
                )

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": output_type.__name__,
                        "schema": schema,
                        "strict": True,
                    },
                },
            }

            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            # Capture the raw completion response for provenance
            metadata["raw_response"] = data

            try:
                text = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as exc:
                msg = f"Unexpected response structure: {data}"
                raise ValueError(msg) from exc

            try:
                result = output_type.model_validate_json(text)
                return result, metadata
            except ValidationError as exc:
                last_error = exc
                metadata["last_failed_text"] = text
        if last_error is not None:
            raise last_error
        msg = "Retries exhausted without validation error."
        raise RuntimeError(msg)


class LocalLlmMethod(GenderMethod[LocalLlmConfig]):
    """Method adapter for OpenAI-compatible LLMs."""

    descriptor = LOCAL_LLM_DESCRIPTOR
    config_model = LocalLlmConfig

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: LocalLlmConfig,
    ) -> list[PredictionResult]:
        """Classify a batch of people sequentially using the configured LLM API.

        Raises:
            MethodDependencyError: If the ``llm`` extra is not installed.
        """
        try:
            import httpx  # pyright: ignore[reportMissingImports]
        except ImportError as error:
            msg = "local_llm requires the 'llm' extra (install httpx)"
            raise MethodDependencyError(msg) from error

        llm = LlmClient(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            temperature=config.temperature,
            max_validation_retries=config.max_validation_retries,
        )

        results: list[PredictionResult] = []

        with httpx.Client() as client:
            for person in people:
                prompt = self._build_prompt(person)

                try:
                    classification, metadata = llm.structured(
                        client=client,
                        prompt=prompt,
                        output_type=PersonClassification,
                        system=config.system_prompt,
                    )

                    raw_output = metadata.pop("raw_response", {})
                    if classification.reasoning:
                        raw_output["reasoning"] = classification.reasoning

                    metadata["self_reported_certainty"] = classification.certainty

                    result = normalize_raw_label(
                        LOCAL_LLM_NORMALIZATION,
                        classification.gender,
                        method_confidence=classification.confidence,
                        raw_output=raw_output,
                        metadata=metadata,
                    )
                except Exception as exc:
                    # Catch transport and validation errors for the individual record
                    result = PredictionResult(
                        label=None,
                        status=PredictionStatus.error,
                        raw_output={"error": str(exc)},
                        metadata={},
                    )

                results.append(result)

        return validate_prediction_batch(self.descriptor, people, results)

    def _build_prompt(self, person: PersonInput) -> str:
        prompt_parts = ["Please identify the gender of the following historical person."]

        prompt_parts.append(f"TEI ID: {person.tei_id}")

        if person.name_forms is not None:
            for form in person.name_forms:
                name_text = form.projected_text()
                label = "Name" if form.type == "reg" else "Alternative name"
                if form.subtype:
                    label += f" ({form.subtype})"
                prompt_parts.append(f"{label}: {name_text}")
        else:
            name_parts = []
            if person.forenames:
                name_parts.append(" ".join(person.forenames))
            if person.surname:
                name_parts.append(person.surname)
            if name_parts:
                prompt_parts.append(f"Name: {' '.join(name_parts)}")

            if person.alt_names:
                prompt_parts.append(f"Alternative names: {', '.join(person.alt_names)}")

        if person.birth or person.death:
            dates = f"{person.birth or '?'} - {person.death or '?'}"
            prompt_parts.append(f"Life dates: {dates}")

        if person.note:
            prompt_parts.append(f"Note: {person.note}")

        for event in person.events:
            event_desc = f"Event ({event.type})"
            if event.when:
                event_desc += f" at {event.when}"
            if event.note:
                event_desc += f": {event.note}"
            prompt_parts.append(event_desc)

        if person.gnd_id:
            prompt_parts.append(f"GND ID: {person.gnd_id}")

        for system, ext_id in person.external_ids.items():
            prompt_parts.append(f"External ID ({system}): {ext_id}")

        return "\n".join(prompt_parts)
