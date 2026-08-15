"""Pairwise Cohen's kappa restricted to co-answered entries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations

from sklearn.metrics import cohen_kappa_score

from gendertagger.models.classification import CanonicalLabel, PredictionResult, PredictionStatus
from gendertagger.models.evaluation import KappaCell

_ROUNDING_DECIMAL_PLACES = 3
_MINIMUM_CO_ANSWERED_FOR_KAPPA = 2


def compute_kappa_matrix(
    methods: Sequence[str],
    corpus: Sequence[Mapping[str, PredictionResult]],
) -> tuple[KappaCell, ...]:
    """Pairwise Cohen's kappa for every method pair, restricted to co-answered entries.

    A pair reports ``kappa=None`` instead of a misleading number when fewer
    than two entries are co-answered, or when every co-answered label is
    identical for both methods (kappa is undefined -- both raters are
    constant, so expected agreement equals one).

    Args:
        methods: Method identifiers entering the matrix, in the order pairs
            are generated (``itertools.combinations`` over this sequence).
        corpus: One prediction mapping per person.

    Returns:
        One cell per unordered method pair.
    """
    cells: list[KappaCell] = []
    for method_a, method_b in combinations(methods, 2):
        labels_a: list[CanonicalLabel] = []
        labels_b: list[CanonicalLabel] = []
        for person in corpus:
            label_a = _successful_label(person[method_a])
            label_b = _successful_label(person[method_b])
            if label_a is not None and label_b is not None:
                labels_a.append(label_a)
                labels_b.append(label_b)

        co_answered_count = len(labels_a)
        kappa: float | None = None
        if co_answered_count >= _MINIMUM_CO_ANSWERED_FOR_KAPPA and (
            len(set(labels_a)) > 1 or len(set(labels_b)) > 1
        ):
            raw_kappa = float(cohen_kappa_score(labels_a, labels_b))
            kappa = max(-1.0, min(1.0, round(raw_kappa, _ROUNDING_DECIMAL_PLACES)))

        cells.append(
            KappaCell(
                method_a=method_a,
                method_b=method_b,
                co_answered_count=co_answered_count,
                kappa=kappa,
            )
        )
    return tuple(cells)


def _successful_label(prediction: PredictionResult) -> CanonicalLabel | None:
    return prediction.label if prediction.status is PredictionStatus.success else None
