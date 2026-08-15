"""Direct on-demand classification service for arbitrary name inputs."""

from __future__ import annotations

import threading
from collections import Counter, OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import JsonValue, ValidationError

from gendertagger.domain.aggregation import (
    REFERENCE_REQUIRED_METHODS,
    ReferenceAggregationError,
)
from gendertagger.domain.aggregation_assessment import (
    ReferenceAssessmentError,
    _agreement_tier_for_score,
    _rounded_share,
    assess_reference_predictions,
)
from gendertagger.methods.base import MethodDependencyError, validate_prediction_batch
from gendertagger.models.aggregation import AggregationOutcome, OverrideSource, VoteCounts
from gendertagger.models.classification import (
    AgreementTier,
    CanonicalLabel,
    PredictionResult,
    PredictionStatus,
)
from gendertagger.models.classify import (
    AggregatedClassification,
    ClassifyNamesResponse,
    MethodClassification,
    NameClassificationResult,
)
from gendertagger.models.person import PersonInput
from gendertagger.services.method_registry import MethodRegistry, UnknownMethodError
from gendertagger.services.unit_of_work import UnitOfWorkFactory

DEFAULT_CACHE_MAX_SIZE = 50_000


class DirectClassificationService:
    """Classify arbitrary names synchronously across registered classification adapters."""

    def __init__(
        self,
        *,
        method_registry: MethodRegistry,
        unit_of_work_factory: UnitOfWorkFactory | None = None,
        cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
    ) -> None:
        self._method_registry = method_registry
        self._unit_of_work_factory = unit_of_work_factory
        self._cache_max_size = cache_max_size
        self._cache: OrderedDict[tuple[str, str, str], PredictionResult] = OrderedDict()
        self._lock = threading.Lock()

    def classify_names(
        self,
        names: Sequence[str],
        methods: Sequence[str] | None = None,
        method_configs: Mapping[str, Mapping[str, JsonValue]] | None = None,
    ) -> ClassifyNamesResponse:
        """Classify each input name across the selected method adapters.

        Args:
            names: Ordered list of non-blank names to classify.
            methods: Optional subset of registered method names to execute; defaults to
                all registered methods in registration order.
            method_configs: Optional explicit configuration dictionaries keyed by method name.

        Returns:
            A :class:`~gendertagger.models.classify.ClassifyNamesResponse` mapping each input name
            to its per-method classification results and aggregated ensemble verdict.

        Raises:
            UnknownMethodError: If an unknown method name is requested.
        """
        selected_registrations = self._resolve_registrations(methods)
        people = [
            PersonInput(tei_id=f"name_{index + 1}", forenames=[name])
            for index, name in enumerate(names)
        ]

        predictions_by_name: list[dict[str, PredictionResult]] = [
            {} for _ in range(len(names))
        ]
        classifications_by_name: list[dict[str, MethodClassification]] = [
            {} for _ in range(len(names))
        ]

        for registration in selected_registrations:
            method_name = registration.descriptor.name
            method_predictions = self._execute_method(
                registration=registration,
                people=people,
                names=names,
                raw_config=method_configs.get(method_name) if method_configs else None,
            )
            for index, prediction in enumerate(method_predictions):
                predictions_by_name[index][method_name] = prediction
                classifications_by_name[index][method_name] = MethodClassification(
                    label=prediction.label,
                    status=prediction.status,
                    method_confidence=prediction.method_confidence,
                    raw_label=prediction.raw_label,
                    error_message=(
                        str(prediction.raw_output.get("error"))
                        if prediction.status is PredictionStatus.error
                        and "error" in prediction.raw_output
                        else None
                    ),
                )

        results = []
        for index, name in enumerate(names):
            aggregated = self._aggregate_predictions(predictions_by_name[index])
            results.append(
                NameClassificationResult(
                    name=name,
                    classifications=classifications_by_name[index],
                    aggregated=aggregated,
                )
            )

        return ClassifyNamesResponse(results=results)

    def _resolve_registrations(self, methods: Sequence[str] | None) -> tuple[Any, ...]:
        if methods is None:
            return self._method_registry.registrations

        registrations = []
        for method_name in methods:
            registration = self._method_registry.registration_for(method_name)
            if registration is None:
                msg = f"method {method_name!r} is not registered"
                raise UnknownMethodError(msg)
            registrations.append(registration)
        return tuple(registrations)

    def _execute_method(
        self,
        *,
        registration: Any,
        people: Sequence[PersonInput],
        names: Sequence[str],
        raw_config: Mapping[str, JsonValue] | None,
    ) -> list[PredictionResult]:
        method_name = registration.descriptor.name
        try:
            config = self._resolve_config(registration, raw_config)
            config_key = config.model_dump_json() if hasattr(config, "model_dump_json") else str(config)
        except (MethodDependencyError, ValidationError, Exception) as error:
            error_message = f"{type(error).__name__}: {error}".strip()
            return [
                PredictionResult(
                    label=None,
                    status=PredictionStatus.error,
                    raw_label="error",
                    raw_output={"error": error_message},
                )
                for _ in people
            ]

        results: list[PredictionResult | None] = [None] * len(people)
        miss_indices: list[int] = []
        miss_people: list[PersonInput] = []

        with self._lock:
            for index, (person, name) in enumerate(zip(people, names, strict=True)):
                del person
                cache_key = (method_name, config_key, name)
                cached = self._cache.get(cache_key)
                if cached is not None:
                    self._cache.move_to_end(cache_key)
                    results[index] = PredictionResult(
                        label=cached.label,
                        status=cached.status,
                        method_confidence=cached.method_confidence,
                        raw_label=cached.raw_label,
                        raw_output=dict(cached.raw_output),
                        metadata=dict(cached.metadata),
                    )
                else:
                    miss_indices.append(index)
                    miss_people.append(people[index])

        if miss_people:
            try:
                new_predictions: list[PredictionResult] = registration.adapter.predict_batch(miss_people, config)
                validate_prediction_batch(registration.descriptor, miss_people, new_predictions)
            except (MethodDependencyError, ValidationError, Exception) as error:
                error_message = f"{type(error).__name__}: {error}".strip()
                new_predictions = [
                    PredictionResult(
                        label=None,
                        status=PredictionStatus.error,
                        raw_label="error",
                        raw_output={"error": error_message},
                    )
                    for _ in miss_people
                ]

            with self._lock:
                for miss_idx, pred in zip(miss_indices, new_predictions, strict=True):
                    results[miss_idx] = pred
                    cache_key = (method_name, config_key, names[miss_idx])
                    self._cache[cache_key] = pred
                    self._cache.move_to_end(cache_key)
                    if len(self._cache) > self._cache_max_size:
                        self._cache.popitem(last=False)

        return [r for r in results if r is not None]

    def _aggregate_predictions(
        self, predictions: Mapping[str, PredictionResult]
    ) -> AggregatedClassification:
        supplied_methods = set(predictions)
        if set(REFERENCE_REQUIRED_METHODS).issubset(supplied_methods):
            try:
                ref_result = assess_reference_predictions(predictions)
                return AggregatedClassification(
                    label=ref_result.label,
                    outcome=ref_result.outcome,
                    certainty_tier=ref_result.certainty_tier,
                    agreement_tier=ref_result.agreement_tier,
                    agreement_score=ref_result.agreement_score,
                    vote_counts=ref_result.pooled_vote_counts,
                    override_source=ref_result.override_source,
                )
            except (ReferenceAggregationError, ReferenceAssessmentError):
                pass

        return self._aggregate_subset_predictions(predictions)

    def _aggregate_subset_predictions(
        self, predictions: Mapping[str, PredictionResult]
    ) -> AggregatedClassification:
        parenthetical = predictions.get("parenthetical_qualifier")
        parenthetical_label = (
            parenthetical.label
            if parenthetical and parenthetical.status is PredictionStatus.success
            else None
        )

        gnd = predictions.get("gnd")
        gnd_label = gnd.label if gnd and gnd.status is PredictionStatus.success else None
        substantive_gnd_label = (
            gnd_label if gnd_label is not None and gnd_label is not CanonicalLabel.unknown else None
        )

        pooled_labels = [
            pred.label
            for name, pred in predictions.items()
            if name not in ("parenthetical_qualifier", "hivoto_xgboost", "gnd")
            and pred.status is PredictionStatus.success
            and pred.label is not None
        ]

        if gnd and gnd.status is PredictionStatus.success and gnd.label is CanonicalLabel.unknown:
            pooled_labels.append(CanonicalLabel.unknown)

        vote_counts = self._count_votes(pooled_labels)

        if parenthetical_label is not None:
            comparison_count = len(pooled_labels) + int(substantive_gnd_label is not None)
            agreeing_count = sum(label is parenthetical_label for label in pooled_labels) + int(
                substantive_gnd_label is parenthetical_label
            )
            if comparison_count == 0:
                agreement_score, agreement_tier = 1.0, AgreementTier.single_rater
            else:
                agreement_score = _rounded_share(agreeing_count, comparison_count)
                agreement_tier = _agreement_tier_for_score(agreement_score)
            return AggregatedClassification(
                label=parenthetical_label,
                outcome=AggregationOutcome.decided,
                certainty_tier=None,
                agreement_tier=agreement_tier,
                agreement_score=agreement_score,
                vote_counts=vote_counts,
                override_source=OverrideSource.parenthetical_qualifier,
            )

        if substantive_gnd_label is not None:
            comparison_count = len(pooled_labels)
            agreeing_count = sum(label is substantive_gnd_label for label in pooled_labels)
            if comparison_count == 0:
                agreement_score, agreement_tier = 1.0, AgreementTier.single_rater
            else:
                agreement_score = _rounded_share(agreeing_count, comparison_count)
                agreement_tier = _agreement_tier_for_score(agreement_score)
            return AggregatedClassification(
                label=substantive_gnd_label,
                outcome=AggregationOutcome.decided,
                certainty_tier=None,
                agreement_tier=agreement_tier,
                agreement_score=agreement_score,
                vote_counts=vote_counts,
                override_source=OverrideSource.gnd,
            )

        if not pooled_labels:
            return AggregatedClassification(
                label=None,
                outcome=AggregationOutcome.no_data,
                certainty_tier=None,
                agreement_tier=AgreementTier.no_answer,
                agreement_score=None,
                vote_counts=vote_counts,
                override_source=None,
            )

        max_count = max(vote_counts.for_label(label) for label in CanonicalLabel)
        top_labels = tuple(
            label for label in CanonicalLabel if vote_counts.for_label(label) == max_count
        )

        if len(top_labels) == 1:
            winning_label = top_labels[0]
            total_votes = len(pooled_labels)
            score = _rounded_share(max_count, total_votes) if total_votes > 1 else 1.0
            tier = (
                AgreementTier.single_rater
                if total_votes == 1
                else _agreement_tier_for_score(score)
            )
            return AggregatedClassification(
                label=winning_label,
                outcome=AggregationOutcome.decided,
                certainty_tier=None,
                agreement_tier=tier,
                agreement_score=score,
                vote_counts=vote_counts,
                override_source=None,
            )

        substantive_top = tuple(
            label for label in top_labels if label is not CanonicalLabel.unknown
        )
        if CanonicalLabel.unknown in top_labels and len(substantive_top) == 1:
            winning_label = substantive_top[0]
            total_votes = len(pooled_labels)
            score = _rounded_share(max_count, total_votes) if total_votes > 1 else 1.0
            tier = (
                AgreementTier.single_rater
                if total_votes == 1
                else _agreement_tier_for_score(score)
            )
            return AggregatedClassification(
                label=winning_label,
                outcome=AggregationOutcome.decided,
                certainty_tier=None,
                agreement_tier=tier,
                agreement_score=score,
                vote_counts=vote_counts,
                override_source=None,
            )

        total_votes = len(pooled_labels)
        score = _rounded_share(max_count, total_votes)
        return AggregatedClassification(
            label=None,
            outcome=AggregationOutcome.unresolved_tie,
            certainty_tier=None,
            agreement_tier=AgreementTier.no_consensus,
            agreement_score=score,
            vote_counts=vote_counts,
            override_source=None,
        )

    @staticmethod
    def _count_votes(labels: Sequence[CanonicalLabel]) -> VoteCounts:
        counts = Counter(labels)
        return VoteCounts(
            male=counts[CanonicalLabel.male],
            female=counts[CanonicalLabel.female],
            unknown=counts[CanonicalLabel.unknown],
            institution=counts[CanonicalLabel.institution],
        )

    def _resolve_config(
        self,
        registration: Any,
        raw_config: Mapping[str, JsonValue] | None,
    ) -> Any:
        if raw_config is not None:
            return registration.config_model.model_validate(raw_config)

        if registration.data_artifact_logical_type is not None:
            if self._unit_of_work_factory is None:
                msg = f"method {registration.descriptor.name!r} requires a lookup artifact"
                raise MethodDependencyError(msg)
            with self._unit_of_work_factory() as unit_of_work:
                artifact = unit_of_work.artifacts.get_latest_artifact(
                    registration.data_artifact_logical_type
                )
            if artifact is None:
                msg = (
                    f"no registered lookup artifact for {registration.data_artifact_logical_type!r}"
                )
                raise MethodDependencyError(msg)
            return registration.config_model.model_validate({"lookup_sha256": artifact.sha256})

        return registration.config_model.model_validate({})
