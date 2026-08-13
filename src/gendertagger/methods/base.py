"""Method adapter contracts and boundary validation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from gendertagger.models.classification import PredictionResult
from gendertagger.models.method import MethodDescriptor
from gendertagger.models.person import PersonInput


class MethodConfig(BaseModel):
    """Closed base contract for adapter-specific resolved configuration."""

    model_config = ConfigDict(extra="forbid")


MethodConfigT = TypeVar("MethodConfigT", bound=MethodConfig)


class GenderMethod(Protocol[MethodConfigT]):
    """Structural contract implemented by every classification adapter."""

    descriptor: MethodDescriptor
    config_model: type[MethodConfigT]

    def predict_batch(
        self,
        people: Sequence[PersonInput],
        config: MethodConfigT,
    ) -> list[PredictionResult]:
        """Classify people and return one result per input in the same order.

        Record-specific scientific or input failures are represented by error
        results. Batch-wide infrastructure failures and invalid adapter or
        configuration state raise so orchestration can apply retry policy.
        """
        ...


class MethodContractError(ValueError):
    """Raised when an adapter violates its declared result contract."""


def validate_prediction_batch(
    descriptor: MethodDescriptor,
    people: Sequence[PersonInput],
    predictions: list[PredictionResult],
) -> list[PredictionResult]:
    """Validate adapter result cardinality and declared confidence semantics.

    Args:
        descriptor: Metadata declared by the producing adapter.
        people: Ordered inputs supplied to the adapter.
        predictions: Ordered outputs returned by the adapter.

    Returns:
        The original prediction list after successful validation.

    Raises:
        MethodContractError: If output cardinality differs from the input or a
            confidence value violates the adapter descriptor.
    """
    if len(predictions) != len(people):
        msg = (
            f"method '{descriptor.name}' returned {len(predictions)} predictions "
            f"for {len(people)} people"
        )
        raise MethodContractError(msg)

    declared_range = descriptor.method_confidence_range
    for index, prediction in enumerate(predictions):
        method_confidence = prediction.method_confidence
        if method_confidence is None:
            continue
        if declared_range is None:
            msg = (
                f"method '{descriptor.name}' returned confidence at index {index} "
                "without declaring a range"
            )
            raise MethodContractError(msg)
        if not declared_range.minimum <= method_confidence <= declared_range.maximum:
            msg = (
                f"method '{descriptor.name}' returned confidence {method_confidence} "
                f"outside [{declared_range.minimum}, {declared_range.maximum}] at index {index}"
            )
            raise MethodContractError(msg)

    return predictions
